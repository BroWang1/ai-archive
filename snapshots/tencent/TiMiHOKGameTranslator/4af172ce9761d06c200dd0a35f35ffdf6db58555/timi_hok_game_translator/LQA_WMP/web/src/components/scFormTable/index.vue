<!--
 * @Descripttion: 表单表格
 * @version: 1.1
 * @Author: sakuya
-->
<template>
  <div
    ref="scFormTable"
    class="sc-form-table"
    :class="{'has-add': add}"
  >
    <el-table ref="table" :data="data" border stripe>
      <el-table-column type="index" width="50" fixed="left">
        <template #header>
          <el-button v-if="add" type="primary" icon="Plus" size="small" circle @click="rowAdd" />
        </template>
        <template #default="scope">
          <div class="sc-form-table-handle">
            <span>{{ scope.$index + 1 }}</span>
            <el-button
              v-if="remove || scope.row.canRemove" plain circle type="danger" icon="Delete" size="small"
              @click="rowDel(scope.row, scope.$index)"
            />
          </div>
        </template>
      </el-table-column>
      <el-table-column v-if="dragSort" label="" width="50">
        <template #default>
          <div class="move" style="cursor: move;">
            <el-icon><DCaret /></el-icon>
          </div>
        </template>
      </el-table-column>
      <slot />
      <template #empty>
        {{ placeholder }}
      </template>
    </el-table>
  </div>
</template>

<script>
import Sortable from 'sortablejs';

export default {
  props: {
    add: { type: Boolean, default: true },
    remove: { type: Boolean, default: true },
    modelValue: { type: Array, default: () => [] },
    addTemplate: { type: Object, default: () => {} },
    placeholder: { type: String, default: '暂无数据' },
    dragSort: { type: Boolean, default: false },
  },
  data() {
    return {
      data: [],
    };
  },
  watch: {
    modelValue() {
      this.data = this.modelValue;
    },
    data: {
      handler() {
        this.$emit('update:modelValue', this.data);
      },
      deep: true,
    },
  },
  mounted() {
    this.data = this.modelValue || [];
    if (this.dragSort) {
      this.rowDrop();
    }
  },
  methods: {
    rowDrop() {
      // eslint-disable-next-line @typescript-eslint/no-this-alias
      const that = this;
      const tbody = this.$refs.table.$el.querySelector('.el-table__body-wrapper tbody');
      Sortable.create(tbody, {
        handle: '.move',
        animation: 300,
        ghostClass: 'ghost',
        onEnd({ newIndex, oldIndex }) {
          that.data.splice(newIndex, 0, that.data.splice(oldIndex, 1)[0]);
          const newArray = that.data.slice(0);
          const tmpHeight = that.$refs.scFormTable.offsetHeight;
          that.$refs.scFormTable.style.setProperty('height', `${tmpHeight}px`);
          that.data = [];
          that.$nextTick(() => {
            that.data = newArray;
            that.$nextTick(() => {
              that.$refs.scFormTable.style.removeProperty('height');
            });
          });
        },
      });
    },
    rowAdd() {
      const temp = JSON.parse(JSON.stringify(this.addTemplate));
      this.data.push(temp);
    },
    rowDel(row, index) {
      this.data.splice(index, 1);
    },
  },
};
</script>

<style scoped>
  .sc-form-table {width: 100%;}

  .sc-form-table .sc-form-table-handle {text-align: center;}

  .sc-form-table .sc-form-table-handle span {display: inline-block;}

  .sc-form-table .sc-form-table-handle button {display: none;}

  .sc-form-table.has-add .hover-row .sc-form-table-handle span {display: none;}

  .sc-form-table.has-add .hover-row .sc-form-table-handle button {display: inline-block;}

  .sc-form-table .move {text-align: center;font-size: 14px;margin-top: 3px;}
</style>
