<!--
 * @Description: 执行信息
-->
<template>
  <div class="mb-2.75 mt-0.5">
    <el-tabs type="border-card">
      <el-tab-pane label="编辑器">
        <el-table class="mt-3.5" :data="data.list || []" style="width: 100%">
          <el-table-column prop="execute_pc" label="执行机器" min-width="180" />
          <!-- 执行语言 -->
          <el-table-column prop="language" label="执行语言" min-width="130">
            <template #default="scope">
              <fs-values-format
                class="cursor-pointer"
                :model-value="scope.row[scope.column.property]"
                :dict="languageDict"
              />
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" />
          <el-table-column prop="editor_nums" label="运行编辑器数" align="right" />
        </el-table>
      </el-tab-pane>
      <el-tab-pane label="执行进度">
        <div class="bg-gray-50 py-3 px-6 leading-[32px]">
          <div>当前上报数据： {{ info.all_data_count }}</div>
          <div>已还原识别数据：{{ info.all_imaged_count }}</div>
        </div>
        <el-table class="mt-3.5" :data="languages || []" style="width: 100%" v-loading="loading">
          <!-- 执行语言 -->
          <el-table-column prop="language" label="执行语言" min-width="130">
            <template #default="scope">
              <fs-values-format
                class="cursor-pointer"
                :model-value="scope.row[scope.column.property]"
                :dict="languageDict"
              />
            </template>
          </el-table-column>
          <el-table-column prop="imaged_count" align="center" label="已还原识别数据">
            <template #default="scope">
              {{ scope.row.imaged_count }}
              <el-divider direction="vertical" />
              {{ scope.row.imaged_count_per }}
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script>
import { customRequest } from '@/utils/service.ts';
export default {
  name: 'runInfo',
  props: {
    data: { type: Object, required: true },
    languageDict: { type: Object, required: true },
  },
  data() {
    return {
      languages: [],
      info: {
        all_data_count: 0,
        all_imaged_count: 0,
      },
      languages: [],
      loading: false,
    };
  },
  created() {
    this.getData();
  },
  methods: {
    async getData() {
      this.loading = true;
      const { data } = await customRequest({ url: '/api/job/progress', method: 'get', params: { job_id: this.data.id } });
      this.info = data;
      this.languages = data.languges;
      this.loading = false;
    },
  },
};
</script>
