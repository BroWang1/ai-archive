import router from '@/router';
import { useUserStoreHook } from '@/store/modules/user';
import { usePermissionStoreHook } from '@/store/modules/permission';
import { setRouteChange } from '@/hooks/useRouteListener';
import { useTitle } from '@/hooks/useTitle';
import { getToken } from '@/utils/cache/cookies';
import routeSettings from '@/config/route';
import isWhiteList from '@/config/white-list';
import NProgress from 'nprogress';
import 'nprogress/nprogress.css';

const { setTitle } = useTitle();
NProgress.configure({ showSpinner: false });

router.beforeEach(async (to, _from, next) => {
  NProgress.start();
  const userStore = useUserStoreHook();
  const permissionStore = usePermissionStoreHook();

  // 未登录
  if (!getToken()) {
    if (isWhiteList(to)) return next();
    return next({ path: '/login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : {} });
  }

  // 已登录访问登录/注册页，回到首页
  if (isWhiteList(to)) {
    return next({ path: '/' });
  }

  // 已获取过用户信息
  if (userStore.roles.length !== 0) {
    const { projects, superAdmin } = userStore;
    if (to.path === '/') {
      if (projects.length) return next({ path: `/project-${projects[0].value}/task` });
      return next({ path: superAdmin ? '/project' : '/403' });
    }
    return next();
  }

  // 首次进入：获取用户信息与项目角色，生成可访问路由
  try {
    await userStore.getInfo();
    // 注意：角色必须是一个数组！ 例如: ["admin"] 或 ["developer", "editor"]
    const { roles, superAdmin, projects } = userStore;
    routeSettings.dynamic ? permissionStore.setRoutes(roles, superAdmin, projects) : permissionStore.setAllRoutes();
    permissionStore.addRoutes.forEach(route => router.addRoute(route));
    // 没有任何项目权限（如刚注册的用户），超级管理员可进入系统管理创建项目
    if (!projects.length && !superAdmin) {
      return next({ path: '/403', replace: true });
    }
    // 设置 replace: true, 因此导航将不会留下历史记录
    next({ ...to, replace: true });
  } catch (err: any) {
    // 会话失效等错误：重置本地登录态并重新登录
    userStore.resetToken();
    next({ path: '/login', query: { redirect: to.fullPath } });
  }
});

router.afterEach((to) => {
  setRouteChange(to);
  setTitle(to.meta.title);
  NProgress.done();
});
