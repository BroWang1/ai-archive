/**
 * 当前项目缺陷系统信息及提单下拉选项（发现版本/修复版本/发布计划）
 * GET /api/bug/tracker_meta?project_id=
 */
import { customRequest } from '@/utils/service';

const cache = new Map();

export async function getTrackerMeta(projectId, force = false) {
  if (!force && cache.has(projectId)) return cache.get(projectId);
  const empty = {
    type: 'none', label: '', remote: false, version_report_list: [], version_fix_list: [], release_id_list: [], error: '',
  };
  let meta = empty;
  try {
    const res = await customRequest({ url: '/api/bug/tracker_meta', method: 'get', params: { project_id: projectId }, silent: true });
    meta = { ...empty, ...res.data };
  } catch (err) {
    meta = { ...empty, error: err?.response?.data?.msg || err.message };
  }
  cache.set(projectId, meta);
  // 缓存 60 秒，配置修改后能较快生效
  setTimeout(() => cache.delete(projectId), 60 * 1000);
  return meta;
}

/** 转换为提单表单使用的 {params, options} */
export function toBugFormOptions(meta) {
  return {
    params: { version_report: '', version_fix: '', release_id: '' },
    options: {
      version_report: meta.version_report_list || [],
      version_fix: meta.version_fix_list || [],
      release_id: meta.release_id_list || [],
    },
  };
}
