// ==========================================
// 文件: LQARestore\Platform\Editor\Windows\LqaAutoPipelineWindow.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using LQARestore.Core;
using LQARestore.Core.Editor;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 自动化流水线 (EditorWindow)
    /// 把前面几个 "手动菜单" 串成一条自动循环, 无需人工逐步操作:
    ///   监控任务数据 (轮询 GET /api/job/datas) → 有数据则逐条: 下载 dump → 解码落盘 → 还原并截图/导框
    ///   → 提交结果 (POST /api/image/entity) → 全部处理完毕后继续监控下一批
    /// 复用已有能力 (不重复造轮子):
    ///   - LqaApiClient.GetJobDatas / DownloadDataDump / UploadImageEntity (HTTP);
    ///   - LqaDumpDecoder (gzip 三连解码);
    ///   - RestoreEngine.RestoreFromDump (同步还原, 内部截图 Restore.png + 导出 rect_locations.json)
    /// 配置来源: Host/JWT(Platform)、project_id(Project)、job_id(Job)、language/count/module_ids(Filter)
    ///   language 用筛选窗口选定的平台数字码; minID 由本窗口自动推进 (处理过的最大 data_id), 无需手填
    /// 编辑器内无 MonoBehaviour 主循环, 全程用 EditorApplication.update 驱动状态机, 不用协程
    /// 还原是编辑器态能力 (依赖 EditorSceneHost/AssetDatabase), 故整条流水线只在 Unity 编辑器内运行
    /// </summary>
    public class LqaAutoPipelineWindow : EditorWindow
    {
        /// <summary>
        /// 打开窗口的菜单入口 (Tools/LQA/平台/自动化/自动化流水线...)
        /// 创建 (或聚焦) 窗口后固定尺寸并居中, 打开时先刷新一次四类配置快照再显示
        /// </summary>
        [MenuItem("Tools/LQA/平台/自动化/自动化流水线...", false, 340)]
        public static void Open()
        {
            var win = GetWindow<LqaAutoPipelineWindow>(false, "LQA 自动化流水线", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 700);
            win.Refresh();
            win.Show();
        }

        // ==========================================
        // 配置快照 (启动/刷新时从各自持久化配置读取一次, 运行期不再变更)
        // ==========================================

        /// <summary>
        /// 平台连接配置 (Host / DownloadHost / 鉴权令牌), 决定请求发往哪个平台
        /// </summary>
        private LqaPlatformConfig _conn;

        /// <summary>
        /// 项目配置 (project_id), 提交结果时关联到的项目上下文
        /// </summary>
        private LqaProjectConfig _proj;

        /// <summary>
        /// 任务配置 (job_id), 指定监控/拉取哪个任务批次的数据
        /// </summary>
        private LqaJobConfig _job;

        /// <summary>
        /// 筛选配置 (language / count / minID / module_ids), 决定 "怎么从任务里筛数据"
        /// </summary>
        private LqaFilterConfig _filter;

        /// <summary>
        /// 提交配置 (提供 ai_sign 开关), 提交结果时决定是否触发平台 AI 检测
        /// </summary>
        private LqaSubmitConfig _submit;

        // ==========================================
        // 可调参数 (仅停机态可改, 运行期锁定)
        // ==========================================

        /// <summary>
        /// 监控轮询间隔 (秒): 两轮监控之间的等待时间, 范围 5~300, 默认 30
        /// </summary>
        private float _monitorInterval = 30f;

        /// <summary>
        /// 还原后是否自动提交: 关掉则只拉取+还原(供人工核对), 不走提交步骤
        /// </summary>
        private bool _autoSubmit = true;

        // ==========================================
        // 运行状态机
        // ==========================================

        /// <summary>
        /// 流水线阶段枚举:
        ///   Stopped 未运行;
        ///   Monitoring 等待到点并发起监控请求;
        ///   ListPending 监控请求进行中(等清单返回);
        ///   Downloading 处理当前条目: 下载 dump(下载完成后同步还原);
        ///   Submitting 处理当前条目: 提交还原结果
        /// </summary>
        private enum Phase { Stopped, Monitoring, ListPending, Downloading, Submitting }

        /// <summary>
        /// 当前流水线阶段, 由 Tick 驱动流转
        /// </summary>
        private Phase _phase = Phase.Stopped;

        /// <summary>
        /// 平台客户端 (启动时按连接配置构造, 全程复用)
        /// </summary>
        private LqaApiClient _client;

        /// <summary>
        /// 当前进行中的 HTTP 请求句柄 (监控/下载/提交三种请求复用同一字段, 同一时刻只有一个在飞)
        /// </summary>
        private LqaRequest _req;

        /// <summary>
        /// 下次发起监控的时间点 (以 EditorApplication.timeSinceStartup 为基准)
        /// </summary>
        private double _nextMonitorTime;

        /// <summary>
        /// 还原引擎实例 (启动时构造, 逐条还原时复用同一实例)
        /// </summary>
        private RestoreEngine _engine;

        /// <summary>
        /// 本次运行使用的译文文件路径 (启动时从持久化配置读一次; 空 = 用原文还原)
        /// </summary>
        private string _translationPath;

        /// <summary>
        /// 本次运行使用的字体变体模板 (启动时读一次; 空 = 字体按 dump 原样还原)
        /// </summary>
        private string _fontVariantTemplate;

        /// <summary>
        /// 当前批次待处理队列 (由一次监控返回的 datas 解析而来, 逐条消费)
        /// </summary>
        private readonly List<DataItem> _queue = new List<DataItem>();

        /// <summary>
        /// _qIndex: 队列中当前处理到的下标; _retry: 当前条目已重试次数
        /// </summary>
        private int _qIndex, _retry;

        /// <summary>
        /// 单条目的最大尝试次数 (含首次): 达到即跳过该条
        /// </summary>
        private const int MaxRetry = 3;

        /// <summary>
        /// 当前条目落盘后的 dump json 路径 (还原/提交都基于其所在目录读写)
        /// </summary>
        private string _curJsonPath;

        /// <summary>
        /// 当前条目的平台 data_id (字符串形式, 用于日志与提交)
        /// </summary>
        private string _curDataId;

        // ==========================================
        // 统计与游标
        // ==========================================

        /// <summary>
        /// 运行以来累计: 拉取 / 还原 / 提交 / 失败 条数 (界面统计栏显示)
        /// </summary>
        private int _totalPulled, _totalRestored, _totalSubmitted, _totalFailed;

        /// <summary>
        /// 已处理过的最大 data_id, 作为下次监控请求的 minID, 避免重复领取
        /// </summary>
        private long _minIdCursor;

        /// <summary>
        /// 日志区滚动位置
        /// </summary>
        private Vector2 _scrollLog;

        /// <summary>
        /// 运行日志缓冲 (界面日志区显示的文本源)
        /// </summary>
        private readonly StringBuilder _log = new StringBuilder();

        /// <summary>
        /// 单条待处理数据: Id(平台 data_id)、FilePath(平台 dump 存储路径)、ModuleId(所属模块)
        /// </summary>
        private class DataItem { public int Id; public string FilePath; public string ModuleId; }

        /// <summary>
        /// 窗口失活/关闭时停止流水线, 防止后台状态机继续跑或请求悬挂
        /// </summary>
        private void OnDisable() { StopInternal(); }

        /// <summary>
        /// 窗口获得焦点时, 若处于停机态则刷新一次配置快照 (让界面显示最新的四类配置)
        /// </summary>
        private void OnFocus() { if (_phase == Phase.Stopped) Refresh(); }

        /// <summary>
        /// 重新读取平台/项目/任务/筛选四类持久化配置到本地快照
        /// </summary>
        private void Refresh()
        {
            _conn = LqaPlatformConfig.Load();
            _proj = LqaProjectConfig.Load();
            _job = LqaJobConfig.Load();
            _filter = LqaFilterConfig.Load();
            _submit = LqaSubmitConfig.Load();
        }

        /// <summary>
        /// EditorWindow 的 IMGUI 绘制回调: 顶部说明 + 只读配置回显 + 可调参数 + 启停按钮 + 状态/统计/日志
        /// </summary>
        private void OnGUI()
        {
            // 点击空白处时取消输入框焦点, 避免键盘控制停留在某个控件上
            if (Event.current != null && Event.current.type == EventType.MouseDown)
                GUIUtility.keyboardControl = 0;

            EditorGUILayout.LabelField("自动化流水线", EditorStyles.boldLabel);
            Rect helpRect = EditorGUILayout.GetControlRect(false, 62f);
            EditorGUI.HelpBox(helpRect,
                "自动循环: 监控任务数据 → 有数据则逐条 下载→还原(截图+导框)→提交 → 继续监控,\n" +
                "配置取自 平台连接/项目配置/任务配置/筛选变量/提交配置 及 译文文件/字体变体 配置 (语言码 用筛选里选的平台码, 最小ID 自动推进),\n" +
                "整条流水线在编辑器内运行 (还原依赖编辑器); 关闭窗口即停止",
                MessageType.Info);

            // 只读回显当前生效的四类配置, 便于启动前核对
            EditorGUILayout.Space(2);
            DrawReadonly("平台 Host (仅查看)", string.IsNullOrEmpty(_conn.Host) ? "(未配置)" : _conn.Host);
            DrawReadonly("项目 ID (仅查看)", _proj.ProjectId);
            DrawReadonly("任务 ID (仅查看)", _job.JobId);
            DrawReadonly("语言码 (仅查看)", string.IsNullOrEmpty(_filter.Language) ? "(未选, 去 筛选变量 拉取选择)" : _filter.Language);
            DrawReadonly("筛选 (仅查看)", string.Format("数量={0}  模块ID={1}  最小ID(游标)={2}",
                _filter.Count,
                string.IsNullOrEmpty(_filter.ModuleIds) ? "(空)" : _filter.ModuleIds, _minIdCursor));
            DrawReadonly("译文文件 (仅查看)", string.IsNullOrEmpty(LqaTranslationConfig.GetPath())
                ? "(未配置, 用原文还原)" : LqaTranslationConfig.GetPath());

            EditorGUILayout.Space(4);

            // 运行中禁用可调参数, 只有停机态才允许修改间隔与自动提交开关
            using (new EditorGUI.DisabledScope(_phase != Phase.Stopped))
            {
                _monitorInterval = EditorGUILayout.Slider(
                    new GUIContent("监控间隔 (秒)", "两轮监控之间的等待时间"), _monitorInterval, 5f, 300f);
                _autoSubmit = EditorGUILayout.Toggle(
                    new GUIContent("还原后自动提交", "关闭则只监控+拉取+还原, 提交留人工 (用 \"提交还原结果\" 菜单)"), _autoSubmit);
            }

            EditorGUILayout.Space(6);

            // 启停按钮随阶段切换: 停机显示 "启动", 其余显示 "停止"
            if (_phase == Phase.Stopped)
            {
                if (GUILayout.Button("启动流水线", GUILayout.Height(30))) StartPipeline();
            }
            else
            {
                if (GUILayout.Button("停止流水线", GUILayout.Height(30))) { StopInternal(); AppendLog("== 已停止 =="); }
            }

            EditorGUILayout.Space(4);
            EditorGUILayout.LabelField("状态", PhaseText());
            EditorGUILayout.LabelField("统计", string.Format(
                "拉取 {0} / 还原 {1} / 提交 {2} / 失败 {3}", _totalPulled, _totalRestored, _totalSubmitted, _totalFailed));

            // 有日志时才绘制可滚动的日志区
            if (_log.Length > 0)
            {
                EditorGUILayout.LabelField("日志", EditorStyles.boldLabel);
                _scrollLog = EditorGUILayout.BeginScrollView(_scrollLog, GUILayout.ExpandHeight(true));
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
        /// 绘制一行 "标签 + 只读可选中文本" (用文本框样式呈现, 方便复制但不可编辑)
        /// </summary>
        /// <param name="label">左侧前缀标签</param>
        /// <param name="value">右侧显示值 (null 视为空串)</param>
        private void DrawReadonly(string label, string value)
        {
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PrefixLabel(label);
            EditorGUILayout.SelectableLabel(value ?? "", EditorStyles.textField,
                GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();
        }

        /// <summary>
        /// 把当前阶段翻译成界面状态栏的人类可读文本 (监控倒计时 / 清单获取中 / 第几条下载或提交)
        /// </summary>
        private string PhaseText()
        {
            switch (_phase)
            {
                case Phase.Monitoring:
                    double wait = _nextMonitorTime - EditorApplication.timeSinceStartup;
                    return wait > 0 ? string.Format("监控中: {0:0}s 后拉取下一批", wait) : "监控中: 即将拉取";
                case Phase.ListPending:  return "监控中: 正在获取任务清单...";
                case Phase.Downloading:  return string.Format("处理中 {0}/{1}: 下载 数据ID={2}", _qIndex + 1, _queue.Count, _curDataId);
                case Phase.Submitting:   return string.Format("处理中 {0}/{1}: 提交 数据ID={2}", _qIndex + 1, _queue.Count, _curDataId);
                default:                 return "已停止";
            }
        }

        // ==========================================
        // 启停
        // ==========================================

        /// <summary>
        /// 启动流水线: 校验必填配置 → 构造客户端与还原引擎 → 重置统计与游标 →
        /// 读取译文/字体变体配置 → 挂接 EditorApplication.update 状态机 → 立即发起首次监控
        /// 任一前置校验失败则记日志并中止, 不进入运行态
        /// </summary>
        private void StartPipeline()
        {
            Refresh();
            // 前置校验: Host / Job / Project 必填; 自动提交额外要求 Language 为有效数字码
            if (string.IsNullOrEmpty(_conn.Host)) { AppendLog("[错误] 平台 Host 未配置 (平台连接)"); return; }
            if (_job.IsIdle) { AppendLog("[错误] 任务 ID 未配置或为 0 (任务配置)"); return; }
            if (string.IsNullOrEmpty(_proj.ProjectId) || _proj.ProjectId == "0") { AppendLog("[错误] 项目 ID 未配置 (项目配置)"); return; }
            if (_autoSubmit && !IsAllDigits(_filter.Language)) { AppendLog("[错误] 自动提交需要有效 语言码 (去 筛选变量 拉取选择)"); return; }

            _client = new LqaApiClient(_conn);
            _engine = new RestoreEngine(new EditorFontResolver(), new EditorSceneHost());
            _totalPulled = _totalRestored = _totalSubmitted = _totalFailed = 0;
            // minID 初始取筛选配置 (可为 0), 之后自动推进
            long.TryParse(_filter.MinID, out _minIdCursor);

            // 读取持久化的译文文件配置 (译文文件配置窗口设置); 路径失效则回退原文还原
            _translationPath = LqaTranslationConfig.GetPath();
            if (!string.IsNullOrEmpty(_translationPath) && !File.Exists(_translationPath))
            {
                _translationPath = null;
            }

            // 读取持久化的字体变体模板 (字体变体配置窗口设置); 空=字体按 dump 原样还原
            _fontVariantTemplate = LqaFontVariantConfig.GetTemplate();

            _log.Length = 0;
            AppendLog("== 流水线启动 (间隔 " + _monitorInterval + "s, 自动提交=" + _autoSubmit
                      + ", 译文=" + (string.IsNullOrEmpty(_translationPath) ? "原文" : _translationPath)
                      + ", 字体变体=" + (string.IsNullOrEmpty(_fontVariantTemplate) ? "无" : _fontVariantTemplate) + ") ==");

            // 先摘再挂, 避免重复订阅导致 Tick 被多次调用
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            // 立即发起第一次监控
            _nextMonitorTime = EditorApplication.timeSinceStartup;
            _phase = Phase.Monitoring;
            Repaint();
        }

        /// <summary>
        /// 停止流水线并复位: 摘除状态机回调 → 中止并释放在飞请求 → 清空队列 → 回到停机态
        /// (统计与游标不清零, 便于停机后查看结果)
        /// </summary>
        private void StopInternal()
        {
            EditorApplication.update -= Tick;
            if (_req != null) { _req.Abort(); _req = null; }
            _queue.Clear();
            _phase = Phase.Stopped;
        }

        // ==========================================
        // 状态机主循环
        // ==========================================

        /// <summary>
        /// 挂在 EditorApplication.update 上的每帧驱动: 按当前阶段分派到对应的 Tick 处理
        /// </summary>
        private void Tick()
        {
            switch (_phase)
            {
                case Phase.Monitoring:  TickMonitoring();  break;
                case Phase.ListPending: TickListPending(); break;
                case Phase.Downloading: TickDownloading(); break;
                case Phase.Submitting:  TickSubmitting();  break;
            }
        }

        /// <summary>
        /// 监控阶段: 未到点只刷新倒计时显示; 到点则发起 GET /api/job/datas 并切到 ListPending
        /// </summary>
        private void TickMonitoring()
        {
            // 到点才发起监控请求, 否则刷新一下倒计时显示
            if (EditorApplication.timeSinceStartup < _nextMonitorTime) { Repaint(); return; }

            AppendLog("[监控] 拉取清单 (最小ID>" + _minIdCursor + ", 数量=" + _filter.Count + ") ...");
            _req = _client.GetJobDatas(_job.JobId, _filter.Language,
                                       _filter.Count, _minIdCursor.ToString(), _filter.ModuleIds);
            _phase = Phase.ListPending;
            Repaint();
        }

        /// <summary>
        /// 等清单返回: 请求未完成直接返回; 失败则排下一轮监控; 成功则解析队列,
        /// 无数据排下一轮监控, 有数据则累计并开始逐条下载
        /// </summary>
        private void TickListPending()
        {
            if (_req == null || !_req.Poll()) return;

            if (_req.Kind != LqaResponseKind.Success)
            {
                AppendLog("  -> 监控请求失败: " + Describe(_req) + " (稍后重试)");
                _req = null;
                ScheduleNextMonitor();
                return;
            }

            string body = _req.Text;
            _req = null;
            int n = ParseList(body);
            if (n <= 0)
            {
                AppendLog("  -> 暂无新数据");
                ScheduleNextMonitor();
                return;
            }

            AppendLog("  -> 发现 " + n + " 条新数据, 开始处理");
            _totalPulled += n;
            _qIndex = 0; _retry = 0;
            BeginItemDownload();
        }

        /// <summary>
        /// 解析监控返回体 data.datas[] 填充待处理队列; 跳过缺 id/file_path 的无效条目, 返回入队条数
        /// </summary>
        /// <param name="body">GET /api/job/datas 的响应体 JSON</param>
        private int ParseList(string body)
        {
            _queue.Clear();
            object root = null;
            try { root = MiniJson.Parse(body); } catch { }
            var rootDict = root as Dictionary<string, object>;
            var data = rootDict.Get<Dictionary<string, object>>("data");
            var datas = data != null ? data.Get<List<object>>("datas") : null;
            if (datas == null) return 0;
            foreach (var o in datas)
            {
                var d = o as Dictionary<string, object>;
                if (d == null) continue;
                int id = d.GetInnerInt("id", 0);
                string fp = d.GetInnerString("file_path", "");
                if (id <= 0 || string.IsNullOrEmpty(fp)) continue;
                _queue.Add(new DataItem { Id = id, FilePath = fp, ModuleId = d.GetInnerString("module_id", "") });
            }
            return _queue.Count;
        }

        // ==========================================
        // 逐条: 下载
        // ==========================================

        /// <summary>
        /// 开始下载当前下标的条目: 队列耗尽则收尾批次; 否则记录 data_id 并发起 dump 下载, 切到 Downloading
        /// </summary>
        private void BeginItemDownload()
        {
            if (_qIndex >= _queue.Count) { OnBatchDone(); return; }
            var item = _queue[_qIndex];
            _curDataId = item.Id.ToString();
            _retry = 0;
            AppendLog(string.Format("[{0}/{1}] 数据ID={2} 文件路径={3} 下载 ...", _qIndex + 1, _queue.Count, _curDataId, item.FilePath));
            _req = _client.DownloadDataDump(item.FilePath);
            _phase = Phase.Downloading;
            Repaint();
        }

        /// <summary>
        /// 等下载返回: 成功则 gzip 解码并按 "每条独立目录" 落盘为 dump json, 随后同步还原;
        /// 下载或解码/落盘失败走重试或跳过
        /// </summary>
        private void TickDownloading()
        {
            if (_req == null || !_req.Poll()) return;
            var item = _queue[_qIndex];

            if (_req.Kind == LqaResponseKind.Success)
            {
                byte[] raw = _req.Bytes;
                _req = null;
                try
                {
                    // 每条独立目录, 避免多条的 Restore.png 互相覆盖
                    string dir = Path.Combine(Application.persistentDataPath, "LQAAuto",
                                              "Job_" + Sanitize(_job.JobId), item.Id.ToString());
                    Directory.CreateDirectory(dir);
                    _curJsonPath = Path.Combine(dir, item.Id + ".json");
                    // 先解码得到干净 dump json, 落盘后再从中还原无文本背景图
                    string json = LqaDumpDecoder.Decode(raw);
                    File.WriteAllText(_curJsonPath, json, new UTF8Encoding(false));
                    // 还原 bg_data -> ScreenShot_NoText.png (供还原引擎铺底图)
                    TryRestoreBackground(dir, json);
                    AppendLog("  -> 已落盘, 还原中 ...");
                    DoRestore(item);  // 同步还原
                }
                catch (System.Exception e)
                {
                    AppendLog("  -> 下载/解码/落盘失败: " + e.Message);
                    RetryOrSkip(BeginItemDownload);
                }
            }
            else
            {
                AppendLog("  -> 下载失败: " + Describe(_req));
                _req = null;
                RetryOrSkip(BeginItemDownload);
            }
        }

        /// <summary>
        /// 同步还原当前条目 (截图 Restore.png + 导出 rect_locations.json), 然后进入提交或跳到下一条
        /// 还原异常计失败并跳过; 未产出 Restore.png (无可见文本) 或关闭自动提交时, 仅还原不提交
        /// </summary>
        /// <param name="item">当前处理的数据条目 (用于取 module_id 等)</param>
        private void DoRestore(DataItem item)
        {
            try
            {
                // 同步: 完成后目录内已有 Restore.png(+rect_locations.json)
                _engine.RestoreFromDump(_curJsonPath, _translationPath, _fontVariantTemplate);
                _totalRestored++;
            }
            catch (System.Exception e)
            {
                AppendLog("  -> 还原失败: " + e.Message);
                _totalFailed++;
                NextItem();
                return;
            }

            string png = Path.Combine(Path.GetDirectoryName(_curJsonPath), "Restore.png");
            if (!File.Exists(png))
            {
                AppendLog("  -> 还原未产出 Restore.png (可能无可见文本), 跳过提交");
                NextItem();
                return;
            }

            if (!_autoSubmit)
            {
                AppendLog("  -> 已还原 (自动提交关闭), 跳过提交");
                NextItem();
                return;
            }
            BeginItemSubmit();
        }

        // ==========================================
        // 逐条: 提交
        // ==========================================

        /// <summary>
        /// 开始提交当前条目: 读取还原目录内的 Restore.png 与 rect_locations.json,
        /// 发起 POST /api/image/entity (带 language) 并切到 Submitting; 读图失败则计失败并跳过
        /// </summary>
        private void BeginItemSubmit()
        {
            string dir = Path.GetDirectoryName(_curJsonPath);
            string png = Path.Combine(dir, "Restore.png");
            string rectPath = Path.Combine(dir, "rect_locations.json");
            byte[] bytes;
            try { bytes = File.ReadAllBytes(png); }
            catch (System.Exception e) { AppendLog("  -> 读还原图失败: " + e.Message); _totalFailed++; NextItem(); return; }

            // 文本框文件缺失时用空对象兜底, 保证提交仍带上合法的 rect_locations 字段
            bool hasRect = File.Exists(rectPath);
            string rects = hasRect ? SafeRead(rectPath) : "{}";
            _retry = 0;
            string uploadName = _job.JobId + "-" + _curDataId + "-" + _filter.Language + ".png";
            AppendLog("  -> 提交还原结果 (语言=" + _filter.Language + ", AI=" + _submit.TriggerAI + ", 文件名=" + uploadName + ") ...");
            AppendLog("     图片: " + png);
            AppendLog("     JSON: " + (hasRect ? rectPath : rectPath + " (缺失, 用空对象兜底)"));
            _req = _client.UploadImageEntity(_proj.ProjectId, _job.JobId, _curDataId, _filter.Language,
                                             rects, bytes, uploadName, _submit.TriggerAI ? "1" : "0");
            _phase = Phase.Submitting;
            Repaint();
        }

        /// <summary>
        /// 等提交返回: 成功则计数并推进到下一条; 失败走重试或跳过
        /// </summary>
        private void TickSubmitting()
        {
            if (_req == null || !_req.Poll()) return;
            if (_req.Kind == LqaResponseKind.Success)
            {
                _req = null;
                _totalSubmitted++;
                AppendLog("  -> 提交成功");
                NextItem();
            }
            else
            {
                AppendLog("  -> 提交失败: " + Describe(_req));
                _req = null;
                RetryOrSkip(BeginItemSubmit);
            }
        }

        // ==========================================
        // 条目推进 / 重试
        // ==========================================

        /// <summary>
        /// 失败后的重试/跳过决策: 未达上限则自增重试次数并重跑给定步骤; 达上限则计失败并跳到下一条
        /// </summary>
        /// <param name="retryStep">重试时要重新执行的步骤 (BeginItemDownload / BeginItemSubmit)</param>
        private void RetryOrSkip(System.Action retryStep)
        {
            if (_retry < MaxRetry - 1)
            {
                _retry++;
                AppendLog("  -> 重试 " + _retry + "/" + (MaxRetry - 1) + " ...");
                retryStep();
            }
            else
            {
                _totalFailed++;
                AppendLog("  -> 达重试上限, 跳过 data_id=" + _curDataId);
                NextItem();
            }
        }

        /// <summary>
        /// 推进到下一条: 先用当前 data_id 推进 minID 游标 (取已处理过的最大 id) 避免下轮重复领取,
        /// 再自增下标并复位重试计数, 开始下一条下载
        /// </summary>
        private void NextItem()
        {
            // 推进 minID 游标 (取已处理过的最大 id), 避免下轮监控重复领取
            if (int.TryParse(_curDataId, out int cur) && cur > _minIdCursor) _minIdCursor = cur;
            _qIndex++;
            _retry = 0;
            BeginItemDownload();
        }

        /// <summary>
        /// 当前批次全部处理完毕: 记日志并排下一轮监控
        /// </summary>
        private void OnBatchDone()
        {
            AppendLog("[批次完成] 继续监控 (最小ID 已推进到 " + _minIdCursor + ")");
            ScheduleNextMonitor();
        }

        /// <summary>
        /// 安排下一轮监控: 设定下次监控时间点并切回 Monitoring 阶段
        /// </summary>
        private void ScheduleNextMonitor()
        {
            _nextMonitorTime = EditorApplication.timeSinceStartup + _monitorInterval;
            _phase = Phase.Monitoring;
            Repaint();
        }

        // ==========================================
        // 辅助
        // ==========================================

        /// <summary>
        /// 安全读取文本文件: 任何异常都回落为空 JSON 对象 "{}", 不抛出
        /// </summary>
        /// <param name="p">文件路径</param>
        private static string SafeRead(string p) { try { return File.ReadAllText(p); } catch { return "{}"; } }

        /// <summary>
        /// 判断字符串是否非空且全部由数字字符组成 (用于校验 Language 是否为合法平台数字码)
        /// </summary>
        private static bool IsAllDigits(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            foreach (char c in s) if (c < '0' || c > '9') return false;
            return true;
        }

        /// <summary>
        /// 把字符串清洗为合法文件名片段 (非法字符替换为 '_'; 空值回退 "0"), 用于拼接落盘目录名
        /// </summary>
        private static string Sanitize(string s)
        {
            if (string.IsNullOrEmpty(s)) return "0";
            foreach (char c in Path.GetInvalidFileNameChars()) s = s.Replace(c, '_');
            return s;
        }

        /// <summary>
        /// 从 dump json 取出 bg_data(PNG 的 hex), 还原成纯背景图 ScreenShot_NoText.png
        /// 还原引擎 (RestoreEngine) 铺底图依赖此文件; 无 bg_data 或还原失败均只记日志, 不中断流水线
        /// </summary>
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

        /// <summary>
        /// 把失败请求翻译成人类可读的错误描述 (业务归类 + 可选 HTTP 码 + 底层错误信息), 用于日志
        /// </summary>
        /// <param name="req">已完成且非成功的请求句柄</param>
        private static string Describe(LqaRequest req)
        {
            var sb = new StringBuilder();
            switch (req.Kind)
            {
                case LqaResponseKind.AuthFailed:   sb.Append("鉴权未通过 (JWT无效/过期)"); break;
                case LqaResponseKind.NetworkError: sb.Append("网络不可达 (检查Host/内网)"); break;
                case LqaResponseKind.ServerError:  sb.Append("服务端错误"); break;
                default:                           sb.Append("未知"); break;
            }
            if (req.Code > 0) sb.Append(" [HTTP ").Append(req.Code).Append("]");
            if (!string.IsNullOrEmpty(req.Error)) sb.Append(" ").Append(req.Error);
            return sb.ToString();
        }

        /// <summary>
        /// 追加一行日志到缓冲并触发界面重绘 (让日志区实时刷新)
        /// </summary>
        /// <param name="line">要追加的日志行</param>
        private void AppendLog(string line) { _log.AppendLine(line); Repaint(); }
    }
}