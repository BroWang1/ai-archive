import { ref } from 'vue';
import store from '@/store';
import { defineStore } from 'pinia';
import { type RouteRecordRaw } from 'vue-router';
import { constantRoutes, dynamicRoutes, systemRoute } from '@/router';
import { flatMultiLevelRoutes } from '@/router/helper';
import routeSettings from '@/config/route';
import { SUPER_ADMIN_PROJECT_ID } from '@/constants/app-key';

const hasPermission = (roles: string[], route: RouteRecordRaw, superAdmin: number) => {
  const routeRoles = route.meta?.roles || [];
  if (superAdmin) {
    return true;
  }
  return routeRoles.length ? roles.some(role => routeRoles.includes(role)) : true;
};

const filterSystemRoutes = (routes: RouteRecordRaw[], roles: string[], superAdmin: number) => {
  const res: RouteRecordRaw[] = [];
  routes.forEach((route) => {
    const tempRoute = {
      ...route,
      meta: { ...route.meta, type: 'system', value: SUPER_ADMIN_PROJECT_ID },
    };
    if (hasPermission(roles, tempRoute, superAdmin)) {
      if (tempRoute.children) {
        tempRoute.children = filterSystemRoutes(tempRoute.children, roles, superAdmin);
      }
      res.push(tempRoute);
    }
  });
  return res;
};

const filterDynamicRoutes = (routes: RouteRecordRaw[], roles: string[], superAdmin: number, projects: number[]) => {
  const res: RouteRecordRaw[] = [];
  projects.forEach((item) => {
    routes.forEach((route) => {
      const tempRoute = {
        ...route, name: `${item}-${route.name as string}`, path: `/project-${item}${route.path}`,
        meta: {
          ...route.meta, type: 'project', value: item,
          activeMenu: route.meta!.activeMenu ? `/project-${item}${route.meta!.activeMenu}` : undefined,
          // @ts-ignore
          roles: (route.meta.roles || []).map(roleItem => `${item}:${roleItem}`),
        },
      };
      if (hasPermission(roles, tempRoute, superAdmin)) {
        if (tempRoute.children) {
          tempRoute.children = filterDynamicRoutes(tempRoute.children, roles, superAdmin, [item]);
        }
        res.push(tempRoute);
      }
    });
  });
  return res;
};

export const usePermissionStore = defineStore('permission', () => {
  /** 可访问的路由 */
  const routes = ref<RouteRecordRaw[]>([]);
  /** 有访问权限的动态路由 */
  const addRoutes = ref<RouteRecordRaw[]>([]);

  /** 根据角色生成可访问的 Routes（可访问的路由 = 常驻路由 + 有访问权限的动态路由） */
  const setRoutes = (roles: string[], superAdmin: number, projects: LabelValueOptions) => {
    const accessedRoutes = [
      ...filterSystemRoutes(systemRoute, roles, superAdmin),
      ...filterDynamicRoutes(dynamicRoutes, roles, superAdmin, projects.map(item => item.value) as number[]),
    ];
    _set(accessedRoutes);
  };

  /** 所有路由 = 所有常驻路由 + 所有动态路由 */
  const setAllRoutes = () => {
    _set(dynamicRoutes);
  };

  const _set = (accessedRoutes: RouteRecordRaw[]) => {
    routes.value = constantRoutes.concat(accessedRoutes);
    addRoutes.value = routeSettings.thirdLevelRouteCache ? flatMultiLevelRoutes(accessedRoutes) : accessedRoutes;
  };

  return { routes, addRoutes, setRoutes, setAllRoutes };
});

/** 在 setup 外使用 */
export function usePermissionStoreHook() {
  return usePermissionStore(store);
}
