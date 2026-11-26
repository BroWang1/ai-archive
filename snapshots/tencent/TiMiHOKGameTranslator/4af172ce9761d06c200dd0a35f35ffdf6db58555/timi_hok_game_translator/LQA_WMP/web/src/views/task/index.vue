<!--
 * @Description: 任务管理
-->
<template>
  <div class="app-container !pt-4.25 bg-white">
    <fs-crud ref="crudRef" v-bind="crudBinding">
      <!-- 操作按钮 -->
      <template #actionbar-right>
        <!-- 创建任务 -->
        <el-button type="primary" @click="openRunTask" icon="Plus">添加</el-button>
      </template>

      <!-- 状态 - 失败展示错误描述 -->
      <template #cell_status="scope">
        <el-popover v-if="scope.row.reason" :content="scope.row.reason" width="80vw">
<!--          <div class="whitespace-pre-line">{{ scope.row.reason }}</div>-->
          <template #reference>
            <fs-values-format :model-value="scope.row.status" :dict="statusDict" color="auto" :auto-effects="['plain']" />
          </template>
        </el-popover>
        <fs-values-format v-else :model-value="scope.row.status" :dict="statusDict" color="auto" :auto-effects="['plain']" />
      </template>
    </fs-crud>

    <!-- 执行任务表单 -->
    <fs-form-wrapper ref="runTaskFormWrapperRef">
      <!-- 项目资源 -->
      <template #form_project_resource="scope">
        <project-resource
          ref="projectSourceRef" v-model="scope.form.project_resource"
          :disabled="scope.attrs.disabled"
        />
      </template>

      <!-- 译文资源 -->
      <template #form_translate_resource="scope">
        <translate-resource
          ref="translateResourceRef"
          v-model="scope.form.translate_resource" :disabled="scope.attrs.disabled"
        />
      </template>
    </fs-form-wrapper>

    <!-- 任务追加数据表单 -->
    <fs-form-wrapper ref="runningTaskAddFormWrapperRef" />

    <!-- 执行信息弹窗 -->
    <el-dialog
      v-model="progressDialog.visible"
      :title="`${progressDialog.form.id} - ${progressDialog.form.name} 执行信息`"
      width="1000"
      destroy-on-close
    >
      <run-info-area :data="progressDialog.form" :language-dict="languageDict" v-if='progressDialog.visible' />
    </el-dialog>
  </div>
</template>

