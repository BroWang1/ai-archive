// ==========================================
// 文件: LQARestore\Platform\Editor\Windows\LqaSubmitRestoreWindow.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// 提交还原结果到平台 (EditorWindow)
    /// 职责: 把 "手动还原(跳过背景)" 产出的还原图连同文本框上传到平台, 关联到对应的平台 data_id
    /// 一个 "可提交项" = 一个还原目录, 需含三样 (还原流程与拉取落盘约定产生):
    ///   - {data_id}.json: dump(拉取时以 data_id 命名落盘), 文件名即平台 data_id;
    ///   - Restore.png: 还原结果图(RestoreEngine 截图输出到 dump 同目录);
    ///   - rect_locations.json: 文本框(RestoreEngine 还原时导出, 平台 rect_locations 格式)
    /// 上传: POST /api/image/entity (multipart, 见 LqaApiClient.UploadImageEntity), ai_sign=0 只存图与框、不触发 AI
    ///   project_id 取自 Project Config; job_id 取自 Job Config; language 在本窗口填 (平台内部语言码, 数字)
    /// 编辑器内用 EditorApplication.update 逐帧轮询请求句柄, 不用协程
    /// </summary>
    public class LqaSubmitRestoreWindow : EditorWindow
    {
        /// <summary>
        /// 菜单入口: Tools/LQA/平台/单步/提交还原结果...
        /// 打开 (或聚焦已存在的) 窗口, 锁定固定大小且在主编辑器窗口内居中, 打开即刷新一次配置快照
        /// </summary>
        [MenuItem("Tools/LQA/平台/单步/提交还原结果...", false, 322)]
        public static void Open()
        {
            // 普通 (非 utility) 窗口: utility 置顶会挡住 OpenFolderPanel
            var win = GetWindow<LqaSubmitRestoreWindow>(false, "LQA 提交还原结果", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 700);
            win.Refresh();
            win.Show();
        }

        /// <summary>
        /// 平台连接配置快照 (Host / 鉴权令牌等, Refresh 时从 LqaPlatformConfig 载入)
        /// </summary>
        private LqaPlatformConfig _conn;

        /// <summary>
        /// 项目配置快照 (提供 project_id, Refresh 时从 LqaProjectConfig 载入)
        /// </summary>
        private LqaProjectConfig _proj;

        /// <summary>
        /// 任务配置快照 (提供 job_id, Refresh 时从 LqaJobConfig 载入)
        /// </summary>
        private LqaJobConfig _job;

        /// <summary>
        /// 提交配置快照 (提供 ai_sign 开关, Refresh 时从 LqaSubmitConfig 载入)
        /// </summary>
        private LqaSubmitConfig _submit;

        /// <summary>
        /// 平台内部语言码 (数字字符串), 只读: 取自筛选变量(Filter Config)选好的语言, 本窗口不编辑
        /// </summary>
        private string _language = "";

        /// <summary>
        /// 待提交的还原目录列表 (每个目录为一个可提交项)
        /// </summary>
        private readonly List<string> _dirs = new List<string>();

        /// <summary>
        /// 是否正在提交中 (提交期间禁用编辑类按钮, 避免中途改动列表)
        /// </summary>
        private bool _running;

        /// <summary>
        /// 当前处理到的目录下标 (_index) 与当前目录已重试次数 (_retry)
        /// </summary>
        private int _index, _retry;

        /// <summary>
        /// 单个目录的最大尝试次数 (含首次, 即最多重试 MaxRetry-1 次)
        /// </summary>
        private const int MaxRetry = 3;

        /// <summary>
        /// 平台客户端 (StartSubmit 时按当前连接配置构造)
        /// </summary>
        private LqaApiClient _client;

        /// <summary>
        /// 当前在途的上传请求句柄 (Tick 中每帧轮询直至完成)
        /// </summary>
        private LqaRequest _req;

        /// <summary>
        /// 累计成功 (_okCount) 与失败 (_failCount) 的目录数
        /// </summary>
        private int _okCount, _failCount;

        /// <summary>
        /// 目录列表滚动位置 (_scrollDirs) 与日志区滚动位置 (_scrollLog)
        /// </summary>
        private Vector2 _scrollDirs, _scrollLog;

        /// <summary>
        /// 运行日志缓冲 (AppendLog 追加, OnGUI 只读展示)
        /// </summary>
        private readonly StringBuilder _log = new StringBuilder();

        /// <summary>
        /// 待处理的文件夹选择类型: 无 / 选单个还原目录 / 选父目录扫子目录
        /// </summary>
        private enum PendingPick { None, Single, Parent }

        /// <summary>
        /// 已排队但尚未执行的文件夹选择类型 (延迟到 GUI 帧外才真正弹窗)
        /// </summary>
        private PendingPick _pendingPick = PendingPick.None;

        /// <summary>
        /// 是否已向 delayCall 注册过一次待执行的选择 (防止重复注册)
        /// </summary>
        private bool _pickScheduled;

        /// <summary>
        /// 窗口重新获得焦点时: 非提交中则刷新配置快照, 同步其它配置窗口的改动
        /// </summary>
        private void OnFocus() { if (!_running) Refresh(); }

        /// <summary>
        /// 窗口禁用/关闭时清理: 反注册延迟选择与逐帧轮询, 并中止在途请求, 防止回调打到已销毁窗口
        /// </summary>
        private void OnDisable()
        {
            if (_pickScheduled) { EditorApplication.delayCall -= DoPendingPick; _pickScheduled = false; }
            EditorApplication.update -= Tick;
            if (_req != null) { _req.Abort(); _req = null; }
        }

        /// <summary>
        /// 从各配置载入最新快照 (连接/项目/任务), 语言只读复用筛选变量里选好的数字码
        /// </summary>
        private void Refresh()
        {
            _conn = LqaPlatformConfig.Load();
            _proj = LqaProjectConfig.Load();
            _job = LqaJobConfig.Load();
            _submit = LqaSubmitConfig.Load();
            // 语言只读复用筛选变量 (Filter Config) 里选好的数字码, 本窗口不再输入语言
            _language = LqaFilterConfig.Load().Language;
        }

        /// <summary>
        /// 一个还原目录是否可提交: 含 Restore.png + rect_locations.json + 至少一个 {digits}.json
        /// </summary>
        private static bool IsRestoreDir(string dir)
        {
            if (string.IsNullOrEmpty(dir) || !Directory.Exists(dir)) return false;
            if (!File.Exists(Path.Combine(dir, "Restore.png"))) return false;
            return !string.IsNullOrEmpty(FindDataIdJson(dir));
        }

        /// <summary>
        /// 在目录里找 "文件名是纯数字的 json" (即拉取落盘的 {data_id}.json), 返回其 data_id; 找不到返回 ""
        /// </summary>
        private static string FindDataIdJson(string dir)
        {
            foreach (var p in Directory.GetFiles(dir, "*.json"))
            {
                string name = Path.GetFileNameWithoutExtension(p);
                if (IsAllDigits(name)) return name;
            }
            return "";
        }

        /// <summary>
        /// 判断字符串是否为非空且全部由数字字符 (0-9) 组成
        /// </summary>
        private static bool IsAllDigits(string s)
        {
            if (string.IsNullOrEmpty(s)) return false;
            foreach (char c in s) if (c < '0' || c > '9') return false;
            return true;
        }

        /// <summary>
        /// 绘制面板: 顶部只读配置上下文 + 待提交目录列表(增删) + 开始/取消按钮 + 状态与日志
        /// </summary>
        private void OnGUI()
        {
            // 见上一窗口经验: MouseDown 时清键盘焦点, 避免 SelectableLabel 抢焦点吃掉按钮首次点击
            if (Event.current != null && Event.current.type == EventType.MouseDown)
                GUIUtility.keyboardControl = 0;

            EditorGUILayout.LabelField("提交还原结果到平台", EditorStyles.boldLabel);

            // 固定高度画 HelpBox, 避免自动高度在两趟布局不一致导致下方按钮点击热区错位
            Rect helpRect = EditorGUILayout.GetControlRect(false, 58f);
            EditorGUI.HelpBox(helpRect,
                "把手动还原产出的 Restore.png + rect_locations.json 提交到平台 (POST /api/image/entity, AI标记 由 \"提交配置\" 决定)\n" +
                "目录需含: {数据ID}.json + Restore.png + rect_locations.json, 项目ID/任务ID 取自 项目配置/任务配置",
                MessageType.Info);

            EditorGUILayout.Space(2);
            DrawReadonly("平台 Host (仅查看)", string.IsNullOrEmpty(_conn.Host) ? "(未配置)" : _conn.Host);
            DrawReadonly("项目 ID (仅查看)", _proj.ProjectId);
            DrawReadonly("任务 ID (仅查看)", _job.JobId);

            // 语言只读: 取自 "筛选变量" 窗口选好的数字码, 本窗口不输入 (改语言请去 Filter Config 拉取选择)
            DrawReadonly("语言码 (仅查看)", string.IsNullOrEmpty(_language)
                ? "(未设置, 请去 筛选配置 拉取并选择语言)" : _language);

            EditorGUILayout.Space(6);

            EditorGUILayout.LabelField("待提交目录 (" + _dirs.Count + ")", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(_running))
            {
                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button("添加目录...")) SchedulePick(PendingPick.Single);
                if (GUILayout.Button("添加父目录(扫子目录)...")) SchedulePick(PendingPick.Parent);
                if (GUILayout.Button("清空", GUILayout.Width(60))) _dirs.Clear();
                EditorGUILayout.EndHorizontal();
            }

            _scrollDirs = EditorGUILayout.BeginScrollView(_scrollDirs, GUILayout.Height(120));
            int removeAt = -1;
            for (int i = 0; i < _dirs.Count; i++)
            {
                EditorGUILayout.BeginHorizontal();
                bool ok = IsRestoreDir(_dirs[i]);
                // 不可提交的目录前打 ⚠ 标记, 提示缺文件
                EditorGUILayout.LabelField(ok ? "" : "⚠", GUILayout.Width(16));
                EditorGUILayout.SelectableLabel(_dirs[i],
                    EditorStyles.textField, GUILayout.Height(EditorGUIUtility.singleLineHeight));
                using (new EditorGUI.DisabledScope(_running))
                {
                    if (GUILayout.Button("移除", GUILayout.Width(50))) removeAt = i;
                }
                EditorGUILayout.EndHorizontal();
            }
            EditorGUILayout.EndScrollView();
            // 遍历中不改集合, 循环结束后再删, 避免枚举/布局错位
            if (removeAt >= 0) _dirs.RemoveAt(removeAt);

            EditorGUILayout.Space(6);

            using (new EditorGUI.DisabledScope(_running || _dirs.Count == 0))
            {
                if (GUILayout.Button("开始提交", GUILayout.Height(28))) StartSubmit();
            }
            if (_running && GUILayout.Button("取消", GUILayout.Height(22))) Cancel("已取消");

            string status = _running
                ? string.Format("提交中 {0}/{1} (成功 {2}, 失败 {3})", _index + 1, _dirs.Count, _okCount, _failCount)
                : (_okCount + _failCount > 0
                    ? string.Format("完成: 成功 {0}, 失败 {1}", _okCount, _failCount) : "就绪");
            EditorGUILayout.LabelField("状态", status);

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
        /// 画一行只读的 "标签 + 可选中复制文本" (值为空时显示空串)
        /// </summary>
        /// <param name="label">左侧字段名</param>
        /// <param name="value">右侧只读展示的值</param>
        private void DrawReadonly(string label, string value)
        {
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PrefixLabel(label);
            EditorGUILayout.SelectableLabel(value ?? "", EditorStyles.textField,
                GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();
        }

        // ==========================================
        // 添加目录 (延迟到 GUI 帧外弹选择框)
        // ==========================================

        /// <summary>
        /// 排队一次文件夹选择: 记录选择类型并注册到 delayCall, 待离开 OnGUI 事件流程后再弹窗
        /// (在 OnGUI 里同步弹 OpenFolderPanel 会打断布局, 故延迟到帧外)
        /// </summary>
        /// <param name="which">本次选择类型 (单个目录 / 父目录扫子目录)</param>
        private void SchedulePick(PendingPick which)
        {
            _pendingPick = which;
            if (_pickScheduled) return;
            _pickScheduled = true;
            EditorApplication.delayCall += DoPendingPick;
        }

        /// <summary>
        /// delayCall 回调: 反注册自身并取出排队的选择类型, 真正执行目录添加
        /// </summary>
        private void DoPendingPick()
        {
            EditorApplication.delayCall -= DoPendingPick;
            _pickScheduled = false;
            var which = _pendingPick;
            _pendingPick = PendingPick.None;
            if (which == PendingPick.None) return;
            AddDir(which == PendingPick.Parent);
        }

        /// <summary>
        /// 弹文件夹选择框并把结果加入待提交列表:
        ///   asParent=true 时把所选目录及其可提交子目录逐个加入; 否则只加所选的单个目录 (不可提交则记日志提示)
        /// </summary>
        /// <param name="asParent">true=按父目录扫描其下的还原子目录; false=添加单个还原目录</param>
        private void AddDir(bool asParent)
        {
            string picked = EditorUtility.OpenFolderPanel(
                asParent ? "选择父目录 (扫描其下的还原子目录)" : "选择一个还原目录", "", "");
            if (string.IsNullOrEmpty(picked)) return;

            if (asParent)
            {
                int added = 0;
                foreach (var sub in Directory.GetDirectories(picked))
                    if (IsRestoreDir(sub) && !_dirs.Contains(sub)) { _dirs.Add(sub); added++; }
                // 父目录自身也可能就是一个还原目录, 一并纳入
                if (IsRestoreDir(picked) && !_dirs.Contains(picked)) { _dirs.Add(picked); added++; }
                AppendLog("扫描到 " + added + " 个可提交还原目录");
            }
            else
            {
                if (_dirs.Contains(picked)) return;
                _dirs.Add(picked);
                if (!IsRestoreDir(picked))
                    AppendLog("⚠ 该目录缺少 Restore.png 或 {数据ID}.json, 提交时会被跳过: " + picked);
            }
            Repaint();
        }

        // ==========================================
        // 提交流程
        // ==========================================

        /// <summary>
        /// 开始提交: 先刷新并校验前置配置 (Host/JobId/ProjectId/Language), 全部就绪后
        /// 重置计数与日志, 构造客户端, 注册逐帧轮询 Tick, 并从第一个目录开始处理
        /// </summary>
        private void StartSubmit()
        {
            Refresh();
            if (string.IsNullOrEmpty(_conn.Host)) { Fatal("平台 Host 未配置, 去 平台连接配置 设置"); return; }
            if (_job.IsIdle) { Fatal("任务ID 未配置或为 0, 去 任务配置 设置"); return; }
            if (string.IsNullOrEmpty(_proj.ProjectId) || _proj.ProjectId == "0") { Fatal("项目ID 未配置, 去 项目配置 设置"); return; }
            if (!IsAllDigits(_language)) { Fatal("语言 未设置或非数字码; 请去 筛选配置 拉取并选择语言"); return; }

            _client = new LqaApiClient(_conn);
            _running = true;
            _index = 0; _retry = 0; _okCount = 0; _failCount = 0;
            _log.Length = 0;
            AppendLog("开始提交, 共 " + _dirs.Count + " 个目录");

            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            BeginDir();
        }

        /// <summary>
        /// 开始处理当前下标的目录: 全部处理完则收尾;
        /// 目录不可提交 (缺文件) 则计失败并跳到下一个; 否则发起本目录的上传
        /// </summary>
        private void BeginDir()
        {
            if (_index >= _dirs.Count) { Finish(); return; }
            string dir = _dirs[_index];
            _retry = 0;

            AppendLog(string.Format("[{0}/{1}] {2}", _index + 1, _dirs.Count, dir));

            if (!IsRestoreDir(dir))
            {
                _failCount++;
                AppendLog("  -> 跳过: 缺 Restore.png 或 {数据ID}.json");
                NextDir();
                return;
            }
            SendCurrent();
        }

        /// <summary>
        /// 发起当前目录的上传请求: 读 data_id / Restore.png / rect_locations.json
        /// (读图失败则计失败并跳下一个; 无 rect 文件则用空框 "{}" 兜底), 调 UploadImageEntity 得到在途句柄 _req
        /// </summary>
        private void SendCurrent()
        {
            string dir = _dirs[_index];
            string dataId = FindDataIdJson(dir);
            string pngPath = Path.Combine(dir, "Restore.png");
            string rectPath = Path.Combine(dir, "rect_locations.json");

            byte[] png;
            try { png = File.ReadAllBytes(pngPath); }
            catch (System.Exception e) { _failCount++; AppendLog("  -> 读图失败: " + e.Message); NextDir(); return; }

            string rects = "{}";
            if (File.Exists(rectPath))
            {
                try { rects = File.ReadAllText(rectPath); }
                catch (System.Exception e) { AppendLog("  -> 读 rect_locations 失败 (用空框): " + e.Message); }
            }
            else AppendLog("  -> 无 rect_locations.json, 用空框提交");

            string uploadName = _job.JobId + "-" + dataId + "-" + _language + ".png";
            AppendLog("  提交还原结果 (数据ID=" + dataId + ", 语言=" + _language + ", AI=" + _submit.TriggerAI + ", 文件名=" + uploadName + ") ...");
            _req = _client.UploadImageEntity(_proj.ProjectId, _job.JobId, dataId, _language, rects, png, uploadName, _submit.TriggerAI ? "1" : "0");
            Repaint();
        }

        /// <summary>
        /// 逐帧轮询 (挂在 EditorApplication.update): 请求完成后按结果分流——
        /// 成功则计数并进下一目录; 失败则在未达重试上限时重发, 否则计失败并进下一目录
        /// </summary>
        private void Tick()
        {
            if (!_running || _req == null || !_req.Poll()) return;

            if (_req.Kind == LqaResponseKind.Success)
            {
                _req = null;
                _okCount++;
                AppendLog("  -> 提交成功");
                NextDir();
            }
            else
            {
                string detail = Describe(_req);
                _req = null;
                AppendLog("  -> 提交失败: " + detail);
                if (_retry < MaxRetry - 1)
                {
                    _retry++;
                    AppendLog("  -> 重试 " + _retry + "/" + (MaxRetry - 1) + " ...");
                    SendCurrent();
                }
                else
                {
                    _failCount++;
                    AppendLog("  -> 达重试上限, 该目录失败");
                    NextDir();
                }
            }
        }

        /// <summary>
        /// 前进到下一个目录并开始处理
        /// </summary>
        private void NextDir() { _index++; BeginDir(); }

        /// <summary>
        /// 全部目录处理完毕的收尾: 反注册轮询, 置为非运行态, 记录汇总结果
        /// </summary>
        private void Finish()
        {
            EditorApplication.update -= Tick;
            _running = false;
            AppendLog(string.Format("== 完成: 成功 {0}, 失败 {1} ==", _okCount, _failCount));
            Repaint();
        }

        /// <summary>
        /// 中途取消: 反注册轮询, 中止在途请求, 置为非运行态并记录原因
        /// </summary>
        /// <param name="reason">取消原因 (写入日志)</param>
        private void Cancel(string reason)
        {
            EditorApplication.update -= Tick;
            if (_req != null) { _req.Abort(); _req = null; }
            _running = false;
            AppendLog("== " + reason + " ==");
            Repaint();
        }

        /// <summary>
        /// 记录一条致命前置错误到日志 (前置校验不通过时用, 不启动流程)
        /// </summary>
        /// <param name="msg">错误说明</param>
        private void Fatal(string msg) { AppendLog("[错误] " + msg); Repaint(); }

        /// <summary>
        /// 把失败请求归类翻译成可读文案 (业务归类 + 可选 HTTP 码 + Error + 截断后的响应体)
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
            // 响应体可能很长, 只取前 160 字符入日志, 避免刷屏
            if (!string.IsNullOrEmpty(req.Text)) sb.Append(" ").Append(req.Text.Length > 160 ? req.Text.Substring(0, 160) : req.Text);
            return sb.ToString();
        }

        /// <summary>
        /// 追加一行日志并请求重绘 (使日志区实时刷新)
        /// </summary>
        /// <param name="line">日志行文本</param>
        private void AppendLog(string line) { _log.AppendLine(line); Repaint(); }
    }
}