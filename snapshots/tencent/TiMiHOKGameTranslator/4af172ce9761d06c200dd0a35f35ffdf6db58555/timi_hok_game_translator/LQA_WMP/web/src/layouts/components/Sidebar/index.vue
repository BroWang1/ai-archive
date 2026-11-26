<script lang="ts" setup>
import { computed, ref, watch, onMounted, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAppStore } from '@/store/modules/app';
import { usePermissionStore } from '@/store/modules/permission';
import { useSettingsStore } from '@/store/modules/settings';
import SidebarItem from './SidebarItem.vue';
import Logo from '../Logo/index.vue';
import { useDevice } from '@/hooks/useDevice';
import { useLayoutMode } from '@/hooks/useLayoutMode';
import { getCssVariableValue } from '@/utils';
import { useUserStoreHook } from '@/store/modules/user';
import { SUPER_ADMIN_PROJECT_ID } from '@/constants/app-key';
import { customRequest } from '@/utils/service';

const v3SidebarMenuBgColor = getCssVariableValue('--v3-sidebar-menu-bg-color');
const v3SidebarMenuTextColor = getCssVariableValue('--v3-sidebar-menu-text-color');
const v3SidebarMenuActiveTextColor = getCssVariableValue('--v3-sidebar-menu-active-text-color');
const userStore = useUserStoreHook();
const { superAdmin, projects } = userStore;

const parentGroups = ref<any[]>([]);
if (superAdmin) {
  parentGroups.value.push({
    label: '系统',
    value: 'system',
    options: [{ label: '系统管理', value: SUPER_ADMIN_PROJECT_ID }],
  });
}
parentGroups.value.push({
  label: '项目',
  value: 'project',
  options: projects.filter(item => (superAdmin ? true : (item.roles as string[]).length)),
});

// 项目下拉
const parentValue = ref<number | string>(projects.length ? projects[0].value : '');
// const parentGroups = ref([
//   {
//     label: '系统',
//     value: 'system',
//     options: [{ label: '系统管理', value: 1 }],
//   },
//   {
//     label: '项目',
//     value: 'project',
//     options: [
//       { label: '测试', value: 2 },
//       { label: '测试2', value: 3 },
//     ],
//   },
// ]);
function projectChange(val: number) {
  if (val !== SUPER_ADMIN_PROJECT_ID) {
    if (route.path.startsWith('/project-')) {
      let usePath = route.path;
      if (route.meta.activeMenu) {
        usePath = route.meta.activeMenu;
      }
      // 从项目的切换过来
      const pathArr = usePath.split('/').slice(2);
      pathArr.unshift(`project-${val}`);
      router.push(`/${pathArr.join('/')}`);
    } else {
      // 从系统的切换过来
      router.push(`/project-${val}/task`);
    }
  }
}

const { isMobile } = useDevice();
const { isLeft, isTop } = useLayoutMode();
const route = useRoute();
const router = useRouter();
const appStore = useAppStore();
const permissionStore = usePermissionStore();
const settingsStore = useSettingsStore();

watch(
  route,
  () => {
    showThis();
  },
  { immediate: true },
);
function showThis() {
  parentValue.value = (route.meta?.value || SUPER_ADMIN_PROJECT_ID) as number;
}

const activeMenu = computed(() => {
  const {
    meta: { activeMenu },
    path,
  } = route;
  return activeMenu ? activeMenu : path;
});

// 路由判断展示
const noHiddenRoutes = computed(() => permissionStore.routes.filter((item) => {
  if (typeof parentValue.value === 'string') {
    return [];
  }
  const hiddenFlag = !item.meta?.hidden;
  if (parentValue.value !== SUPER_ADMIN_PROJECT_ID) {
    // 项目
    return hiddenFlag && item.meta?.type === 'project' && item.meta?.value === parentValue.value;
  }
  // 系统
  return hiddenFlag && item.meta?.type !== 'project';
}));

