import axios, { type AxiosInstance, type AxiosRequestConfig } from 'axios';
import { useUserStoreHook } from '@/store/modules/user';
import { ElMessage } from 'element-plus';
import { get, merge } from 'lodash-es';

/** 后端约定：认证失败的业务码 */
const AUTH_ERROR_CODE = 1003;

/** 会话失效：清理本地登录态并跳转登录页（登录页本身的请求不跳转） */
function logout() {
  useUserStoreHook().resetToken();
  const { pathname, search } = window.location;
  if (pathname.startsWith('/login') || pathname.startsWith('/register')) return;
  const redirect = encodeURIComponent(`${pathname}${search}`);
  window.location.href = `/login?redirect=${redirect}`;
}

/** 创建请求实例 */
function createService() {
  // 创建一个 axios 实例命名为 service
  const service = axios.create();
  // 请求拦截
  service.interceptors.request.use(
    (config) => {
      // 修改 get 请求 Content-Type，为 application/json 改为空
      if (config.method === 'get') {
        if (config.headers['Content-Type'] === 'application/json') {
          config.headers['Content-Type'] = null;
        }
      }
      return config;
    },
    // 发送失败
    error => Promise.reject(error),
  );
  // 响应拦截（可根据具体业务作出相应的调整）
  service.interceptors.response.use(
    (response) => {
      // apiData 是 api 返回的数据
      const apiData = response.data;
      // 二进制数据则直接返回
      const responseType = response.request?.responseType;
      if (responseType === 'blob' || responseType === 'arraybuffer') return apiData;
      // 这个 code 是和后端约定的业务 code，0 表示成功
      const code = apiData?.code;
      // 如果没有 code, 代表这不是项目后端开发的 api
      if (code === undefined) {
        ElMessage.error('非本系统的接口');
        return Promise.reject(new Error('非本系统的接口'));
      }
      if (code === 0) return apiData;
      if (code === AUTH_ERROR_CODE) {
        logout();
        return Promise.reject(new Error(apiData.msg || '未登录'));
      }
      const msg = apiData.message || apiData.msg || 'Error';
      if (!get(response, 'config.silent', false)) ElMessage.error(msg);
      // 与 HTTP 错误保持一致：调用方可通过 err.response.data.msg 读取后端信息
      return Promise.reject(Object.assign(new Error(msg), { response }));
    },
    (error) => {
      // status 是 HTTP 状态码
      const status = get(error, 'response.status');
      // 业务错误后端返回 HTTP 500 + {code, msg}，调用方按需读取 error.response.data
      const silent = get(error, 'config.silent', false);
      switch (status) {
        case 400:
          error.message = '请求错误';
          break;
        case 401:
          // 会话失效：登录接口本身的 401（账号或密码错误）交给调用方提示
          if (!String(get(error, 'config.url', '')).includes('/api/user/login')) {
            logout();
            return Promise.reject(error);
          }
          break;
        case 403:
          error.message = '拒绝访问';
          break;
        case 404:
          error.message = '请求地址出错';
          break;
        case 408:
          error.message = '请求超时';
          break;
        case 500:
          error.message = '服务器内部错误';
          break;
        case 501:
          error.message = '服务未实现';
          break;
        case 502:
          error.message = '网关错误';
          break;
        case 503:
          error.message = '服务不可用';
          break;
        case 504:
          error.message = '网关超时';
          break;
        case 505:
          error.message = 'HTTP 版本不受支持';
          break;
        default:
          break;
      }
      if (!silent) {
        ElMessage.error(error.response?.data?.msg || error.message);
      }
      return Promise.reject(error);
    },
  );
  return service;
}

/**
 * GET 请求（列表 / 字典等）的最小返回时长（毫秒）。
 *
 * 背景：测试环境请求通常 <100ms，fast-crud 的 loading 状态（按钮 is-loading、
 *   表格 v-loading 遮罩）持续时间太短，用户视觉上来不及感知就消失，看起来
 *   像是"点了没反应"。线上环境请求本来就 >500ms，此配置对其没有任何影响。
 *
 * 行为：GET 请求的 Promise 至少等待 MIN_DELAY_MS 才 resolve。
 *   - 真实请求 < 500ms：延迟到 500ms resolve → loading 清晰可见；
 *   - 真实请求 > 500ms：按真实时长 resolve → 和未加该机制时完全一致；
 *   - 非 GET 请求（表单提交 POST / PATCH / DELETE 等）不受影响，依然按真实
 *     速度返回，不影响表单响应感；
 *   - 业务侧可通过 config.minDelay 显式覆盖（例如传 0 关闭延迟）。
 *
 * 例外：字典 / 枚举 / 项目配置 类接口（system/enums、project/config、
 *   bug/tracker_meta）会自动跳过最小延迟。因为 fast-crud 的 dict-select
 *   组件在字典未加载时会先把原始 value（如 "3"）当成 label 展示出来，
 *   等 500ms 后字典返回才切换为真实 label（如 "中"），造成明显的字段
 *   "数字→文字"闪烁。字典本身的加载速度足够快，无需人为延迟。
 */
const MIN_DELAY_MS = 500;

/** 平台接口请求：浏览器使用 Session Cookie 认证 */
function createCustomRequest(service: AxiosInstance) {
  return function <T = any>(
    config: AxiosRequestConfig & { silent?: boolean; minDelay?: number },
  ): Promise<T> {
    const defaultConfig = {
      headers: {
        // 'web' 表示使用 Session 认证；API 调用方可传入 access_token
        'LQA-Authorization': 'web',
        'Content-Type': 'application/json',
      },
      withCredentials: true,
      timeout: 0,
      baseURL: import.meta.env.VITE_BASE_API,
      data: {},
    };
    // 将默认配置 defaultConfig 和传入的自定义配置 config 进行合并成为 mergeConfig
    const mergeConfig = merge(defaultConfig, config);

    // 仅对 GET 请求（列表查询 / 字典加载等）应用最小返回时长；非 GET 请求保持原速
    const method = String(mergeConfig.method || 'get').toLowerCase();
    // 字典 / 枚举 / 项目配置 类"打开表单必须等的加载请求"直接跳过最小延迟，
    // 否则 fast-crud 的 dict-select 组件会先显示原始 value（如 "3"）再切换为
    // label（如 "中"），造成明显的字段闪烁。
    const url = String(mergeConfig.url || '');
    const isDictLike = /\/api\/(system\/enums|project\/config|bug\/tracker_meta)/.test(url);
    const minDelay = config.minDelay ?? (method === 'get' && !isDictLike ? MIN_DELAY_MS : 0);
    if (minDelay <= 0) {
      return service(mergeConfig);
    }

    // Promise.all 等待"真实请求"与"最小延时"都完成，取请求结果返回
    const requestPromise = service(mergeConfig);
    const delayPromise = new Promise(resolve => setTimeout(resolve, minDelay));
    return Promise.all([requestPromise, delayPromise]).then(([res]) => res) as Promise<T>;
  };
}

/** 用于网络请求的实例 */
const service = createService();
/** 用于网络请求的方法 */
export const customRequest = createCustomRequest(service);
export const request = customRequest;
