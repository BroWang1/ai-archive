// ==========================================
// 文件: LQARestore\Platform\Editor\Core\LqaApiClient.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// 与 LQA 平台服务端交互的统一客户端 (编辑器侧)
    /// 目的: 把 "和服务器打交道" 的所有通用细节收敛到一处, 供连通性测试 / 以后的拉取任务 / 下载 dump /
    ///   上传结果等功能直接复用, 避免每个功能各写一份 UnityWebRequest 样板与踩同样的坑
    /// 统一封装的要点 (都是之前在连通性测试里踩出来的经验):
    ///   1. 自动拼接 Host + path, 自动加鉴权头 LQA-Authorization;
    ///   2. redirectLimit = 0 —— 平台对未鉴权请求会 302 跳登录页, 禁止自动跟随可避免
    ///      "Redirect limit exceeded" 的模糊报错, 让 302 作为响应码被直接识别;
    ///   3. 统一超时;
    ///   4. 统一的响应归类 (LqaResponseKind), 把 HTTP 码 + 网络错误翻译成业务语义;
    ///   5. 编辑器内无 MonoBehaviour 主循环, 故请求以 "异步句柄 + 每帧 Poll" 的形式对外
    ///      (调用方在 EditorApplication.update 里轮询 LqaRequest.Poll)
    /// 用法示例 (连通性测试):
    ///   var client = new LqaApiClient(LqaPlatformConfig.Load());
    ///   var req = client.TestConnection();
    ///   // 每帧: if (req.Poll()) { switch(req.Kind){...} 用 req.Code / req.Text / req.Error }
    /// 用法示例 (以后拉取, GET JSON):
    ///   var req = client.Get("/api/job/datas?job_id=65&count=1");
    ///   // Poll 完成后 req.Text 就是响应体, 交给 MiniJson 解析
    /// </summary>
    public class LqaApiClient
    {
        /// <summary>
        /// 鉴权请求头名 (平台全局鉴权中间件读取)
        /// </summary>
        public const string AuthHeader = "LQA-Authorization";

        /// <summary>
        /// 默认请求超时 (秒)
        /// </summary>
        public const int DefaultTimeoutSec = 10;

        /// <summary>
        /// 平台连接配置 (Host / DownloadHost / 鉴权令牌 Authorization 等), 构造时注入, 全程只读
        /// </summary>
        private readonly LqaPlatformConfig _config;

        /// <summary>
        /// 构造客户端, 配置由调用方读取后注入, 本类不负责加载/持久化
        /// </summary>
        /// <param name="config">平台连接配置, 通常来自 LqaPlatformConfig.Load()</param>
        public LqaApiClient(LqaPlatformConfig config)
        {
            _config = config;
        }

        /// <summary>
        /// 当前配置 (只读访问, 供调用方读取 Host/DownloadHost 等)
        /// </summary>
        public LqaPlatformConfig Config { get { return _config; } }

        // ==========================================
        // 通用请求构造
        // ==========================================

        /// <summary>
        /// 发起一个 GET 请求, 返回可轮询的句柄
        /// </summary>
        /// <param name="path">相对路径 (以 / 开头, 如 "/api/test?num=1"); 也可传绝对 URL</param>
        /// <param name="withAuth">是否携带鉴权头 (默认 true; 平台几乎所有接口都需要)</param>
        /// <param name="useDownloadPath">是否用 DownloadPath 前缀 (下载 dump/资源时用), 否则用 ApiPath 前缀</param>
        public LqaRequest Get(string path, bool withAuth = true, bool useDownloadPath = false)
        {
            var req = UnityWebRequest.Get(BuildUrl(path, useDownloadPath));
            Prepare(req, withAuth);
            return LqaRequest.Send(req);
        }

        /// <summary>
        /// 发起一个 POST 请求 (JSON body), 返回可轮询的句柄
        /// </summary>
        /// <param name="path">相对路径或绝对 URL</param>
        /// <param name="jsonBody">JSON 字符串请求体</param>
        /// <param name="withAuth">是否携带鉴权头</param>
        public LqaRequest PostJson(string path, string jsonBody, bool withAuth = true)
        {
            return SendJson(UnityWebRequest.kHttpVerbPOST, path, jsonBody, withAuth);
        }

        /// <summary>
        /// 发起一个带 JSON body 的请求, 支持任意 HTTP 方法 (POST/PATCH 等)
        /// </summary>
        /// <param name="verb">HTTP 方法, 如 "POST" / "PATCH"</param>
        /// <param name="path">相对路径或绝对 URL</param>
        /// <param name="jsonBody">JSON 字符串请求体</param>
        /// <param name="withAuth">是否携带鉴权头</param>
        public LqaRequest SendJson(string verb, string path, string jsonBody, bool withAuth = true)
        {
            var req = new UnityWebRequest(BuildUrl(path, false), verb);
            byte[] body = System.Text.Encoding.UTF8.GetBytes(jsonBody ?? "");
            req.uploadHandler = new UploadHandlerRaw(body);
            req.downloadHandler = new DownloadHandlerBuffer();
            req.SetRequestHeader("Content-Type", "application/json");
            Prepare(req, withAuth);
            return LqaRequest.Send(req);
        }

        /// <summary>
        /// 发起一个 multipart/form-data POST 请求 (上传文件/表单), 返回可轮询的句柄, 为以后 "上传结果" 预留
        /// </summary>
        /// <param name="path">相对路径或绝对 URL</param>
        /// <param name="form">已构造好的 WWWForm (可含字段与文件)</param>
        /// <param name="withAuth">是否携带鉴权头</param>
        public LqaRequest PostForm(string path, WWWForm form, bool withAuth = true)
        {
            var req = UnityWebRequest.Post(BuildUrl(path, false), form);
            Prepare(req, withAuth);
            return LqaRequest.Send(req);
        }

        // ==========================================
        // 具体业务 API
        // ==========================================

        /// <summary>
        /// 连通性测试: GET /api/test?num=1&delay=0 (带鉴权)
        /// 该接口只回显参数, 但会过平台全局鉴权中间件, 故能一次验证 网络可达 + 服务存活 + JWT 有效
        /// </summary>
        public LqaRequest TestConnection()
        {
            return Get("/api/test?num=1&delay=0", withAuth: true, useDownloadPath: false);
        }

        /// <summary>
        /// 拉取任务数据清单: GET /api/job/datas (带鉴权)
        /// 返回体形如 { code, data: { bug_ids, datas: [{ id, file_path, module_id }] } }
        ///   - id: 平台数据标识 (data_id), 用作本地文件命名;
        ///   - file_path: 该条 dump 数据在平台的存储路径 (gzip), 供下一步下载;
        ///   - module_id: 所属模块
        /// </summary>
        /// <param name="jobId">任务批次 ID</param>
        /// <param name="language">语言码 (平台码, 如 en/pt)</param>
        /// <param name="count">拉取条数上限</param>
        /// <param name="minId">增量游标, 只拉 id 大于它的数据</param>
        /// <param name="moduleIds">模块过滤, 多个用 '_' 分隔 (转成 ',' 发送); 空=不过滤</param>
        public LqaRequest GetJobDatas(string jobId, string language,
                                      string count, string minId, string moduleIds)
        {
            var sb = new System.Text.StringBuilder("/api/job/datas?");
            sb.Append("job_id=").Append(UnityWebRequest.EscapeURL(jobId ?? "0"));
            if (!string.IsNullOrEmpty(language))
                sb.Append("&language=").Append(UnityWebRequest.EscapeURL(language));
            if (!string.IsNullOrEmpty(count))
                sb.Append("&count=").Append(UnityWebRequest.EscapeURL(count));
            if (!string.IsNullOrEmpty(minId))
                sb.Append("&minID=").Append(UnityWebRequest.EscapeURL(minId));
            if (!string.IsNullOrEmpty(moduleIds))
                // 平台约定: module_ids 用 ',' 分隔; 本地配置用 '_' 分隔便于输入, 这里转换
                sb.Append("&module_ids=").Append(UnityWebRequest.EscapeURL(moduleIds.Replace('_', ',')));
            return Get(sb.ToString(), withAuth: true, useDownloadPath: false);
        }

        /// <summary>
        /// 下载单条 dump 数据: GET {Host}{DownloadPath}{file_path}
        /// file_path 来自 GetJobDatas 返回的每项 file_path (平台资源路径, gzip 压缩)
        /// 资源需鉴权, 故带上 LQA-Authorization
        /// 完成后 req.Bytes 即 gzip 原始字节, 交给 LqaDumpDecoder 解码为 dump json
        /// </summary>
        public LqaRequest DownloadDataDump(string filePath)
        {
            // file_path 通常以 / 开头的相对路径; Get 会自动拼到 Host + DownloadPath 后
            return Get(filePath, withAuth: true, useDownloadPath: true);
        }

        // 说明: 上传相关业务 API 已在下方实现; 若后续还需新增其它接口, 按上面 Get/PostJson/PostForm 的封装方式追加即可

        // ==========================================
        // 上传相关业务 API (三步链路, 对齐平台上传协议)
        //   1. UploadDataJson -> POST  /api/data/entity  建 data, 返回 data_id
        //   2. UploadFile -> POST  /api/upload_file  传截图, 返回 file_path
        //   3. UpdateDataImage -> PATCH /api/data/entity  回填 shot_img_path/module_id/resource_version
        // ==========================================

        /// <summary>
        /// [上传第1步] POST /api/data/entity: 用补全后的 dump json 建一条 data
        /// body = { project_id, job_id, data:{...} } (application/json)
        /// 成功响应形如 { code:0, data:{ data:{ id, ... } } }, 其中 data.data.id 即新建的平台 data_id
        /// </summary>
        /// <param name="projectId">项目 ID</param>
        /// <param name="jobId">任务 ID</param>
        /// <param name="dataJsonObject">已补全平台必需 key 的 data 对象的 JSON 字符串 (调用方拼好)</param>
        public LqaRequest UploadDataJson(string projectId, string jobId, string dataJsonObject)
        {
            // 手工拼外层 JSON: {"project_id": ..,"job_id": ..,"data": <dataJsonObject> }
            // dataJsonObject 已是合法 JSON 文本, 直接内嵌 (不再二次转义)
            var sb = new System.Text.StringBuilder();
            sb.Append("{\"project_id\":").Append(ToJsonNumberOrString(projectId))
              .Append(",\"job_id\":").Append(ToJsonNumberOrString(jobId))
              .Append(",\"data\":").Append(string.IsNullOrEmpty(dataJsonObject) ? "{}" : dataJsonObject)
              .Append("}");
            return PostJson("/api/data/entity", sb.ToString(), withAuth: true);
        }

        /// <summary>
        /// [上传第2步] POST /api/upload_file: 上传单个文件 (如截图), multipart 字段名固定为 "file"
        /// 成功响应形如 { code:0, data:{ file_name, file_path } }, file_path 供第3步回填
        /// </summary>
        /// <param name="fileBytes">文件原始字节</param>
        /// <param name="fileName">文件名 (含扩展名, 平台据此取扩展名)</param>
        public LqaRequest UploadFile(byte[] fileBytes, string fileName)
        {
            var form = new WWWForm();
            // 平台上传接口取请求里的第一个文件, 字段名约定为 "file"
            form.AddBinaryData("file", fileBytes ?? new byte[0], fileName ?? "file.png", "application/octet-stream");
            return PostForm("/api/upload_file", form, withAuth: true);
        }

        /// <summary>
        /// [上传第3步] PATCH /api/data/entity: 给已建的 data 回填截图路径与可选的 module_id/resource_version
        /// body = { id, shot_img_path, module_id?, resource_version? } (application/json)
        /// </summary>
        /// <param name="dataId">第1步返回的平台 data_id</param>
        /// <param name="shotImgPath">第2步返回的 file_path</param>
        /// <param name="moduleId">模块 ID (空则不带)</param>
        /// <param name="resourceVersion">资源版本 (空则不带)</param>
        public LqaRequest UpdateDataImage(string dataId, string shotImgPath, string moduleId, string resourceVersion)
        {
            var sb = new System.Text.StringBuilder();
            sb.Append("{\"id\":").Append(ToJsonNumberOrString(dataId))
              .Append(",\"shot_img_path\":").Append(JsonStr(shotImgPath));
            if (!string.IsNullOrEmpty(moduleId))
                sb.Append(",\"module_id\":").Append(ToJsonNumberOrString(moduleId));
            if (!string.IsNullOrEmpty(resourceVersion))
                sb.Append(",\"resource_version\":").Append(JsonStr(resourceVersion));
            sb.Append("}");
            return SendJson("PATCH", "/api/data/entity", sb.ToString(), withAuth: true);
        }

        /// <summary>
        /// [提交还原结果] POST /api/image/entity: 把一张还原图 (Restore.png) 连同文本框 rect_locations 作为
        /// image 提交, 关联到指定 data_id。multipart: 一个文件字段 (图) + 若干表单字段
        /// 平台提交图片接口必需: project_id/job_id/data_id (int)、language (int, 内部语言码)、rect_locations (str)
        /// ai_sign 默认 0 —— 传 0 表示"只存图与框, 不触发 AI 检测/建 bug", 契合手动提交还原结果的语义
        /// </summary>
        /// <param name="projectId">项目 ID</param>
        /// <param name="jobId">任务 ID</param>
        /// <param name="dataId">该还原图对应的平台 data_id</param>
        /// <param name="language">平台内部语言码 (数字字符串)</param>
        /// <param name="rectLocationsJson">文本框 JSON (平台 rect_locations 格式)</param>
        /// <param name="imageBytes">还原图字节 (Restore.png)</param>
        /// <param name="imageFileName">图片文件名 (含扩展名)</param>
        /// <param name="aiSign">是否触发 AI 检测, 默认 "0" (不触发)</param>
        public LqaRequest UploadImageEntity(string projectId, string jobId, string dataId, string language,
                                            string rectLocationsJson, byte[] imageBytes, string imageFileName,
                                            string aiSign = "0")
        {
            var form = new WWWForm();
            form.AddField("project_id", projectId ?? "0");
            form.AddField("job_id", jobId ?? "0");
            form.AddField("data_id", dataId ?? "0");
            form.AddField("language", language ?? "0");
            form.AddField("rect_locations", string.IsNullOrEmpty(rectLocationsJson) ? "{}" : rectLocationsJson);
            form.AddField("ai_sign", aiSign ?? "0");
            form.AddBinaryData("file", imageBytes ?? new byte[0], imageFileName ?? "Restore.png", "image/png");
            return PostForm("/api/image/entity", form, withAuth: true);
        }

        /// <summary>
        /// 拉取语言映射: GET /api/job/entity?job_id=&mappings=1&fields=id (带鉴权)
        /// 该接口在 mappings=1 时返回 data.mappings.language = [{ name, value, label }],
        ///   其中 value 即提交 image 时要用的 "平台内部语言码" (数字), name 为显示名 (如 en/中文)
        /// 语言列表是项目相关且存于平台 DB, 故动态拉取而非硬编码, 保证与平台一致
        /// </summary>
        /// <param name="jobId">任意有效 job_id (语言表随该 job 所属项目返回)</param>
        public LqaRequest GetLanguageMappings(string jobId)
        {
            return Get("/api/job/entity?job_id=" + UnityWebRequest.EscapeURL(jobId ?? "0") + "&mappings=1&fields=id",
                       withAuth: true, useDownloadPath: false);
        }

        /// <summary>
        /// 把纯数字字符串按 JSON 数字输出, 否则按 JSON 字符串输出 (兼容 id 为数字/字符串)
        /// </summary>
        private static string ToJsonNumberOrString(string s)
        {
            if (string.IsNullOrEmpty(s)) return "0";
            long n;
            if (long.TryParse(s, out n)) return s;  // 纯整数, 直接作数字
            return JsonStr(s);
        }

        /// <summary>
        /// 把字符串转成合法的 JSON 字符串字面量 (加引号并转义)
        /// </summary>
        private static string JsonStr(string s)
        {
            if (s == null) return "\"\"";
            var sb = new System.Text.StringBuilder("\"");
            foreach (char c in s)
            {
                switch (c)
                {
                    case '\"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default: sb.Append(c); break;
                }
            }
            sb.Append("\"");
            return sb.ToString();
        }

        // ==========================================
        // 内部
        // ==========================================

        /// <summary>
        /// 拼接完整 URL: 绝对 URL 原样返回; 相对路径拼到 Host + (ApiPath | DownloadPath) 之后
        /// </summary>
        private string BuildUrl(string path, bool useDownloadPath)
        {
            if (!string.IsNullOrEmpty(path) &&
                (path.StartsWith("http://") || path.StartsWith("https://")))
                return path;

            string host = (_config.Host ?? "").TrimEnd('/');
            string prefix = NormalizePrefix(useDownloadPath ? _config.DownloadPath : _config.ApiPath);
            string p = path ?? "";
            if (p.Length > 0 && !p.StartsWith("/")) p = "/" + p;
            return host + prefix + p;
        }

        /// <summary>
        /// 规范化路径前缀: 去首尾空白, 保证以 / 开头且不以 / 结尾; 空则返回空串
        /// </summary>
        private static string NormalizePrefix(string prefix)
        {
            if (string.IsNullOrEmpty(prefix)) return "";
            prefix = prefix.Trim();
            if (prefix.Length == 0) return "";
            if (!prefix.StartsWith("/")) prefix = "/" + prefix;
            return prefix.TrimEnd('/');
        }

        /// <summary>
        /// 统一设置鉴权头 / redirectLimit / 超时
        /// </summary>
        private void Prepare(UnityWebRequest req, bool withAuth)
        {
            if (withAuth && !string.IsNullOrEmpty(_config.Authorization))
                req.SetRequestHeader(AuthHeader, _config.Authorization);
            // 禁止自动跟随重定向: 平台对未鉴权请求 302 跳登录页, 让其作为响应码直接暴露, 而非报 Redirect limit exceeded
            req.redirectLimit = 0;
            req.timeout = DefaultTimeoutSec;
        }
    }

    /// <summary>
    /// 响应的业务归类 (把 HTTP 码 + 网络错误翻译成语义)
    /// </summary>
    public enum LqaResponseKind
    {
        /// <summary>
        /// 请求尚未完成
        /// </summary>
        Pending,
        /// <summary>
        /// 成功 (2xx)
        /// </summary>
        Success,
        /// <summary>
        /// 鉴权未通过 (301/302/307/308 跳登录页, 或 401/403)
        /// </summary>
        AuthFailed,
        /// <summary>
        /// 网络层失败 (连不上 / 超时 / DNS / 非内网)
        /// </summary>
        NetworkError,
        /// <summary>
        /// 能连上但服务端返回其它错误 (其它 4xx/5xx)
        /// </summary>
        ServerError,
    }

    /// <summary>
    /// 一次 LQA 平台请求的句柄: 持有 UnityWebRequest, 调用方每帧 Poll 直至完成
    /// 完成后用 Kind/Code/Text/Error 读取结果, 设计为 "编辑器友好" (不依赖协程)
    /// </summary>
    public class LqaRequest
    {
        private UnityWebRequest _req;
        private UnityWebRequestAsyncOperation _op;

        /// <summary>
        /// 是否已完成
        /// </summary>
        public bool IsDone { get; private set; }
        /// <summary>
        /// HTTP 响应码 (完成后有效; 网络层失败时通常为 0)
        /// </summary>
        public long Code { get; private set; }
        /// <summary>
        /// 响应体文本 (完成且非纯二进制时有效)
        /// </summary>
        public string Text { get; private set; }
        /// <summary>
        /// 响应体原始字节 (下载 dump 等场景用)
        /// </summary>
        public byte[] Bytes { get; private set; }
        /// <summary>
        /// 底层错误信息 (成功时为空)
        /// </summary>
        public string Error { get; private set; }
        /// <summary>
        /// 业务归类
        /// </summary>
        public LqaResponseKind Kind { get; private set; }

        /// <summary>
        /// 创建并发起请求 (由 LqaApiClient 调用)
        /// </summary>
        internal static LqaRequest Send(UnityWebRequest req)
        {
            var r = new LqaRequest();
            r._req = req;
            r.Kind = LqaResponseKind.Pending;
            try
            {
                r._op = req.SendWebRequest();
            }
            catch (Exception e)
            {
                // 发送阶段就失败 (如明文 HTTP 被 Player Settings 禁止、URL 非法等):
                // 转成 "已完成的网络错误", 避免异常穿透调用方的 OnGUI 造成 GUILayout 状态错乱
                r.Error = e.Message;
                r.Kind = LqaResponseKind.NetworkError;
                r.IsDone = true;
                if (r._req != null) { r._req.Dispose(); r._req = null; }
                r._op = null;
            }
            return r;
        }

        /// <summary>
        /// 每帧轮询: 未完成返回 false; 本帧刚完成则解析结果并返回 true (幂等)
        /// 调用方通常在 EditorApplication.update 里调它
        /// </summary>
        public bool Poll()
        {
            if (IsDone) return true;
            if (_op == null || !_op.isDone) return false;

            try
            {
                Code = _req.responseCode;
                Error = _req.error;
                var dh = _req.downloadHandler;
                if (dh != null)
                {
                    Bytes = dh.data;
                    Text = dh.text;
                }
                Kind = Classify(_req, Code);
            }
            catch (Exception e)
            {
                Kind = LqaResponseKind.ServerError;
                Error = "处理响应异常: " + e.Message;
            }
            finally
            {
                if (_req != null) { _req.Dispose(); _req = null; }
                _op = null;
                IsDone = true;
            }
            return true;
        }

        /// <summary>
        /// 主动放弃并释放 (调用方取消时用)
        /// </summary>
        public void Abort()
        {
            if (_req != null)
            {
                try { _req.Abort(); } catch { }
                _req.Dispose();
                _req = null;
            }
            _op = null;
            IsDone = true;
        }

        /// <summary>
        /// 把 UnityWebRequest 结果翻译成业务归类
        /// </summary>
        private static LqaResponseKind Classify(UnityWebRequest req, long code)
        {
            if (code == 301 || code == 302 || code == 307 || code == 308) return LqaResponseKind.AuthFailed;
            if (code == 401 || code == 403) return LqaResponseKind.AuthFailed;
            if (HasNetworkError(req) && code == 0) return LqaResponseKind.NetworkError;
            if (code >= 200 && code < 300) return LqaResponseKind.Success;
            return LqaResponseKind.ServerError;
        }

        /// <summary>
        /// 请求底层是否连接/协议失败 (兼容不同 Unity 版本的 result 枚举)
        /// </summary>
        private static bool HasNetworkError(UnityWebRequest req)
        {
#if UNITY_2020_2_OR_NEWER
            return req.result == UnityWebRequest.Result.ConnectionError
                || req.result == UnityWebRequest.Result.ProtocolError
                || req.result == UnityWebRequest.Result.DataProcessingError;
#else
            return req.isNetworkError || req.isHttpError;
#endif
        }
    }
}