const diskUsageProgress = reactive({
  percent: 0,
  total: 1000,
  free: 0,
  cur_use: 100,
  used_str: 'N/A/N/A',
  status: 'success' as 'success' | 'exception' | 'warning',
});
onMounted(() => {
  // 获取硬盘使用情况
  customRequest({
    url: '/api/disk_usage',
  }).then((res: any) => {
    if (res.code === 0) {
      const gb = 1024 ** 3;
      // diskUsageProgress.cur_use = res.data.app_used / gb;
      // diskUsageProgress.total = res.data.total / gb;
      diskUsageProgress.free = res.data.free / gb;
      // diskUsageProgress.percent = (diskUsageProgress.cur_use / diskUsageProgress.total) * 100;
      // diskUsageProgress.used_str =
      // diskUsageProgress.free.toString()+ 'GB 可用'+'\n共' + diskUsageProgress.total.toString() + 'GB'
      // diskUsageProgress.status = diskUsageProgress.percent > 80 ? 'warning' : 'success';
    }
  });
});

const isCollapse = computed(() => !appStore.sidebar.opened);
const isLogo = computed(() => isLeft.value && settingsStore.showLogo);
const backgroundColor = computed(() => (isLeft.value ? v3SidebarMenuBgColor : undefined));
const textColor = computed(() => (isLeft.value ? v3SidebarMenuTextColor : undefined));
const activeTextColor = computed(() => (isLeft.value ? v3SidebarMenuActiveTextColor : undefined));
const sidebarMenuItemHeight = computed(() => (!isTop.value ? 'var(--v3-sidebar-menu-item-height)' : 'var(--v3-navigationbar-height)'));
const sidebarMenuHoverBgColor = computed(() => (!isTop.value ? 'var(--v3-sidebar-menu-hover-bg-color)' : 'transparent'));
const tipLineWidth = computed(() => (!isTop.value ? '2px' : '0px'));
// 当为顶部模式时隐藏垂直滚动条
const hiddenScrollbarVerticalBar = computed(() => (isTop.value ? 'none' : 'block'));
</script>

<template>
  <div :class="{ 'has-logo': isLogo }">
    <Logo v-if="isLogo" :collapse="isCollapse" />
    <!-- 项目下拉 -->
    <div class="parent-select px-3.5 py-4.25">
      <el-check-tag
        class="w-full text-xl flex justify-between !py-0.25 !px-2.25"
        :class="{'is-collapse': isCollapse}" checked
      >
        <el-select class="layout-side-top-select" v-model="parentValue" @change="projectChange">
          <el-option-group v-for="group in parentGroups" :key="group.label" :label="group.label">
            <el-option v-for="item in group.options" :key="item.value" :label="item.label" :value="item.value" />
          </el-option-group>
        </el-select>
      </el-check-tag>
    </div>
    <el-scrollbar wrap-class="scrollbar-wrapper" :class="isCollapse ? 'is-collapse' : ''">
      <el-menu
        :default-active="activeMenu"
        :collapse="isCollapse && !isTop"
        :background-color="backgroundColor"
        :text-color="textColor"
        :active-text-color="activeTextColor"
        :unique-opened="true"
        :collapse-transition="false"
        :mode="isTop && !isMobile ? 'horizontal' : 'vertical'"
      >
        <SidebarItem v-for="route in noHiddenRoutes" :key="route.path" :item="route" :base-path="route.path" />
      </el-menu>
    </el-scrollbar>

    <el-footer class="disk-use bg-white flex flex-col items-center justify-start" :class="isCollapse ? 'h-0' : ''">
      <div style="text-align: center">
        <b>硬盘使用情况</b>
        <!-- <br/>
        {{ '已用 ' + diskUsageProgress.cur_use.toFixed(2).toString() + 'GB' }} -->
        <br/>
        {{ '剩余 ' + diskUsageProgress.free.toFixed(2).toString() + 'GB' }}
      </div>
      <!-- <el-progress
        :percentage="diskUsageProgress.percent" :status="diskUsageProgress.status"
      /> -->
    </el-footer>
  </div>
