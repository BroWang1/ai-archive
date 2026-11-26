<script lang="ts" setup>
import { useTagsViewStore } from '@/store/modules/tags-view';
import { useSettingsStore } from '@/store/modules/settings';
import Footer from './Footer/index.vue';
import { h, type Component } from 'vue';
import { RouteLocationNormalizedLoaded } from 'vue-router';

const tagsViewStore = useTagsViewStore();
const settingsStore = useSettingsStore();

// 用来存已经创建的组件
const wrapperMap = new Map();
// 将router传个我们的组件重新换一个新的组件，原组件包里面
function formatComponentInstance(component: Component, route: RouteLocationNormalizedLoaded) {
  let wrapper;
  if (component) {
    const wrapperName = route.name;
    if (wrapperMap.has(wrapperName)) {
      wrapper = wrapperMap.get(wrapperName);
    } else {
      wrapper = {
        name: wrapperName,
        render() {
          return h(component);
        },
      };
      wrapperMap.set(wrapperName, wrapper);
    }
    return h(wrapper);
  }
}
</script>

<template>
  <section class="app-main">
    <div class="app-scrollbar">
      <!-- key 采用 route.path 和 route.fullPath 有着不同的效果，大多数时候 path 更通用 -->
      <router-view v-slot="{ Component, route }">
        <transition name="el-fade-in" mode="out-in">
          <keep-alive :include="tagsViewStore.cachedViews">
            <component
              :is="formatComponentInstance(Component, route)" :key="route.fullPath"
              class="app-container-grow"
            />
          </keep-alive>
        </transition>
      </router-view>
      <!-- 页脚 -->
      <Footer v-if="settingsStore.showFooter" />
    </div>
    <!-- 返回顶部 -->
    <el-backtop />
    <!-- 返回顶部（固定 Header 情况下） -->
    <el-backtop target=".app-scrollbar" />
  </section>
</template>

<style lang="scss" scoped>
@import "@/styles/mixins.scss";

.app-main {
  width: 100%;
  display: flex;
}

.app-scrollbar {
  flex-grow: 1;
  overflow: auto;
  @extend %scrollbar;
  display: flex;
  flex-direction: column;
  .app-container-grow {
    flex-grow: 1;
  }
}
</style>
