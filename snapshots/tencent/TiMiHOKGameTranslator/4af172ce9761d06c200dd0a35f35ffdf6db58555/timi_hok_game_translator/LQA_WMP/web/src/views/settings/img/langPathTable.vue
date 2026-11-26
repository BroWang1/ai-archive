<!--
 * @Description: 翻译配置
-->
<template>
  <sc-form-table
    :model-value="modelValue"
    v-bind="$attrs"
    @update:model-value="(val) => $emit('update:modelValue', val)"
  >
    <!-- 语言 -->
    <el-table-column prop="code_raw" label="语言">
      <template #default="scope">
        <el-select v-model="scope.row.code_raw" :disabled="disabled" placeholder="请选择语言">
          <el-option v-for="item in langCodeOptions" :key="item.value" v-bind="item" :value="item.name" />
        </el-select>
      </template>
    </el-table-column>

    <!-- 列名 -->
    <el-table-column prop="code" label="列名">
      <template #default="scope">
        <el-input v-model="scope.row.code" :disabled="disabled" placeholder="请输入列名" />
      </template>
    </el-table-column>

    <!-- 配置路径 -->
    <el-table-column prop="filePath" label="配置路径">
      <template #default="scope">
        <el-input v-model="scope.row.filePath" :disabled="disabled" placeholder="请输入配置路径" />
        <div
          v-if="scope.row.filePath && !isValidPath(scope.row.filePath)"
          class="lang-path-error-tip"
        >
          路径格式不合法
        </div>
      </template>
    </el-table-column>
  </sc-form-table>
</template>

<script>
import { customRequest } from '@/utils/service';
import { isValidPath } from '@/utils/validate';

export default {
  name: 'langPathTable',
  emits: ['update:modelValue'],
  props: {
    modelValue: { type: Array, default: () => [] },
    disabled: { type: Boolean, default: false },
    projectId: { type: [Number, String] },
  },
  data() {
    return {
      langCodeOptions: [],
    };
  },
  watch: {
    projectId: {
      handler(val) {
        if (val) {
          // 获取语言映射
          customRequest({
            url: '/api/project/config',
            method: 'get',
            params: { project_id: this.$route.meta.value, cate: 'Language' },
          }).then((res) => {
            // this.langCodeOptions = res.data.list.filter(item => item.enable);
            this.langCodeOptions = res.data.list;
            this.langCodeOptions.sort((a, b) => a.value - b.value);
          });
        }
      },
      immediate: true,
    },
  },
  methods: {
    /** 透传到公共校验工具（供模板中 this.isValidPath 使用） */
    isValidPath,
  },
};
</script>

<style lang="scss" scoped>
.lang-path-error-tip {
  color: var(--el-color-danger, #f56c6c);
  font-size: 12px;
  line-height: 1;
  padding-top: 4px;
}
</style>