</template>

<style lang="scss" scoped>
%tip-line {
  &::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: v-bind(tipLineWidth);
    height: 100%;
    background-color: var(--v3-sidebar-menu-tip-line-bg-color);
  }
}

.has-logo {
  .el-scrollbar {
    // 多 1% 是为了在左侧模式时侧边栏最底部不显示 1px 左右的白色线条
    height: calc(101% - var(--v3-header-height));
  }
}

$footer-height: 117px;
$transition-time: 0.35s;
.el-scrollbar {
  // 多 1% 是为了在顶部模式时防止垂直滚动
  height: calc(101% - 72px - $footer-height);
  transition: height $transition-time;
  &.is-collapse {
    height: calc(101% - 72px);
  }
  :deep(.scrollbar-wrapper) {
    // 限制水平宽度
    overflow-x: hidden !important;
    .el-scrollbar__view {
      height: 100%;
    }
  }
  // 滚动条
  :deep(.el-scrollbar__bar) {
    &.is-horizontal {
      // 隐藏水平滚动条
      display: none;
    }
    &.is-vertical {
      // 当为顶部模式时隐藏垂直滚动条
      display: v-bind(hiddenScrollbarVerticalBar);
    }
  }
}

// 页脚展示硬盘使用情况
.el-footer.disk-use {
  height: $footer-height;
  transition: height $transition-time;
  .el-progress {
    width: 80%;
    margin-top: 8px;
    :deep(.el-progress__text) {
      min-width: 0;
    }
  }
}

.el-menu {
  border: none;
  min-height: 100%;
  width: 100% !important;
}

.el-menu--horizontal {
  height: v-bind(sidebarMenuItemHeight);
}

:deep(.el-menu-item),
:deep(.el-sub-menu__title),
:deep(.el-sub-menu .el-menu-item),
:deep(.el-menu--horizontal .el-menu-item) {
  height: v-bind(sidebarMenuItemHeight);
  line-height: v-bind(sidebarMenuItemHeight);
  &.is-active,
  &:hover {
    background-color: v-bind(sidebarMenuHoverBgColor);
  }
}

:deep(.el-sub-menu) {
  &.is-active {
    > .el-sub-menu__title {
      color: v-bind(activeTextColor) !important;
    }
  }
}

:deep(.el-menu-item.is-active) {
  @extend %tip-line;
}

.el-menu--collapse {
  :deep(.el-sub-menu.is-active) {
    .el-sub-menu__title {
      @extend %tip-line;
    }
  }
}

// 项目下拉
.parent-select {
  --el-input-bg-color: transparent;
  --el-fill-color-blank: transparent;
  --el-select-border-color-hover: transparent;
  --el-select-input-focus-border-color: transparent;
  background-color: #fff;
  border-bottom: 1px solid #ebeef5;

  .el-check-tag {
    //border: 1px solid var(--el-color-primary-light-7);

    // 输入框
    .layout-side-top-select.el-select:deep(.el-select__selected-item) {
      font-weight: bold;
      color: var(--el-color-primary);
    }

    // 本体
    .layout-side-top-select.el-select:deep(.el-select__wrapper) {
      padding: 5px 12px;
      min-height: 34px;
      // 边框
      box-shadow: 0 0 0 1px transparent inset;

      .el-select__suffix {
        .el-icon {
          font-size: 12px;

          svg {
            stroke: var(--el-color-primary);
            stroke-width: 100;
          }
        }
      }

      &.is-focus,
      &:hover {
        box-shadow: 0 0 0 1px transparent inset !important;
      }
    }

    &.is-collapse {
      padding: 0 !important;
      .layout-side-top-select.el-select:deep(.el-select__wrapper) {
        padding-left: 8px;
        .el-select__selection {
          display: none;
        }
      }
    }
  }
}
</style>
