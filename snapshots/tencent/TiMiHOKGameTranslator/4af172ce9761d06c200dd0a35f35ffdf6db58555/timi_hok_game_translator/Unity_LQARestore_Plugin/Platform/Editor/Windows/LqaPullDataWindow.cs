// ==========================================
// 文件: LQARestore\Platform\Editor\Windows\LqaPullDataWindow.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using LQARestore.Core.Json;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// 拉取项目任务数据到本地 (EditorWindow)
    /// 职责: 按当前 "平台连接 + 项目 + 任务" 配置, 从平台拉取一批任务数据 (dump) 下载到本地,
    ///   并以平台的数据标识 (data_id) 命名每个文件
    /// 完整链路 (均由平台源码确认):
    ///   1. GET /api/job/datas?job_id=&language=&count=&minID=&module_ids=
    ///      -> data.datas = [{ id, file_path, module_id }]; id 即平台 data_id, file_path 是 gzip dump 的存储路径;
    ///   2. 逐条 GET {DownloadHost}{file_path} 下载 gzip 原始字节;
    ///   3. LqaDumpDecoder 三连解码 (魔数判定 -> GZip解压 -> 截断到最后 '}') 得 dump json;
    ///   4. 以 data_id 命名建子目录落盘: {persistentDataPath}/LQAPull/Job_{jobId}/{data_id}/{data_id}.json,
    ///      并把 dump 里的 bg_data(PNG hex) 还原为同目录下的 ScreenShot_NoText.png
    /// 依赖: LqaApiClient(HTTP) / LqaDumpDecoder(解码) / MiniJson+DictExt(解析清单与 bg_data) /
    ///   LqaPlatformConfig(连接) + LqaProjectConfig(项目) + LqaJobConfig(任务标识) + LqaFilterConfig(筛选变量)
    /// 编辑器内无 MonoBehaviour 主循环, 故用 EditorApplication.update 逐帧轮询请求句柄, 不用协程
    /// 本窗口做 "拉取+落盘+背景图还原"; UI 结构层面的还原仍是 RestoreEngine 的职责, 可另起功能对接
    /// </summary>
    public class LqaPullDataWindow : EditorWindow
    {
        /// <summary>
        /// 菜单入口: Tools/LQA/平台/单步/拉取任务数据...
        /// 打开 (或聚焦已存在的) 窗口, 锁定固定大小并在主编辑器内居中, 打开时先刷新一次配置快照
        /// </summary>
        [MenuItem("Tools/LQA/平台/单步/拉取任务数据...", false, 320)]
        public static void Open()
        {
            var win = GetWindow<LqaPullDataWindow>(true, "LQA 拉取任务数据", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 700);
            win.Refresh();
            win.Show();
        }

        // ==========================================
        // 配置快照 (打开/聚焦时从 EditorPrefs 刷新, 全程只读展示)
        // ==========================================

        /// <summary>
        /// 平台连接配置 (Host / DownloadHost / 鉴权令牌等)
        /// </summary>
        private LqaPlatformConfig _conn;

        /// <summary>
        /// 项目配置 (project_id 等)
        /// </summary>
        private LqaProjectConfig _proj;

        /// <summary>
        /// 任务配置 (job_id 任务批次标识)
        /// </summary>
        private LqaJobConfig _job;

        /// <summary>
        /// 筛选变量配置 (language/count/minID/module_ids)
        /// </summary>
        private LqaFilterConfig _filter;

        // ==========================================
        // 运行时状态
        // ==========================================

        /// <summary>
        /// 拉取流程的阶段: 就绪 -> 拉清单 -> 下载 -> 完成
        /// </summary>
        private enum Phase { Idle, FetchingList, Downloading, Done }

        /// <summary>
        /// 当前所处阶段, 决定 Tick 走哪条分支与 UI 展示
        /// </summary>
        private Phase _phase = Phase.Idle;

        /// <summary>
        /// 本次拉取使用的 HTTP 客户端 (StartPull 时按当前连接配置新建)
        /// </summary>
        private LqaApiClient _client;

        /// <summary>
        /// 拉清单的请求句柄 (每帧 Poll 直至完成)
        /// </summary>
        private LqaRequest _listReq;

        /// <summary>
        /// 当前正在下载的 dump 请求句柄 (每帧 Poll 直至完成)
        /// </summary>
        private LqaRequest _dumpReq;

        /// <summary>
        /// 待下载队列 (由清单解析填充)
        /// </summary>
        private readonly List<DataItem> _queue = new List<DataItem>();

        /// <summary>
        /// 当前处理到队列的第几个 (下载阶段游标)
        /// </summary>
        private int _index;

        /// <summary>
        /// 当前项已重试次数
        /// </summary>
        private int _retry;

        /// <summary>
        /// 单个数据项的最大尝试次数 (含首次), 达上限则跳过
        /// </summary>
        private const int MaxRetry = 3;

        /// <summary>
        /// 成功落盘条数 / 失败(跳过)条数, 用于进度与完成汇总
        /// </summary>
        private int _okCount, _failCount;

        /// <summary>
        /// 本次落盘的根目录 (以 job 分组)
        /// </summary>
        private string _outputDir = "";

        /// <summary>
        /// 日志区滚动位置
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 过程日志缓冲 (追加式, 显示在窗口底部)
        /// </summary>
        private readonly StringBuilder _log = new StringBuilder();

        /// <summary>
        /// 清单中的一条数据项
        /// </summary>
        private class DataItem
        {
            /// <summary>
            /// 平台数据标识 data_id, 用作本地文件/目录命名
            /// </summary>
            public int Id;

            /// <summary>
            /// 该条 dump 在平台的存储路径 (gzip), 供下载用
            /// </summary>
            public string FilePath;

            /// <summary>
            /// 所属模块 ID
            /// </summary>
            public string ModuleId;
        }

        /// <summary>
        /// 窗口重新获得焦点时: 仅在空闲/已完成状态刷新配置快照
        /// 避免在拉取进行中因用户在别处改配置而打断当前流程
        /// </summary>
        private void OnFocus() { if (_phase == Phase.Idle || _phase == Phase.Done) Refresh(); }

        /// <summary>
        /// 从 EditorPrefs 重新载入四份配置快照 (连接/项目/任务/筛选)
        /// </summary>
        private void Refresh()
        {
            _conn = LqaPlatformConfig.Load();
            _proj = LqaProjectConfig.Load();
            _job = LqaJobConfig.Load();
            _filter = LqaFilterConfig.Load();
        }

        /// <summary>
        /// IMGUI 绘制回调: 顶部说明 + 当前配置摘要(只读) + 操作区 + 状态/进度 + 日志
        /// </summary>
        private void OnGUI()
        {
            EditorGUILayout.LabelField("拉取任务数据到本地", EditorStyles.boldLabel);
            EditorGUILayout.HelpBox(
                "按当前 \"平台连接 + 项目 + 任务 + 筛选变量\" 配置拉取一批 Dump 数据到本地, 以平台数据标识 (data_id) 命名\n" +
                "配置分别在 Tools/LQA/平台/配置 的 平台连接 / 项目配置 / 任务配置 / 筛选变量 里设置",
                MessageType.Info);

            EditorGUILayout.Space(4);

            // 当前配置摘要 (只读展示, 空/未配置时给出引导文案)
            EditorGUILayout.LabelField("当前配置", EditorStyles.boldLabel);
            DrawReadonly("平台 Host (仅查看)", string.IsNullOrEmpty(_conn.Host) ? "(未配置, 去 平台连接 设置)" : _conn.Host);
            DrawReadonly("项目 ID (仅查看)", string.IsNullOrEmpty(_proj.ProjectId) || _proj.ProjectId == "0"
                ? "(未配置, 去 项目配置 设置)" : _proj.ProjectId);
            DrawReadonly("任务 ID (仅查看)", _job.IsIdle ? "(未配置或为0, 去 任务配置 设置)" : _job.JobId);
            DrawReadonly("筛选变量 (仅查看)", string.Format("语言={0}  数量={1}  最小ID={2}  模块ID={3}",
                _filter.Language, _filter.Count, _filter.MinID,
                string.IsNullOrEmpty(_filter.ModuleIds) ? "(空)" : _filter.ModuleIds));

            EditorGUILayout.Space(6);

            // 操作区: 拉取进行中禁用按钮, 防止重复发起; 有输出目录时可一键在文件管理器中打开
            using (new EditorGUI.DisabledScope(_phase == Phase.FetchingList || _phase == Phase.Downloading))
            {
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button("开始拉取", GUILayout.Height(28)))
                    StartPull();
                using (new EditorGUI.DisabledScope(string.IsNullOrEmpty(_outputDir) || !Directory.Exists(_outputDir)))
                {
                    if (GUILayout.Button("打开输出目录", GUILayout.Width(120), GUILayout.Height(28)))
                        EditorUtility.RevealInFinder(_outputDir);
                }
                EditorGUILayout.EndHorizontal();
            }

            // 仅在进行中显示取消按钮
            if (_phase == Phase.FetchingList || _phase == Phase.Downloading)
            {
                if (GUILayout.Button("取消", GUILayout.Height(22)))
                    CancelPull("已取消");
            }

            EditorGUILayout.Space(4);

            // 状态/进度: 按当前阶段拼一句人类可读的状态文案
            string status;
            switch (_phase)
            {
                case Phase.FetchingList: status = "正在拉取任务数据清单..."; break;
                case Phase.Downloading: status = string.Format("正在下载 {0}/{1} (成功 {2}, 失败 {3})",
                    _index + 1, _queue.Count, _okCount, _failCount); break;
                case Phase.Done: status = string.Format("完成: 共 {0} 条, 成功 {1}, 失败 {2}",
                    _queue.Count, _okCount, _failCount); break;
                default: status = "就绪"; break;
            }
            EditorGUILayout.LabelField("状态", status);
            if (!string.IsNullOrEmpty(_outputDir))
                DrawReadonly("输出目录 (仅查看)", _outputDir);

            // 日志区: 独立 ScrollView, 上半部分固定不动, 仅此区域随内容滚动 (对齐上传窗口)
            if (_log.Length > 0)
            {
                EditorGUILayout.Space(4);
                EditorGUILayout.LabelField("日志", EditorStyles.boldLabel);
                _scroll = EditorGUILayout.BeginScrollView(_scroll, GUILayout.ExpandHeight(true));
                string logText = _log.ToString();
                // 按内容真实高度绘制: 内容多则可滚动、不裁剪; 内容少则不硬撑留白
                // 预留约 25px 给竖向滚动条, 使换行宽度与实际绘制宽度一致
                float logWidth = EditorGUIUtility.currentViewWidth - 25f;
                float logHeight = EditorStyles.textArea.CalcHeight(new GUIContent(logText), logWidth);
                EditorGUILayout.SelectableLabel(logText, EditorStyles.textArea,
                    GUILayout.Width(logWidth), GUILayout.Height(logHeight));
                EditorGUILayout.EndScrollView();
            }
        }

        /// <summary>
        /// 绘制一行 "只读键值": 左侧前缀标签 + 右侧可选中复制但不可编辑的文本域
        /// </summary>
        /// <param name="label">左侧字段名</param>
        /// <param name="value">右侧只读值</param>
        private void DrawReadonly(string label, string value)
        {
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PrefixLabel(label);
            EditorGUILayout.SelectableLabel(value, EditorStyles.textField,
                GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();
        }

        // ==========================================
        // 拉取流程: 校验 -> 拉清单 -> 逐条下载落盘
        // ==========================================

        /// <summary>
        /// "开始拉取": 刷新配置 -> 前置校验 -> 重置运行时状态 -> 建输出目录 -> 发起清单请求 -> 挂载逐帧轮询
        /// </summary>
        private void StartPull()
        {
            Refresh();

            // 前置校验: Host 与 JobId 是发起拉取的必要条件, 缺失直接失败并引导用户去配置
            if (string.IsNullOrEmpty(_conn.Host))
            {
                Fail("平台 Host 未配置, 请先去 Tools/LQA/平台/配置/平台连接 设置");
                return;
            }
            if (_job.IsIdle)
            {
                Fail("任务 ID 未配置或为 0, 请先去 Tools/LQA/平台/配置/任务配置 设置一个真实任务批次号");
                return;
            }

            // 重置状态: 清空队列/计数/日志, 并按当前连接配置新建客户端
            _queue.Clear();
            _index = 0; _retry = 0; _okCount = 0; _failCount = 0;
            _log.Length = 0;
            _client = new LqaApiClient(_conn);

            // 输出目录: 以 job 分组, 便于区分不同批次
            _outputDir = Path.Combine(
                Application.persistentDataPath, "LQAPull", "Job_" + Sanitize(_job.JobId));
            try { Directory.CreateDirectory(_outputDir); }
            catch (System.Exception e) { Fail("创建输出目录失败: " + e.Message); return; }

            AppendLog("输出目录: " + _outputDir);
            AppendLog("拉取清单: 任务ID=" + _job.JobId + " 语言=" + _filter.Language +
                      " 数量=" + _filter.Count + " 最小ID=" + _filter.MinID);

            // 发起清单请求, 进入拉清单阶段, 并把 Tick 挂到 EditorApplication.update 逐帧轮询 (先减后加防重复挂载)
            _listReq = _client.GetJobDatas(_job.JobId, _filter.Language,
                                           _filter.Count, _filter.MinID, _filter.ModuleIds);
            _phase = Phase.FetchingList;
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            Repaint();
        }

        /// <summary>
        /// 逐帧轮询总入口 (挂在 EditorApplication.update 上): 按当前阶段分派到拉清单/下载处理
        /// </summary>
        private void Tick()
        {
            if (_phase == Phase.FetchingList) TickFetchList();
            else if (_phase == Phase.Downloading) TickDownload();
        }

        /// <summary>
        /// 拉清单阶段的每帧处理: 等清单请求完成 -> 校验结果 -> 解析清单 -> 无数据则结束/有数据进入下载
        /// </summary>
        private void TickFetchList()
        {
            // 未完成则本帧不处理
            if (_listReq == null || !_listReq.Poll()) return;

            // 非 2xx 一律判失败, 附带原因与明细
            if (_listReq.Kind != LqaResponseKind.Success)
            {
                Fail("拉取清单失败: " + DescribeKind(_listReq) + BuildDetail(_listReq));
                _listReq = null;
                return;
            }

            string body = _listReq.Text;
            _listReq = null;

            // 解析 { code, data: { datas: [{id, file_path, module_id}] } }
            int parsed = ParseList(body);
            if (parsed < 0) { Fail("清单解析失败: 响应不是预期的 JSON 结构"); return; }

            AppendLog("清单解析成功, 共 " + parsed + " 条待下载");
            if (parsed == 0)
            {
                // 结构正常但 0 条: 常见于 minID 已越过全部 data_id, 或该 job 本就无数据
                AppendLog("没有符合条件的数据 (检查 最小ID 是否已越过全部 数据ID, 或该 任务 是否有数据)");
                Finish();
                return;
            }

            // 进入下载阶段, 从队首开始
            _index = 0; _retry = 0;
            _phase = Phase.Downloading;
            BeginDownloadCurrent();
        }

        /// <summary>解析清单, 填充 _queue; 返回条数, 结构异常返回 -1</summary>
        /// <param name="body">清单接口返回的 JSON 文本</param>
        /// <returns>有效数据条数; 顶层/ data 结构异常返回 -1; 有 data 但无 datas 视为 0</returns>
        private int ParseList(string body)
        {
            // 顶层必须是对象, 解析失败或非对象即视为结构异常
            object root = null;
            try { root = MiniJson.Parse(body); } catch { }
            var rootDict = root as Dictionary<string, object>;
            if (rootDict == null) return -1;

            var data = rootDict.Get<Dictionary<string, object>>("data");
            if (data == null) return -1;

            var datas = data.Get<List<object>>("datas");
            if (datas == null) return 0;  // 有 data 但无 datas, 视为 0 条

            // 逐条转成 DataItem; 跳过 id 或 file_path 缺失的无效项
            foreach (var o in datas)
            {
                var d = o as Dictionary<string, object>;
                if (d == null) continue;
                var item = new DataItem
                {
                    Id = d.GetInnerInt("id", 0),
                    FilePath = d.GetInnerString("file_path", ""),
                    ModuleId = d.GetInnerString("module_id", ""),
                };
                if (item.Id <= 0 || string.IsNullOrEmpty(item.FilePath))
                {
                    AppendLog("跳过一条无效项 (数据ID 或 文件路径 缺失)");
                    continue;
                }
                _queue.Add(item);
            }
            return _queue.Count;
        }

        /// <summary>
        /// 为队列当前项发起 dump 下载请求, 并记一条进度日志
        /// </summary>
        private void BeginDownloadCurrent()
        {
            var item = _queue[_index];
            AppendLog(string.Format("[{0}/{1}] 下载 数据ID={2}  {3}",
                _index + 1, _queue.Count, item.Id, item.FilePath));
            _dumpReq = _client.DownloadDataDump(item.FilePath);
            Repaint();
        }

        /// <summary>
        /// 下载阶段的每帧处理: 等 dump 请求完成 -> 成功则解码/落盘/还原背景图并推进, 失败则重试或跳过
        /// </summary>
        private void TickDownload()
        {
            // 未完成则本帧不处理
            if (_dumpReq == null || !_dumpReq.Poll()) return;

            var item = _queue[_index];

            if (_dumpReq.Kind == LqaResponseKind.Success)
            {
                byte[] raw = _dumpReq.Bytes;
                _dumpReq = null;
                try
                {
                    // 三连解码得到干净 dump json
                    string json = LqaDumpDecoder.Decode(raw);
                    // 以平台标识 (data_id) 命名建子目录, json 与还原的背景图都放进去
                    string itemDir = Path.Combine(_outputDir, item.Id.ToString());
                    Directory.CreateDirectory(itemDir);
                    string path = Path.Combine(itemDir, item.Id + ".json");
                    // 用无 BOM 的 UTF-8 写出, 避免下游解析对 BOM 敏感
                    File.WriteAllText(path, json, new UTF8Encoding(false));
                    _okCount++;
                    AppendLog("  -> 保存成功: " + item.Id + "/" + item.Id + ".json (" + json.Length + " 字符)");
                    TryRestoreBackground(itemDir, json);  // 新增: 还原纯背景图
                    AdvanceNext();
                }
                catch (System.Exception e)
                {
                    // 解码或落盘出错: 走重试/跳过逻辑
                    AppendLog("  -> 解码/落盘失败: " + e.Message);
                    RetryOrSkip(item);
                }
            }
            else
            {
                // 下载本身失败 (鉴权/网络/服务端): 走重试/跳过逻辑
                string detail = DescribeKind(_dumpReq) + BuildDetail(_dumpReq);
                _dumpReq = null;
                AppendLog("  -> 下载失败: " + detail);
                RetryOrSkip(item);
            }
        }

        /// <summary>当前项重试或跳过, 然后推进</summary>
        /// <param name="item">当前处理的数据项 (仅用于日志)</param>
        private void RetryOrSkip(DataItem item)
        {
            // 未达上限则原地重试同一项; 达上限则计失败并推进到下一项
            if (_retry < MaxRetry - 1)
            {
                _retry++;
                AppendLog("  -> 重试 " + _retry + "/" + (MaxRetry - 1) + " ...");
                BeginDownloadCurrent();
            }
            else
            {
                _failCount++;
                AppendLog("  -> 达重试上限, 跳过 数据ID=" + item.Id);
                AdvanceNext();
            }
        }

        /// <summary>
        /// 推进到队列下一项: 重置重试计数; 队列走完则收尾, 否则发起下一项下载
        /// </summary>
        private void AdvanceNext()
        {
            _index++;
            _retry = 0;
            if (_index >= _queue.Count) { Finish(); return; }
            BeginDownloadCurrent();
        }

        /// <summary>
        /// 正常收尾: 摘除逐帧轮询, 置完成态, 打印汇总, 刷新资源库并重绘
        /// </summary>
        private void Finish()
        {
            EditorApplication.update -= Tick;
            _phase = Phase.Done;
            AppendLog(string.Format("== 完成: 共 {0} 条, 成功 {1}, 失败 {2} ==",
                _queue.Count, _okCount, _failCount));
            AssetDatabase.Refresh();
            Repaint();
        }

        /// <summary>
        /// 用户主动取消: 摘除轮询, 中止在途请求并释放, 置完成态并记原因
        /// </summary>
        /// <param name="reason">取消原因 (写入日志)</param>
        private void CancelPull(string reason)
        {
            EditorApplication.update -= Tick;
            if (_listReq != null) { _listReq.Abort(); _listReq = null; }
            if (_dumpReq != null) { _dumpReq.Abort(); _dumpReq = null; }
            _phase = Phase.Done;
            AppendLog("== " + reason + " ==");
            Repaint();
        }

        /// <summary>
        /// 因错误终止: 摘除轮询, 中止在途请求并释放, 置完成态并记错误信息
        /// </summary>
        /// <param name="msg">错误描述 (写入日志)</param>
        private void Fail(string msg)
        {
            EditorApplication.update -= Tick;
            if (_listReq != null) { _listReq.Abort(); _listReq = null; }
            if (_dumpReq != null) { _dumpReq.Abort(); _dumpReq = null; }
            _phase = Phase.Done;
            AppendLog("[错误] " + msg);
            Repaint();
        }

        // ==========================================
        // 辅助
        // ==========================================

        /// <summary>
        /// 向日志缓冲追加一行并触发重绘, 使日志实时可见
        /// </summary>
        /// <param name="line">日志内容 (自动换行)</param>
        private void AppendLog(string line)
        {
            _log.AppendLine(line);
            Repaint();
        }

        /// <summary>把 Kind 翻译成人类可读的原因</summary>
        /// <param name="req">已完成的请求句柄</param>
        /// <returns>该失败归类对应的中文原因描述</returns>
        private static string DescribeKind(LqaRequest req)
        {
            switch (req.Kind)
            {
                case LqaResponseKind.AuthFailed:
                    return "鉴权未通过 (JWT 无效/过期, 或被 302 跳登录页)";
                case LqaResponseKind.NetworkError:
                    return "网络不可达 (检查 Host / 是否在内网)";
                case LqaResponseKind.ServerError:
                    return "服务端错误";
                default:
                    return "未知";
            }
        }

        /// <summary>
        /// 拼接失败明细: 有 HTTP 码则附 [HTTP xxx], 有底层错误则附错误文本
        /// </summary>
        /// <param name="req">已完成的请求句柄</param>
        /// <returns>形如 " [HTTP 500] xxx" 的补充明细 (可能为空)</returns>
        private static string BuildDetail(LqaRequest req)
        {
            var sb = new StringBuilder();
            if (req.Code > 0) sb.Append(" [HTTP ").Append(req.Code).Append("]");
            if (!string.IsNullOrEmpty(req.Error)) sb.Append(" ").Append(req.Error);
            return sb.ToString();
        }

        /// <summary>清洗成安全的文件夹名片段 (防止 JobId 里有异常字符)</summary>
        /// <param name="s">原始字符串 (通常是 JobId)</param>
        /// <returns>非法文件名字符被替换为 '_' 的安全片段; 空则返回 "0"</returns>
        private static string Sanitize(string s)
        {
            if (string.IsNullOrEmpty(s)) return "0";
            foreach (char c in Path.GetInvalidFileNameChars())
                s = s.Replace(c, '_');
            return s;
        }

        /// <summary>从 dump json 取出 bg_data(PNG 的 hex), 还原成纯背景图 ScreenShot_NoText.png</summary>
        /// <param name="itemDir">该数据项的落盘子目录 (背景图写入此处)</param>
        /// <param name="json">已解码的 dump json 文本</param>
        private void TryRestoreBackground(string itemDir, string json)
        {
            // 解析 dump 取 bg_data (PNG 的 hex 编码); 无此字段则跳过, 属正常情况
            object root = null;
            try { root = MiniJson.Parse(json); } catch { }
            var dict = root as Dictionary<string, object>;
            string hex = dict.GetInnerString("bg_data", "");
            if (string.IsNullOrEmpty(hex))
            {
                AppendLog("  -> 无 bg_data, 跳过背景图还原");
                return;
            }
            try
            {
                // hex -> 字节 -> 写为 PNG 文件
                byte[] png = HexToBytes(hex);
                string bgPath = Path.Combine(itemDir, "ScreenShot_NoText.png");
                File.WriteAllBytes(bgPath, png);
                AppendLog("  -> 背景图还原成功: ScreenShot_NoText.png (" + png.Length + " 字节)");
            }
            catch (System.Exception e)
            {
                // 背景图还原失败不影响 json 已保存成功, 仅记日志
                AppendLog("  -> 背景图还原失败: " + e.Message);
            }
        }

        /// <summary>hex 字符串转字节 (与上传侧 ToHex 互逆; 逐字符解析, 避免大字符串 Substring 开销)</summary>
        /// <param name="hex">十六进制字符串 (长度须为偶数)</param>
        /// <returns>解析出的字节数组; 空输入返回空数组</returns>
        /// <exception cref="System.Exception">长度非偶数或含非法 hex 字符时抛出</exception>
        private static byte[] HexToBytes(string hex)
        {
            if (string.IsNullOrEmpty(hex)) return new byte[0];
            if ((hex.Length & 1) != 0) throw new System.Exception("bg_data hex 长度非偶数");
            var bytes = new byte[hex.Length / 2];
            // 每两个 hex 字符合成一个字节 (高 4 位 + 低 4 位)
            for (int i = 0; i < bytes.Length; i++)
            {
                int hi = HexVal(hex[i * 2]);
                int lo = HexVal(hex[i * 2 + 1]);
                if (hi < 0 || lo < 0) throw new System.Exception("bg_data 含非法 hex 字符");
                bytes[i] = (byte)((hi << 4) | lo);
            }
            return bytes;
        }

        /// <summary>
        /// 单个 hex 字符转 0-15 的数值 (兼容大小写), 非法字符返回 -1
        /// </summary>
        /// <param name="c">十六进制字符 0-9/a-f/A-F</param>
        /// <returns>对应数值 0-15; 非法字符返回 -1</returns>
        private static int HexVal(char c)
        {
            if (c >= '0' && c <= '9') return c - '0';
            if (c >= 'a' && c <= 'f') return c - 'a' + 10;
            if (c >= 'A' && c <= 'F') return c - 'A' + 10;
            return -1;
        }
    }
}