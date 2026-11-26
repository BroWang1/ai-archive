import { dict } from '@fast-crud/fast-crud';
import { customRequest } from '@/utils/service.ts';

/** 用户 */
export function getUserDict() {
  return dict({
    url: '/api/user/list',
    value: 'value',
    label: 'label',
    async getData({ url }) {
      const { data } = await customRequest({ url, method: 'get', params: {
        info_type: 0, // 简略信息
        page_size: 1000000000000000,
      } });
      // 只返回 el-option 需要的 { value, label }，避免把 updated_at / last_login_at / created_at
      // 等后端原始字段作为 attrs 透传到 <el-option>，否则会触发
      // "[Vue warn]: Slot default invoked outside of the render function" 并导致页面白屏
      return data.list.map(item => ({
        value: item.id,
        label: item.name_zh ? `${item.name}(${item.name_zh})` : item.name,
      }));
    },
  });
}

/** 区域语言 */
export function getLanguageDict(projectId, filter = false) {
  if (projectId) {
    return dict({
      url: `/api/project/config?_=${Math.random()}`,
      async getData() {
        const res = await customRequest({
          url: '/api/project/config',
          method: 'get',
          params: { project_id: projectId, cate: 'Language' },
        });
        res.data.list.sort((a, b) => a.value - b.value);
        if (filter) {
          // 执行过滤：只保留已启用，并只返回 el-option 需要的字段，
          // 避免把后端原始字段作为 attrs 透传到 <el-option>，否则会触发
          // "[Vue warn]: Slot default invoked outside of the render function" 警告
          return res.data.list
            .filter(item => item.enable)
            .map(item => ({
              value: item.value,
              label: item.label,
              name: item.name,
            }));
        }
        // 展示未启用数据：同样仅返回必要字段
        return res.data.list.map(item => ({
          value: item.value,
          label: item.enable ? item.label : `${item.label}（未启用）`,
          name: item.name,
          color: item.enable ? undefined : 'info',
          effect: item.enable ? undefined : 'light',
          disabled: !item.enable,
        }));
      },
    });
  }
  return dict({
    url: `/api/system/enums/language?project_id=${projectId}`,
  });
}

/** 缺陷类型 */
export function getBugTypeDict(projectId) {
  // 有项目
  if (projectId) {
    return dict({
      url: `/api/project/config?_=${Math.random()}`,
      async getData() {
        const res = await customRequest({
          url: '/api/project/config',
          method: 'get',
          params: { project_id: projectId, cate: 'BugType' },
        });
        // 仅返回 el-option 需要的字段，避免把后端整条原始记录透传到 <el-option>，
        // 否则会触发 "[Vue warn]: Slot default invoked outside of the render function"
        return res.data.list.map(item => ({
          value: item.value,
          label: item.enable ? item.label : `${item.label}（未启用）`,
          name: item.name,
          color: item.enable ? undefined : 'info',
          effect: item.enable ? undefined : 'light',
          disabled: !item.enable,
        }));
      },
    });
  }

  // 没有项目
  return  dict({
    url: '/api/system/enums/bug_type',
  });
}
