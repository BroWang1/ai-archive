<script lang="ts" setup>
import { computed, onMounted, ref } from 'vue';
import { storeToRefs } from 'pinia';
import { useAppStore } from '@/store/modules/app';
import { useSettingsStore } from '@/store/modules/settings';
import { AppMain, NavigationBar, Sidebar, TagsView, Logo } from './components';
import { customRequest } from '@/utils/service';
import dayjs from 'dayjs';

const appStore = useAppStore();
const settingsStore = useSettingsStore();
const { showTagsView, showLogo } = storeToRefs(settingsStore);

/** 定义计算属性 layoutClasses，用于控制布局的类名 */
const layoutClasses = computed(() => ({
  hideSidebar: !appStore.sidebar.opened,
}));

const announcement = ref('');
onMounted(async () => {
  // 公告先不搞
  // const { data } = await customRequest<{data: any[]}>({
  //   url: '/system/setting/announcement',
  //   method: 'get',
  // });
  // for (let i = 0; i < data.length; i++) {
  //   if (dayjs() > dayjs(data[i].start_time) && dayjs() < dayjs(data[i].end_time)) {
  //     announcement.value = data[i].info;
  //     return;
  //   }
  // }
});
</script>

<template>
  <div :class="layoutClasses" class="app-wrapper">
    <!-- 头部导航栏和标签栏 -->
    <div class="fixed-header layout-header">
      <Logo v-if="showLogo" :collapse="false" class="logo" />
      <div class="content">
        <NavigationBar />
        <TagsView v-show="showTagsView" />
      </div>
    </div>

    <!-- 主容器 -->
    <div :class="{ hasTagsView: showTagsView }" class="main-container">
      <!-- 系统公告 -->
      <div
        v-if="announcement"
        class="fixed px-6.5 top-[82px] text-white text-[14px] py-1.5 w-full opacity-95"
        style="z-index: 1002; background-color:var(--el-color-primary);"
      >
        {{announcement}}
      </div>
      <!-- 左侧边栏 -->
      <Sidebar class="sidebar-container" />
      <!-- 页面主体内容 -->
      <AppMain class="app-main" />
    </div>
  </div>
</template>

<style lang="scss" scoped>
@import "@/styles/mixins.scss";
$transition-time: 0.35s;

.app-wrapper {
  @extend %clearfix;
  width: 100%;
}

.fixed-header {
  position: fixed;
  top: 0;
  z-index: 1002;
  width: 100%;
  display: flex;
  .logo {
    width: var(--v3-sidebar-width);
  }
  .content {
    flex: 1;
    position: relative;
  }
}

.layout-header {
  background-color: var(--v3-header-bg-color);
  box-shadow: var(--v3-header-box-shadow);
  border-bottom: var(--v3-header-border-bottom);
}

.main-container {
  min-height: 100%;
}

.sidebar-container {
  transition: width $transition-time;
  width: var(--v3-sidebar-width) !important;
  height: 100%;
  position: fixed;
  left: 0;
  z-index: 1001;
  overflow: hidden;
  border-right: var(--v3-sidebar-border-right);
  padding-top: var(--v3-navigationbar-height);
}

.app-main {
  transition: padding-left $transition-time;
  padding-top: var(--v3-navigationbar-height);
  padding-left: var(--v3-sidebar-width);
  height: 100vh;
  overflow: auto;
}

.hideSidebar {
  .sidebar-container {
    width: var(--v3-sidebar-hide-width) !important;
  }
  .app-main {
    padding-left: var(--v3-sidebar-hide-width);
  }
}

.hasTagsView {
  .sidebar-container {
    padding-top: var(--v3-header-height);
  }
  .app-main {
    padding-top: var(--v3-header-height);
  }
}
</style>