<script>
import { defineComponent, onMounted, reactive, ref } from 'vue';
import { dict, useColumns, useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.js';
import createRunTaskCrudOptions from './runTask/crud.jsx';
import runningTaskAddCrudOptions from './runningAdd/crud.jsx';
import { customRequest } from '@/utils/service.ts';
import { useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import projectResource from './runTask/projectResource.vue';
import translateResource from './runTask/translateResource.vue';
import { getLanguageDict } from '@/utils/dict.js';
import { getTrackerMeta, toBugFormOptions } from '@/utils/tracker.js';
import runInfoArea from './runTask/info.vue';

export default defineComponent({
  name: 'Task',
  components: { projectResource, translateResource, runInfoArea },
  setup() {
    const route = useRoute();
    const projectSourceRef = ref();
    const translateResourceRef = ref();
    const statusDict = dict({
      url: '/api/system/enums/job_status',
    });

    /** 执行信息 */
    const progressDialog = reactive({
      visible: false,
      form: {},
    });
    async function openProgress({ row }) {
      const infoData = await customRequest({ url: '/api/job/device', method: 'get', params: { job_id: row.id } });
      progressDialog.form = { ...row, ...infoData.data };
      progressDialog.visible = true;
    }

    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose } = useFs({
      createCrudOptions, context: { statusDict, openViewTask, openEditTask, openProgress },
    });


    const { buildFormOptions } = useColumns();

    const runTaskFormWrapperRef = ref();
    const runningTaskAddFormWrapperRef = ref();
    const bugParams = ref({});
    const bugOptions = ref({});
    const trackerMeta = ref({ type: 'none' });
    const languageDict = getLanguageDict(route.meta.value);

    /** 创建任务 */
    function openRunTask() {
      const formOptions = buildFormOptions((
        createRunTaskCrudOptions({
          route, trackerMeta, bugOptions, doRefresh: crudExpose.doRefresh, projectSourceRef, translateResourceRef, crudExpose,
        })
      ));
      formOptions.initialForm = {
        sign_bug_types: [], // 识别缺陷类型

        // 测试数据
        data_ds: [],

        // bug 参数
        ...bugParams.value,
        bill_bug_types: [],
        severity: 3, // 一般
        priority: 3, // 中

        // dataSource: selectedIds.value.length ? 'select' : 'filter',
        // dataSource: 'filter',
      };
      runTaskFormWrapperRef.value.open(formOptions);
    }

    /** 编辑任务 */
    async function openEditTask({ row }) {
      if (row.status === 1) {
        // 未执行 - 编辑
        const formOptions = buildFormOptions((
          createRunTaskCrudOptions({
            route, trackerMeta, bugOptions, doRefresh: crudExpose.doRefresh, projectSourceRef, translateResourceRef,
          })
        ));
        formOptions.initialForm = await customRequest({
          url: '/api/job/entity',
          method: 'get',
          params: { job_id: row.id, progress: 1 },
        }).then(res => ({ ...row, ...res.data.job }));
        // 修改标题
        formOptions.wrapper.title = `${row.id} - ${row.name}`;
        runTaskFormWrapperRef.value.open(formOptions);
      } else if (row.status === 2) {
        // 执行中 - 追加
        const res = await customRequest({
          url: '/api/job/entity',
          method: 'get',
          params: { job_id: row.id, progress: 1 },
        });
        const formOptions = buildFormOptions((
          runningTaskAddCrudOptions({
            route,
            doRefresh: crudExpose.doRefresh,
            selectedLanguages: res.data.job.languages || [],
            selectedDataIds: res.data.job.data_ids || [],
          })
        ));
        formOptions.initialForm = {
          ...row,
          ...res.data.job,
          languages: [], // 语言
          data_ids: [], // 数据添加
        };
        formOptions.wrapper.title = `${row.id} - ${row.name}`;
        runningTaskAddFormWrapperRef.value.open(formOptions);
      }
    }

    /** 查看任务 */
    async function openViewTask({ row }) {
      const formOptions = buildFormOptions((
        createRunTaskCrudOptions({
          route, trackerMeta, bugOptions, doRefresh: crudExpose.doRefresh, projectSourceRef, translateResourceRef,
        })
      ));
      const res = await customRequest({
        url: '/api/job/entity',
        method: 'get',
        params: { job_id: row.id, progress: 1 },
      }).then(res => ({ ...row, ...res.data.job }));
      formOptions.initialForm = res;

      /* 详情操作 */
      // 禁用处理
      formOptions.disabled = true;
      // 加字段
      const addViewKeys = [
        'id', 'status', 'bug_num', 'is_parent', 'regress_num', 'creator_id', // 基础信息
      ];
      addViewKeys.forEach((key) => {
        formOptions.columns[key] = crudBinding.value.viewForm.columns[key];
      });
      formOptions.group.groups.basic.columns = [
        'discern', 'id',  'name', 'status', 'plan_time', 'bug_num', 'is_parent', 'creator_id', 'regress_num',
        'languages', 'sign_bug_types', 'ocr_detect',
      ];
      // 修改标题
      formOptions.wrapper.title = '查看';
      // 隐藏按钮
      Object.values(formOptions.wrapper.buttons).forEach((temp) => {
        temp.show = false;
      });
      runTaskFormWrapperRef.value.open(formOptions);
    }

    onMounted(async () => {
      // 页面打开后立即加载列表数据
      await crudExpose.doRefresh();

      // 缺陷系统提单选项（发现版本/修复版本/发布计划）
      const meta = await getTrackerMeta(route.meta.value);
      trackerMeta.value = meta;
      if (meta.error) {
        ElMessage.warning(`缺陷系统配置有误，自动提单可能失败：${meta.error}`);
      }
      const { params, options } = toBugFormOptions(meta);
      bugParams.value = params;
      bugOptions.value = options;
    });

    return {
      statusDict,
      crudBinding,
      crudRef,
      progressDialog,
      runTaskFormWrapperRef,
      runningTaskAddFormWrapperRef,
      languageDict,
      openRunTask,
      projectSourceRef,
      translateResourceRef,
    };
  },
});
</script>
