<script lang="ts" setup>
const { VITE_APP_TITLE } = import.meta.env;
</script>

<template>
  <footer class="layout-footer">{{ VITE_APP_TITLE }} · 本地化质量检测平台</footer>
</template>

<style lang="scss" scoped>
.layout-footer {
  width: 100%;
  min-height: 50px;
  font-size: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--el-text-color-placeholder);
}
</style>
