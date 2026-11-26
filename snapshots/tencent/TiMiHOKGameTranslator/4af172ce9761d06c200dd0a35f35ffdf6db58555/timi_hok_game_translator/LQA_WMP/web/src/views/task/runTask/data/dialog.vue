<script setup>
import { useFs } from '@fast-crud/fast-crud';
import createCrudOptions from './crud.jsx';
import { watch } from 'vue';

const props = defineProps({
  visible: { type: Boolean, required: true },
  selectedIds: { type: Array, required: true },
});

const emit = defineEmits(['update:visible', 'update:selectedIds']);

// fs-crud 初始化
const { crudRef, crudBinding, crudExpose } = useFs({
  createCrudOptions,
  context: {
    selectedIds: props.selectedIds,
    emit,
  },
});

watch(
  () => props.visible,
  (val) => {
    if (val) {
      // 打开弹窗后刷新列表数据
      crudExpose.doRefresh();
    }
  },
);
</script>

<template>
  <el-dialog
    title="数据补充"
    append-to-body
    :model-value="visible" @update:visible="(e) => emit('update:visible', e)"
    @close="emit('update:visible', false)"
    top="10vh"
    width="64%"
  >
    <div style="height: 75vh;">
      <fs-crud ref="crudRef" v-bind="crudBinding">
        <!-- 操作按钮 -->
        <template #actionbar-right>
          <!-- 已选 n 个 -->
          <template v-if="selectedIds.length">
            <el-tag size="large" type="info" >
              已选 <span style="font-weight: bold">{{selectedIds.length}}</span> 个
            </el-tag>
          </template>
        </template>
      </fs-crud>
    </div>
  </el-dialog>
</template>
