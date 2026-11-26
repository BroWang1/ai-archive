<!--
 * @Description: 全量识别弹窗
-->
<template>
  <el-dialog
    title="全量识别" width="366px"
    :model-value="modelValue" @update:model-value="val => $emit('update:model-value', val)"
    @close="$emit('update:model-value', false)"
  >
    <el-form class="mb-6" :model="form" label-position="top">
      <el-form-item label="区域语言">
        <template #label>
          <div @click.prevent>区域语言</div>
        </template>
        <el-select v-model="form.languages" multiple placeholder="默认为任务的全部语言" clearable>
          <el-option v-for="item in options.languages" :key="item.value" v-bind="item" />
        </el-select>
      </el-form-item>
    </el-form>
    <div slot="footer" class="flex justify-end">
      <el-button @click="$emit('update:model-value', false)">取 消</el-button>
      <el-button type="primary" :loading="loading" @click="jobRecognize">确 定</el-button>
    </div>
  </el-dialog>
</template>

<script>
import { customRequest } from '@/utils/service.ts';
import { ElMessage } from 'element-plus';

export default {
  name: 'recognizeDialog',
  props: {
    modelValue: { type: Boolean, required: true },
    projectId: { type: Number, required: true },
    jobId: { type: Number, required: true },
  },
  emits: ['refresh', 'update:model-value'],
  data() {
    return {
      form: { languages: [] },
      options: {
        languages: [],
      },
      loading: false,
    };
  },
  watch: {
    modelValue(val) {
      if (!val) {
        this.form.languages = [];
      }
    },
  },
  async created() {
    // 获取任务详情
    const jobRes = await customRequest({
      url: '/api/job/entity',
      method: 'get',
      params: { job_id: this.jobId, progress: 1 },
    });
    // 获取项目区域语言配置
    const res = await customRequest({
      url: '/api/project/config',
      method: 'get',
      params: { project_id: this.projectId, cate: 'Language' },
    });
    res.data.list.sort((a, b) => a.value - b.value);
    // 过滤任务包含的语言
    this.options.languages = res.data.list.filter((
      item => jobRes.data.job.languages.includes(item.value)
    ));
  },
  methods: {
    /** 执行全量识别 */
    async jobRecognize() {
      this.loading = true;
      await customRequest({
        url: '/api/image/ai_sign',
        method: 'post',
        data: {
          project_id: this.projectId,
          job_id: this.jobId,
          discern: 0,
          languages: this.form.languages,
        },
      }).then(() => {
        this.form.languages = [];
        this.$emit('update:model-value', false);
      })
        .finally(() => {
          this.loading = false;
        });
      ElMessage.success('操作成功');
      this.$emit('refresh');
    },
  },
};
</script>
