<!--
 * @Description: 结果审核
-->
<template>
  <div class="app-container !pt-4.25 bg-white">
    <fs-crud ref="crudRef" v-bind="crudBinding">
      <!-- 左上按钮 -->
      <template #actionbar-right>
        <!-- 任务全量识别 -->
        <template v-if="$route.query.job_id">
          <el-divider opacity-50 direction="vertical" />
          <el-button @click="recognizeDialogVisible = true">全量识别</el-button>
        </template>

        <template v-if="selectedIds.length">
          <el-divider opacity-50 direction="vertical" />
          <!-- 已选 n 条 -->
          <el-tag size="large" type="info">
            已选 <span style="font-weight: bold">{{ selectedIds.length }}</span> 个
          </el-tag>
          <el-divider opacity-50 direction="vertical" />
          <!-- 审核标注 -->
          <el-button type="success" plain @click="batchAudit(selectedIds, 1)">已审核</el-button>
          <el-button type="danger" plain @click="batchAudit(selectedIds, 0)">未审核</el-button>
          <!-- 删除 -->
          <el-divider opacity-50 direction="vertical" />
          <el-popconfirm title="确定批量删除选中数据？" width="200" @confirm="() => batchDelete(selectedIds)">
            <template #reference>
                <el-button type="danger" plain>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </template>

      <!-- 图片名称-->
      <template #cell_file_name="scope">
        <template v-if="scope.row.file_name">
          <span v-for="(part, index) in scope.row.file_name.split('-')" :key="index">
            <template v-if="isNumeric(part) && index === 1">
              <el-tooltip effect="dark" content="点击查看对应数据" placement="top">
                <a @click="navigateToData(part)">{{ part }}</a>
              </el-tooltip>
            </template>
            <template v-else>
              {{ part }}
            </template>
            <template v-if="index < scope.row.file_name.split('-').length - 1"> - </template>
          </span>
        </template>
      </template>

      <!-- 检测文本 -->
      <template #cell_rect_location="scope">
        <el-button type="primary" icon="View" size="small" link @click="openPreview(scope.row)" />
        <el-divider direction="vertical" />
        <el-button type="primary" icon="Download" size="small" link @click="handleDownload(scope.row)" />
      </template>

      <!-- 还原图片 -->
      <template v-for="imgKey in imgKeys" :key="imgKey"  #[`cell_${imgKey}`]="{ $index, row, value }">
        <el-image
          :src="`${imgPrefix}${value}`"
          :preview-src-list="previewImgs"
          :initial-index="currentImageIndex"
          preview-teleported
          :infinite="false"
          @show="onOpenImgPreview($index * imgKeys.length + imgKeys.indexOf(imgKey))"
          @switch="val => currentImageIndex = val"
          @close="stopAutoPlayImg"
        >
          <template #toolbar="{ actions, prev, next, reset, activeIndex, setActiveItem }">
            <!-- 自动切换 -->
            <el-tooltip v-if="!imageInterval" content="自动切换下一行" :disabled="autoPlayDisabled">
              <el-icon @click="startAutoPlayImg">
                <fs-icon
                  :class="{
                    'opacity-25 cursor-not-allowed': autoPlayDisabled
                  }"
                  icon="solar:playback-speed-outline"
                />
              </el-icon>
            </el-tooltip>
            <el-tooltip v-else content="停止切换">
              <el-icon @click="stopAutoPlayImg">
                <fs-icon
                  icon="mdi:stop-circle-outline"
                />
              </el-icon>
            </el-tooltip>
            <!-- 上一行 -->
            <el-icon
              @click="imagePageDisable(activeIndex, 'prev') ? '' : setActiveItem(activeIndex - imgKeys.length)"
            >
              <arrow-up
                :class="{ 'opacity-25 cursor-not-allowed': imagePageDisable(activeIndex, 'prev', setActiveItem) }"
              />
            </el-icon>
            <!-- 下一行 -->
            <el-icon
              @click="imagePageDisable(activeIndex, 'next') ? '' : setActiveItem(activeIndex + imgKeys.length)"
            >
              <arrow-down :class="{ 'opacity-25 cursor-not-allowed': imagePageDisable(activeIndex, 'next') }"/>
            </el-icon>
            <!-- 缩小 -->
            <el-icon @click="actions('zoomOut')"><zoom-out /></el-icon>
            <!-- 放大 -->
            <el-icon @click="actions('zoomIn')"><zoom-in /></el-icon>
            <!-- 顺时针转 -->
            <el-icon @click=" actions('clockwise')"><refresh-right /></el-icon>
            <!-- 逆时针转 -->
            <el-icon @click="actions('anticlockwise')"><refresh-left /></el-icon>
            <!-- 下载 -->
            <el-icon @click="downloadByUrl(previewImgs[activeIndex])"><download /></el-icon>
          </template>
        </el-image>
      </template>

      <!-- 操作列左侧 -->
      <template #cell-rowHandle-left="scope">
        <el-dropdown>
          <span class="el-dropdown-link">
            识别
            <el-icon class="el-icon--right"><arrow-down /></el-icon>
          </span>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="imgRecognition(scope.row.id, 1)">差异</el-dropdown-item>
              <el-dropdown-item @click="imgRecognition(scope.row.id, 0)">全量</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </template>
    </fs-crud>

    <!-- JSON 预览 -->
    <el-dialog v-model="jsonViewDialog.visible" draggable :title="jsonViewDialog.title" align-center>
      <div class="max-h-[75vh] overflow-y-auto">
        <JsonViewer :value="jsonViewDialog.value" copyable boxed sort />
      </div>
    </el-dialog>

    <!-- 提单表单 -->
    <fs-form-wrapper ref="formWrapperRef" />

    <!-- 全量识别弹窗 -->
    <recognizeDialog
      v-if="$route.query.job_id"
      v-model="recognizeDialogVisible"
      :project-id="$route.meta.value"
      :job-id="$route.query.job_id"
      @refresh="doRefresh"
    />
  </div>
