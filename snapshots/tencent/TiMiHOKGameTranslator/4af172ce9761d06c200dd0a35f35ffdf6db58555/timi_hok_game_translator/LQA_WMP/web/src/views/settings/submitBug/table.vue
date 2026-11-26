<!--
 * @Description: 处理人配置
-->
<template>
  <div style="height: calc(100vh - 356px)">
    <fs-crud ref="crudRef" v-bind="crudBinding" />
  </div>
</template>

<script>
import { defineComponent, watch } from 'vue';
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.jsx';
import { useRoute } from 'vue-router';

export default defineComponent({
  name: 'confTable',
  props: {
    form: { required: true },
    data: { type: Array, default: () => [] },
  },
  emits: ['refresh'],
  setup(props, { emit }) {
    const route = useRoute();
    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose } = useFs({
      createCrudOptions, context: { props, emit, project_id: route.meta.value, refresh: () => emit('refresh') },
    });
    crudExpose.doRefresh = () => emit('refresh');

    crudBinding.value.data = [];

    /** 监听数据变化进行覆盖 */
    watch(
      () => props.data,
      () => {
        crudBinding.value.data = props.data;
      },
    );

    return {
      crudBinding,
      crudRef,
    };
  },
});
</script>
