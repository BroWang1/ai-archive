<!--
 * @Description: 根据长度自动判断是否展示 popover
-->
<template>
  <div v-show="isEllipsis">
    <el-popover :width="width" placement="right" trigger="click" :content="value">
      <template #reference>
        <div ref="valueDom" title="点击查看" class="text-ellipsis of-hidden whitespace-nowrap">{{value}}</div>
      </template>
    </el-popover>
  </div>
  <div v-show="!isEllipsis">{{value}}</div>
</template>

<script>
export default {
  name: 'autoPopover',
  props: {
    width: { type: String, default: '50vw' },
    value: { type: String },
  },
  watch: {
    value: {
      handler() {
        this.$nextTick(() => {
          const { clientWidth } = this.$refs.valueDom;
          const { scrollWidth } = this.$refs.valueDom;
          this.isEllipsis = clientWidth < scrollWidth;
        });
      },
      immediate: true,
    },
  },
  data() {
    return {
      isEllipsis: true,
    };
  },
  methods: {

  },
};
</script>