</template>

<script>
import { computed, defineComponent, onUnmounted, reactive, ref } from 'vue';
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.js';
import { JsonViewer } from 'vue3-json-viewer';
import { downloadByData, downloadByUrl } from '@/utils/download.ts';
import { customRequest } from '@/utils/service.ts';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import recognizeDialog from './recognizeDialog.vue';

export default defineComponent({
  name: 'Audit',
  components: { JsonViewer, recognizeDialog },
  setup() {
    const imgKeys = ['shot_img_path', 'file_path', 'ai_mark_img_path', 'ai_rect_img_path'];
    const imgPrefix = import.meta.env.VITE_RESOURCE_API;
    const jsonViewDialog = reactive({
      visible: false,
      title: '',
      value: '',
    });
    const route = useRoute();
    const router = useRouter();
    const formWrapperRef = ref();
    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose, selectedIds, pageData, previewImgs } = useFs({
      createCrudOptions,
      context: {
        imgPrefix,
        imgKeys,
        formWrapperRef,
        clearRefresh,
      },
    });

    // onMounted(() => {
    // 页面打开后立即加载列表数据
    // crudExpose.doRefresh();
    // });

    // 图片名称方法
    function navigateToData(number) {
      router.push({
        path: 'data',
        query: { id: number },
      });
    }
    function isNumeric(str) {
      return /^\d+$/.test(str); // 检查字符串是否全为数字
    }

    /** 图片上下张判断 */
    let setActiveItemFunc = () => {};
    function imagePageDisable(activeIndex, type, setActiveItem) {
      if (setActiveItem) {
        setActiveItemFunc = setActiveItem;
      }
      if (type === 'prev') {
        return (activeIndex - imgKeys.length) < 0;
      } if (type === 'next') {
        return (activeIndex + imgKeys.length) >= previewImgs.value.length;
      }
    }

    const currentImageIndex = ref(0);
    const imageInterval = ref();
    function onOpenImgPreview(index) {
      currentImageIndex.value = index;
    }

    const autoPlayDisabled = computed(() => (currentImageIndex.value + imgKeys.length) >= previewImgs.value.length);

    function startAutoPlayImg() {
      imageInterval.value = setInterval(() => {
        if (!autoPlayDisabled.value) {
          currentImageIndex.value += imgKeys.length;
          setActiveItemFunc(currentImageIndex.value);
        } else {
          stopAutoPlayImg();
        }
      }, 1000);
    }
    function stopAutoPlayImg() {
      clearInterval(imageInterval.value);
      imageInterval.value = null;
    }
    onUnmounted(() => {
      stopAutoPlayImg();
    });

    /** 获取详细信息 */
    async function getDetail(id) {
      return await customRequest({
        url: '/api/image/entity',
        method: 'get',
        params: { image_id: id },
      }).then((res) => {
        if (res.code === 0) {
          return res.data.image;
        }
        ElMessage.error(res.msg || '获取数据失败');
        throw new Error(res.msg || '获取数据失败');
      });
    }

    /** 检测文本 */
    /** 预览 */
    async function openPreview(row) {
      jsonViewDialog.title = row.file_name;
      const data = await getDetail(row.id);
      if (data.rect_location) {
        jsonViewDialog.value = JSON.parse(data.rect_location);
        jsonViewDialog.visible = true;
      } else {
        ElMessage.error('没有数据');
      }
    }

    /** 下载 */
    async function handleDownload(row) {
      const data = await getDetail(row.id);
      if (data) {
        downloadByData(
          JSON.stringify(JSON.parse(data.rect_location), null, 2),
          `${
            data.file_name.split('.').slice(0, -1)
              .join('.')
          }.json`,
        );
      } else {
        ElMessage.error('没有数据');
      }
    }

    /** 识别 */
    function imgRecognition(id, discern) {
      customRequest({
        url: '/api/image/ai_sign',
        method: 'post',
        data: { project_id: route.meta.value, image_id: id, discern },
      })
        .then((res) => {
          if (res.code === 0) {
            this.$message.success(res.msg || '操作成功');
          }
        })
        .catch((err) => {
          console.log(`lqa_check 接口调用失败: ${err}`);
        });
    }

    /** 批量审核 */
    async function batchAudit(ids, reviewed) {
      await customRequest({
        url: '/api/image/list',
        method: 'patch',
        data: { reviewed, ids },
      }).then((res) => {
        if (res.code === 0) {
          ElMessage.success('操作成功');
          clearRefresh();
        }
      });
    }

    /** 批量删除 */
    async function batchDelete(ids) {
      await customRequest({
        url: '/api/image/entity',
        method: 'delete',
        data: {
          project_id: route.meta.value,
          image_ids: ids,
        },
      }).then((res) => {
        if (res.code === 0) {
          ElMessage.success('操作成功');
          clearRefresh();
        }
      });
    }

    /** 任务全量识别 */
    const recognizeDialogVisible = ref(false);

    /** 清除选中并刷新 */
    function clearRefresh() {
      selectedIds.value = [];
      crudExpose.getTableRef().tableRef.clearSelection();
      crudExpose.doRefresh();
    }

    return {
      downloadByUrl,
      imagePageDisable,
      pageData,
      previewImgs,
      imgKeys,
      imgPrefix,
      crudBinding,
      crudRef,
      jsonViewDialog,
      currentImageIndex,
      autoPlayDisabled,
      startAutoPlayImg,
      imageInterval,
      onOpenImgPreview,
      stopAutoPlayImg,
      batchAudit,
      batchDelete,
      openPreview,
      handleDownload,
      navigateToData,
      isNumeric,
      formWrapperRef,
      selectedIds,
      imgRecognition,
      recognizeDialogVisible,
      doRefresh: crudExpose.doRefresh,
    };
  },
});
</script>

<style scoped>
a {
  color: rgb(9, 160, 241);
}
a:hover {
  cursor: pointer;
}
</style>
