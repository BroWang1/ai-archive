import { useUserStoreHook } from '@/store/modules/user';

/** 全局权限判断函数，和权限指令 v-permission 功能类似 */
export const checkPermission = (permissionRoles: string[]): boolean => {
  if (Array.isArray(permissionRoles) && permissionRoles.length > 0) {
    const { superAdmin, roles } = useUserStoreHook();
    if (superAdmin) {
      return true;
    }
    return roles.some(role => permissionRoles.includes(role));
  }
  console.error('need roles! Like checkPermission([\'admin\',\'editor\'])');
  return false;
};
