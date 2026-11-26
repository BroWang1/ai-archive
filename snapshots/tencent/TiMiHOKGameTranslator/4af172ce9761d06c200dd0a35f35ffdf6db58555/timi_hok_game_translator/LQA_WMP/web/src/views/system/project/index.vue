<!--
 * @Description: 项目管理
-->
<template>
  <div class="app-container !pt-4.25 bg-white">
<!--    <el-card shadow="never" style="height: 100%" :body-style="{ height: '100%' }">-->
      <fs-crud ref="crudRef" v-bind="crudBinding" />
<!--    </el-card>-->
  </div>
</template>

<script>
import { defineComponent, onMounted } from 'vue';
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.ts';

export default defineComponent({
  name: 'Project',

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
