<!--
 * @Description: 缺陷单
-->
<template>
  <div class="app-container !pt-4.25 bg-white">
    <fs-crud ref="crudRef" v-bind="crudBinding">
      <!-- 左上按钮右侧 -->
      <template #actionbar-right>
        <el-tooltip content="当前任务超框和漏译">
          <el-button
            class="ml-1.5"
            v-if="crudBinding.data && crudBinding.data.length" icon="Download" type="primary"
            @click="exportToExcel()" :loading="loadingExcel"
          >
            导出
          </el-button>
        </el-tooltip>
        <!-- 编辑 -->

        <el-button :disabled="!selectedIds.length" type="primary" plain @click="reduEdit">回归状态编辑</el-button>


        <!-- 已选 x 个 -->
        <template v-if="selectedIds.length">
          <el-divider opacity-50 direction="vertical" />
          <el-tag size="large" type="info" >
            已选 <span style="font-weight: bold">{{selectedIds.length}}</span> 个
          </el-tag>
        </template>
      </template>
      <!-- 回归任务 -->
      <template #cell_regress_job_ids="scope">
        <template v-if="scope.row.regress_job_ids">
          <el-button
            class="!ml-0"
            v-for="taskId in (scope.row.regress_job_ids || [])" :key="taskId"
            type="primary" link @click="openTask(taskId)"
          >{{taskId}}</el-button>
        </template>
      </template>
    </fs-crud>

    <!-- 编辑表单 -->
    <fs-form-wrapper ref="editReduFormWrapperRef" />
    <!-- 回归表单 -->
    <fs-form-wrapper ref="formWrapperRef">
      <!-- 译文资源 -->
      <template #form_translate_resource="scope">
        <translate-resource
          ref="translateResourceRef"
          v-model="scope.form.translate_resource" :disabled="scope.attrs.disabled"
        />
      </template>
    </fs-form-wrapper>
  </div>
</template>

<script>
import { defineComponent, onMounted, ref } from 'vue';
import { useColumns, useFs } from '@fast-crud/fast-crud';
import { ElMessage } from 'element-plus';
import createCrudOptions from './crud.js';
import createEditCrudOptions from './editRedu.jsx';
import { useRoute, useRouter } from 'vue-router';
import { customRequest } from '@/utils/service.ts';
import translateResource from '@/views/task/runTask/translateResource.vue';

export default defineComponent({
  name: 'Bugs',
  components: { translateResource },

  setup() {
    const route = useRoute();
    const router = useRouter();
    const formWrapperRef = ref();
    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose, selectedIds } = useFs({ createCrudOptions, context: {
      clearRefresh, formWrapperRef,
    } });

    onMounted(() => {
      // 页面打开后立即加载列表数据
      crudExpose.doRefresh();
    });

    function openTask(taskId) {
      const currentRouteArr = route.path.split('/').slice(0, -1);
      currentRouteArr.push(`task?id=${taskId}`);
      router.push(currentRouteArr.join('/'));
    }

    const { buildFormOptions } = useColumns();
    // 还原编辑
    const editReduFormWrapperRef = ref();
    function reduEdit() {
      const formOptions = buildFormOptions(createEditCrudOptions(route, selectedIds, clearRefresh));
      editReduFormWrapperRef.value.open(formOptions);
    }
    /** 导出当前任务有效缺陷 */
    const loadingExcel = ref(false);
    function exportToExcel() {
      const firstRow = crudBinding.value?.data?.[0];
      const jobId = Number(route.query.job_id) || Number(firstRow?.job_id) || 0;
      if (!jobId) {
        ElMessage.warning('缺少任务 ID，无法导出');
        return;
      }
      const imageId = Number(route.query.image_id) || 0;
      loadingExcel.value = true;
      customRequest({
        url: '/api/bug/export_excel',
        method: 'get',
        params: imageId ? { job_id: jobId, image_id: imageId } : { job_id: jobId },
        responseType: 'blob',
        silent: true, // blob 响应，拦截器无法解析错误 msg，这里自己处理
      }).then((blob) => {
        // 服务端异常时后端返回 JSON（{code, msg}），需要从 blob 中解析
        if (blob?.type?.includes('application/json') || blob?.size < 1024) {
          return blob.text().then((text) => {
            try {
              const data = JSON.parse(text);
              if (data && typeof data.code !== 'undefined' && data.code !== 0) {
                ElMessage.error(data.msg || '导出失败');
                return;
              }
            } catch (e) {
              // 不是 JSON，当成正常文件处理
            }
            downloadBlob(blob);
          });
        }
        downloadBlob(blob);
        return undefined;
      })
        .catch((err) => {
          // HTTP 非 2xx：尝试从 blob 中解析后端 msg
          const data = err?.response?.data;
          if (data instanceof Blob) {
            data.text().then((text) => {
              try {
                const parsed = JSON.parse(text);
                ElMessage.error(parsed.msg || parsed.message || '导出失败');
              } catch (e) {
                ElMessage.error('请求失败,请联系管理员');
              }
            });
          } else {
            ElMessage.error(data?.msg || err?.message || '请求失败,请联系管理员');
          }
          console.log(`export_excel 接口调用失败: ${err}`);
        })
        .finally(() => {
          loadingExcel.value = false;
        });

      function downloadBlob(blob) {
        const url = window.URL.createObjectURL(new Blob([blob]));
        const a = document.createElement('a');
        a.href = url;
        a.download = `bugs_job${jobId}${imageId ? `_image${imageId}` : ''}.xlsx`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
      }
    }

    /** 清除选中并刷新 */
    function clearRefresh() {
      selectedIds.value = [];
      crudExpose.getTableRef().tableRef.clearSelection();
      crudExpose.doRefresh();
    }

    return {
      crudBinding,
      crudRef,
      openTask,
      exportToExcel,
      editReduFormWrapperRef,
      loadingExcel,
      selectedIds,
      formWrapperRef,
      reduEdit,
    };
  },
});

</script>
