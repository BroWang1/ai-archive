<!--
 * @Description: 缺陷类型
-->
<template>
  <fs-crud ref="crudRef" v-bind="crudBinding" />
</template>

<script>
import { defineComponent, onMounted } from 'vue';
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.jsx';

export default defineComponent({
  name: 'bug',

  setup() {
    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose } = useFs({ createCrudOptions });

    onMounted(() => {
      // 页面打开后立即加载列表数据
      crudExpose.doRefresh();
    });

    return {
      crudBinding,
      crudRef,
    };
  },
});

</script>
<style lang="scss" scoped>
  :deep(.isError) {
    .el-input__wrapper {
       --el-input-border-color: red !important;
       --el-input-focus-border-color: red !important;
    }
  }
</style>
