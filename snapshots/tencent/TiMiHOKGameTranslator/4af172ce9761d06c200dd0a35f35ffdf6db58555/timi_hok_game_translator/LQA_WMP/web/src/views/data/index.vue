<!--
 * @Description: 数据管理
-->
<template>
  <div class="app-container !pt-4.25 bg-white">
    <imgDraw :page-reviews="pageReviews" ref="imgDrawRef" />

    <fs-crud ref="crudRef" v-bind="crudBinding">
      <!-- 操作按钮 -->
      <template #actionbar-right>
        <!-- 编辑 -->
        <el-button :disabled="!selectedIds.length" type="primary" plain @click="openEdit">编辑</el-button>
        <!-- 删除 -->
        <el-popconfirm title="确定批量删除选中数据？" width="200" @confirm="batchDelete">
          <template #reference>
              <el-button :disabled="!selectedIds.length" type="danger" plain>删除</el-button>
          </template>
        </el-popconfirm>

        <!-- 已选 n 个 -->
        <template v-if="selectedIds.length">
          <el-divider class="!mx-3" opacity-50 direction="vertical" />
          <el-tag size="large" type="info" >
            已选 <span style="font-weight: bold">{{selectedIds.length}}</span> 个
          </el-tag>
        </template>
      </template>
    </fs-crud>

    <!-- JSON 预览 -->
		<el-dialog
			v-model="jsonViewDialog.visible"
			draggable
			:title="jsonViewDialog.title"
			align-center
		>
			<div class="max-h-[75vh] overflow-y-auto">
				<JsonViewer :value="jsonViewDialog.value" copyable boxed sort />
			</div>
		</el-dialog>

    <!-- 编辑表单 -->
    <fs-form-wrapper ref="editFormWrapperRef" />
  </div>
</template>

<script>
import { defineComponent, onMounted, reactive, ref } from 'vue';
import { dict, useColumns, useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.jsx';
import { JsonViewer } from 'vue3-json-viewer';
import createEditCrudOptions from './editCrud.jsx';
import { useRoute } from 'vue-router';
import { customRequest } from '@/utils/service.ts';
import { ElMessage } from 'element-plus';
import imgDraw from './imgDraw.vue';

export default defineComponent({
  name: 'Task',
  components: { JsonViewer, imgDraw },
  setup() {
    const route = useRoute();
    const jsonViewDialog = reactive({
      visible: false,
      title: '',
      value: '',
    });
    const imgDrawRef = ref();

    const versionDict =  dict({
      url: '/api/data/resource_version/list',
      cache: false,
      async getData({ url }) {
      // 获取字典请求
      // @ts-ignore
        const { data } = await customRequest({ url, method: 'get', params: { project_id: route.meta.value } });
        return data.list.map(item => ({ label: item, value: item }));
      },
    });

    // fs-crud 初始化
    const { selectedIds, pageReviews, crudRef, crudBinding, crudExpose } = useFs({ createCrudOptions, context: {
      jsonViewDialog, clearRefresh, versionDict, imgDrawRef,
    } });

    onMounted(() => {
      // 页面打开后立即加载列表数据
      crudExpose.doRefresh();
    });

    const { buildFormOptions } = useColumns();

    // 编辑
    const editFormWrapperRef = ref();
    function openEdit() {
      const formOptions = buildFormOptions(createEditCrudOptions(route, selectedIds, clearRefresh));
      editFormWrapperRef.value.open(formOptions);
    }

    async function batchDelete() {
      await customRequest({
        url: '/api/data/list',
        method: 'delete',
        data: { ids: selectedIds.value },
      });
      ElMessage.success('删除成功');
      clearRefresh();
    }

    /** 清除选中并刷新 */
    function clearRefresh() {
      selectedIds.value = [];
      crudExpose.getTableRef().tableRef.clearSelection();
      crudExpose.doRefresh();
      versionDict.reloadDict();
    }

    return {
      selectedIds,
      crudBinding,
      crudRef,
      jsonViewDialog,
      editFormWrapperRef,
      openEdit,
      batchDelete,
      imgDrawRef,
      pageReviews,
    };
  },
});
</script>
