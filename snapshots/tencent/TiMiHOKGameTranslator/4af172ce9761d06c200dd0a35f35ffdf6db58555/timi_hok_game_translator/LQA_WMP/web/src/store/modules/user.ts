import { ref } from 'vue';
import store from '@/store';
import { defineStore } from 'pinia';
import { useTagsViewStore } from './tags-view';
import { useSettingsStore } from './settings';
import { getToken, removeToken, setToken } from '@/utils/cache/cookies';
import { resetRouter } from '@/router';
import routeSettings from '@/config/route';
import { customRequest } from '@/utils/service';
import Cookies from 'js-cookie';
import CacheKey from '@/constants/cache-key';

export interface LoginForm {
  username: string
  password: string
}

export interface RegisterForm extends LoginForm {
  name_zh?: string
  email?: string
}

type UserEntity = {
  user: {
    id: number
    name_zh: string
    name: string
    email: string
    is_admin: number
    access_token: string
  },
};
type ProjectEntity = {
  projects: { id: number, name: string, roles: string[] }[]
};

export const useUserStore = defineStore('user', () => {
  /** 是否已登录的本地标记（真正的认证依赖 Session Cookie） */
  const token = ref<string>(getToken() || '');
  const roles = ref<string[]>([]);
  const name = ref<string>('');
  const username = ref<string>('');
  const email = ref<string>('');
  const superAdmin = ref(0);
  const projects = ref<LabelValueOptions>([]);

  const tagsViewStore = useTagsViewStore();
  const settingsStore = useSettingsStore();

  /** 账号密码登录 */
  const login = async (form: LoginForm) => {
    await customRequest({ url: '/api/user/login', method: 'post', data: form, silent: true });
    setToken('web');
    token.value = 'web';
  };

  /** 自助注册 */
  const register = async (form: RegisterForm) => customRequest({
    url: '/api/user/register', method: 'post', data: form, silent: true,
  });

  /** 获取当前用户信息及项目角色 */
  const getInfo = async () => {
    const { data }: { data: UserEntity } = await customRequest({
      url: '/api/user/entity',
      method: 'get',
      params: { info_type: 1 },
    });
    const { data: projectData }: { data: ProjectEntity } = await customRequest({
      url: '/api/user/permission',
      method: 'get',
    });
    Cookies.set(CacheKey.USERNAME_CH, data.user.name_zh || data.user.name);
    Cookies.set(CacheKey.USERNAME_EN, data.user.name);
    name.value = data.user.name;
    username.value = data.user.name_zh || data.user.name;
    email.value = data.user.email || '';

    // 角色：后端返回 `${project_id}_${role}`，前端路由使用 `${project_id}:${roleName}`
    superAdmin.value = data.user.is_admin;
    const roleMap: Record<string, string> = {
      1: 'admin',
      2: 'test',
      3: 'dev',
    };
    roles.value = [...routeSettings.defaultRoles];
    projectData.projects.forEach(item => item.roles.forEach((role) => {
      const roleId = String(role).split('_').pop() as string;
      roles.value.push(`${item.id}:${roleMap[roleId]}`);
    }));

    // 项目
    projects.value = projectData.projects.map(item => ({
      label: item.name, value: item.id, ...item,
    }));
  };

  /** 修改密码 */
  const changePassword = async (oldPassword: string, newPassword: string) => customRequest({
    url: '/api/user/password',
    method: 'post',
    data: { old_password: oldPassword, new_password: newPassword },
  });

  /** 登出 */
  const logout = async () => {
    try {
      await customRequest({ url: '/api/user/logout', method: 'post', silent: true });
    } finally {
      resetToken();
      resetRouter();
      _resetTagsView();
    }
  };
  /** 重置本地登录态 */
  const resetToken = () => {
    removeToken();
    token.value = '';
    roles.value = [];
    projects.value = [];
    superAdmin.value = 0;
  };
  /** 重置 Visited Views 和 Cached Views */
  const _resetTagsView = () => {
    if (!settingsStore.cacheTagsView) {
      tagsViewStore.delAllVisitedViews();
      tagsViewStore.delAllCachedViews();
    }
  };

  return {
    token, roles, name, username, email, superAdmin, projects,
    login, register, getInfo, changePassword, logout, resetToken,
  };
});

/** 在 setup 外使用 */
export function useUserStoreHook() {
  return useUserStore(store);
}
