<!--
 * @Description: 图片还原配置
-->
<template>
  <fs-crud ref="crudRef" v-bind="crudBinding">
    <template #cell_$expand="scope">
      <lang-path-table
        v-model="scope.row.lang_path"
        :project-id="$route.meta.value" :add="false" :remove="false"
        :disabled="true"
      />
    </template>
  </fs-crud>
</template>

<script>
import { defineComponent, ref, nextTick } from 'vue';
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.jsx';
import langPathTable from './langPathTable.vue';
import { customRequest } from '@/utils/service.ts';
import { useRoute } from 'vue-router';

export default defineComponent({
  name: 'ImgTransform',
  components: { langPathTable },
  setup() {
    const route = useRoute();
    // fs-crud 初始化
    const { crudRef, crudBinding, crudExpose } = useFs({ createCrudOptions, context: { project_id: route.meta.value } });

    crudBinding.value.data = [];

    const initializedData = ref(false);

    /** 获取最新数据 */
    function getData() {
      initializedData.value = false;
      customRequest({
        url: '/api/project/config',
        method: 'get',
        params: { project_id: route.meta.value, cate: 'ImgRevert' },
      }).then((res) => {
        crudBinding.value.data = res.data.list;
        nextTick(() => {
          initializedData.value = true;
        });
      });
    }

    /* 初始化获取 */
    getData();

    // watch(
    //   () => crudBinding.value.data,
    //   async () => {
    //     if (initializedData.value) {
    //       initializedData.value = false;

    //       /* 数据预处理、写入序号 */
    //       configData.value.content.forEach((item, index) => {
    //         item.no = index + 1;
    //         item.rows.forEach((row, rowIndex) => {
    //           row.no = rowIndex + 1;
    //         });
    //       });

    //       /* 更新写入 */
    //       const res = await customRequest({
    //         url: '/api/project/config',
    //         method: 'post',
    //         data: configData.value,
    //       });

    //       /* 数据刷新 */
    //       // configData.value = res.data.config;
    //       crudBinding.value.data = res.data.list;
    //       await nextTick();
    //       initializedData.value = true;
    //     }
    //   },
    //   { deep: true },
    // );

    crudExpose.doRefresh = getData;

    return {
      crudBinding,
      crudRef,
    };
  },
});

</script>
