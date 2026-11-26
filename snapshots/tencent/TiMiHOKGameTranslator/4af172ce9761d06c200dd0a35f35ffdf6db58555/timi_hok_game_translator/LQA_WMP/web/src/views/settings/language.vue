<!--
 * @Description: 区域语言
-->
<template>
  <el-table :max-height="tableMaxHeight" stripe :data="data" style="width: 100%">
    <el-table-column prop="label" label="名称" min-width="300" />
    <el-table-column prop="custom_label" label="自定义名称（提单用）" min-width="300">
      <template #default="scope">
        <el-input v-model.trim="scope.row.custom_label" placeholder="自定义名称" @change="(val) => handleChange(scope.row)" />
      </template>
    </el-table-column>
    <el-table-column prop="name" label="编码" min-width="300" />
    <el-table-column prop="enable" label="生效" min-width="300">
      <template #default="scope">
        <el-switch v-model="scope.row.enable" :active-value="1" :inactive-value="0" @change="(val) => handleChange(scope.row)" />
      </template>
    </el-table-column>
  </el-table>
</template>

<script>
import { customRequest } from '@/utils/service.ts';
import { ElMessage } from 'element-plus';

export default {
  name: 'language',
  data() {
    return {
      tableMaxHeight: 500,
      data: [],
    };
  },
  async created() {
    await this.getData();
  },
  mounted() {
    this.tableMaxHeight = window.innerHeight - 240;
  },
  methods: {
    /** 获取数据 */
    async getData() {
      const { data } = await customRequest({
        url: '/api/project/config',
        method: 'get',
        params: { project_id: this.$route.meta.value, cate: 'Language' },
      });
      await this.setData(data);
    },
    /** 设置数据 */
    async setData(data) {
      this.data = data.list;
      this.data.sort((a, b) => a.value - b.value);
      await this.$nextTick();
    },
    /** 生效改变 */
    async handleChange(data) {
      const res = await customRequest({
        url: '/api/project/config?cate=Language',
        method: 'patch',
        data,
      });
      ElMessage.success(res.msg);
      // 设置数据
      await this.getData();
    },
  },
};
</script>
