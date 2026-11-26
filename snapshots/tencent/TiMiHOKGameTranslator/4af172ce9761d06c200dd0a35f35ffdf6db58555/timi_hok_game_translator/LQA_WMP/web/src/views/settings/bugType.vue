<!--
 * @Description: 缺陷类型
-->
<template>
  <el-table :max-height="tableMaxHeight" stripe :data="data" style="width: 100%">
    <el-table-column prop="label" label="名称" min-width="300" />
    <el-table-column prop="name" label="编码" min-width="300" />
    <el-table-column prop="enable" label="生效" min-width="300">
      <template #default="scope">
        <el-switch v-model="scope.row.enable" :active-value="1" :inactive-value="0" @change="(val) => edit(scope.row)" />
      </template>
    </el-table-column>
    <el-table-column label="匹配标识" min-width="300">
      <template #default="scope">
        <el-input v-model="scope.row.show_trans_marks" placeholder="请输入匹配标识" @blur="loseFocus(scope.row)" v-if="[1, 5].includes(scope.row.value)" :class="{'isError': !isJson(scope.row.show_trans_marks)}"></el-input>
      </template>
    </el-table-column>
  </el-table>
</template>

<script>
import { customRequest } from '@/utils/service.ts';
import { ElMessage } from 'element-plus';

export default {
  name: 'bugType',
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
        params: { project_id: this.$route.meta.value, cate: 'BugType' },
      });
      await this.setData(data);
    },
    /** 设置数据 */
    async setData(data) {
      this.data = data.list;
      this.data = this.data.map(item => ({
        ...item,
        show_trans_marks: item.trans_marks || '',
      }));
      await this.$nextTick();
    },
    loseFocus(data) {
      if (data.trans_marks !== data.show_trans_marks) {
        data.trans_marks = data.show_trans_marks;
        delete data.show_trans_marks;
        this.edit(data);
      }
    },
    // 编辑
    async edit(data) {
      const { trans_marks } = data;
      const flag = this.isJson(trans_marks);
      if (flag) {
        customRequest({
          url: '/api/project/config?cate=BugType',
          method: 'patch',
          data: {
            ...data,
            // eslint-disable-next-line camelcase
            trans_marks: trans_marks ? trans_marks : '[]',
          },
        }).then(async (res) => {
          ElMessage.success(res.msg);
          await this.getData(); // 设置数据
        })
          .finally(() => {
            data.show_trans_marks = data.trans_marks;
          });
      } else {
        data.show_trans_marks = data.trans_marks;
        ElMessage.error('匹配标识格式有误，仅支持字符串数组，请重新输入！');
      }
    },
    isJson(str) {
      if (!str) return true;
      try {
        const arr = JSON.parse(str);
        return Array.isArray(arr);
      } catch (e) {
        return false;
      }
    },
  },
};
</script>

<style lang="scss" scoped>
  :deep(.isError) {
    .el-input__wrapper {
       --el-input-border-color: red !important;
       --el-input-focus-border-color: red !important;
    }
  }
</style>
