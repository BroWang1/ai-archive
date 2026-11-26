<!--
 * @Description: 区域语言
-->
<template>
  <fs-crud ref="crudRef" v-bind="crudBinding" />
</template>

<script>
import { defineComponent, onMounted } from 'vue';
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.js';

export default defineComponent({
  name: 'language',

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
