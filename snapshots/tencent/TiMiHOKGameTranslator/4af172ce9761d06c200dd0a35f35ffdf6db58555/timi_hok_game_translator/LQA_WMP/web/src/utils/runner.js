/**
 * 还原任务执行：由浏览器直接调用项目配置的 Webhook（Jenkins / GitLab CI / 自建服务等）
 *  1. POST /api/job/action {action: start|retry}  后端校验任务状态并返回渲染好的 Webhook 请求
 *  2. 浏览器请求 Webhook（目标服务需允许平台域名跨域）
 *  3. 成功后 POST /api/job/action {action: started}  任务置为执行中
 */
import { customRequest } from '@/utils/service';

/** 从 Webhook 响应中尽量提取外部构建ID/链接，便于在任务详情中追溯 */
function extractBuildId(resp, data) {
  if (data && typeof data === 'object') {
    const keys = ['build_id', 'buildId', 'web_url', 'url', 'id', 'number', 'pipeline_id'];
    for (const k of keys) {
      if (data[k] !== undefined && data[k] !== null && data[k] !== '') return String(data[k]);
    }
  }
  // Jenkins 返回 201 + Location（需要目标服务 Access-Control-Expose-Headers: Location）
  return resp.headers.get('Location') || '';
}

function encodeBody(body, headers) {
  if (body === null || body === undefined) return undefined;
  const contentType = Object.entries(headers || {})
    .find(([k]) => k.toLowerCase() === 'content-type')?.[1] || '';
  if (contentType.includes('application/x-www-form-urlencoded') && typeof body === 'object') {
    const params = new URLSearchParams();
    Object.entries(body).forEach(([k, v]) => params.append(k, Array.isArray(v) ? v.join(',') : String(v)));
    return params.toString();
  }
  return typeof body === 'string' ? body : JSON.stringify(body);
}

/** 浏览器发起 Webhook 请求 */
export async function callWebhook(trigger) {
  let resp;
  try {
    resp = await fetch(trigger.url, {
      method: trigger.method,
      headers: trigger.headers || {},
      body: trigger.method === 'GET' ? undefined : encodeBody(trigger.body, trigger.headers),
      mode: 'cors',
      credentials: 'omit',
    });
  } catch (err) {
    throw new Error(`无法访问 Webhook：网络不可达，或目标服务未允许跨域（CORS）。${err.message || ''}`);
  }
  const text = await resp.text().catch(() => '');
  if (!resp.ok) {
    throw new Error(`Webhook 返回 HTTP ${resp.status}：${text.slice(0, 300)}`);
  }
  let data = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = null;
  }
  return extractBuildId(resp, data);
}

/**
 * 开始/重试任务
 * @param {number} jobId
 * @param {'start'|'retry'} action
 * @returns {Promise<string>} 提示信息
 */
export async function runJob(jobId, action = 'start') {
  const res = await customRequest({ url: '/api/job/action', method: 'post', data: { action, job_id: jobId } });
  const { trigger, regression } = res.data;
  const buildId = await callWebhook(trigger);
  await customRequest({
    url: '/api/job/action',
    method: 'post',
    data: { action: 'started', job_id: jobId, regression, build_id: buildId },
  });
  return buildId ? `已触发还原任务（${buildId}）` : '已触发还原任务';
}
