// ==========================================
// 文件: LQARestore\Platform\Editor\Windows\LqaUploadDataWindow.cs
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
    /// 上传单条或多条数据到平台 (EditorWindow)
    /// 职责: 把一个或多个 LQATool 采集产物目录 (含 ui_data_text.json + ScreenShot_*.png) 上传到平台
    /// 每个目录走三步链路 (对齐平台上传协议, 顺序不能乱):
    ///   1. POST /api/data/entity 用补全后的 data json 建 data, 拿平台 data_id;
    ///   2. POST /api/upload_file 上传截图, 拿 file_path;
    ///   3. PATCH /api/data/entity 回填 shot_img_path + module_id + resource_version
    /// 数据整理 (字段补全/截图定位) 在 LqaUploadPayload; HTTP 三步在 LqaApiClient(UploadDataJson/UploadFile/UpdateDataImage)
    /// project_id 取自 LqaProjectConfig, job_id 取自 LqaJobConfig, module_id/resource_version 取自 LqaProjectConfig
    /// 编辑器内无 MonoBehaviour 主循环, 故用 EditorApplication.update 逐帧轮询请求句柄, 不用协程
    /// </summary>
    public class LqaUploadDataWindow : EditorWindow
    {
        /// <summary>
        /// 菜单入口: 打开(或聚焦)上传采集数据窗口, 并刷新配置快照
        /// </summary>
        [MenuItem("Tools/LQA/平台/单步/上传采集数据...", false, 321)]
        public static void Open()
        {
            // 用普通 (可停靠) 窗口而非 utility 窗口: utility 窗口 always-on-top, 会挡住/抢焦点
            // 导致 EditorUtility.OpenFolderPanel 弹出的系统文件夹对话框无法正常显示 (表现为 "点了没反应")
            var win = GetWindow<LqaUploadDataWindow>(false, "LQA 上传采集数据", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 700);
            win.Refresh();
            win.Show();
        }

        // ==========================================
        // 配置快照 (打开/聚焦时从各 Config 读一次, 上传全程用此快照)
        // ==========================================

        /// <summary>
        /// 平台连接配置 (Host / 鉴权令牌), 用于构造 LqaApiClient
        /// </summary>
        private LqaPlatformConfig _conn;

        /// <summary>
        /// 项目配置, 提供 project_id
        /// </summary>
        private LqaProjectConfig _proj;

        /// <summary>
        /// 任务配置, 提供 job_id
        /// </summary>
        private LqaJobConfig _job;

        /// <summary>
        /// 上传配置, 提供回填用的 module_id / resource_version
        /// </summary>
        private LqaUploadConfig _upload;

        /// <summary>
        /// 待上传目录列表 (每项为一个 LQATool 采集产物目录的绝对路径)
        /// </summary>
        private readonly List<string> _dirs = new List<string>();

        // ==========================================
        // 运行时状态
        // 每个目录内部三步: BuildPayload -> PostData -> UploadImg -> PatchData
        // ==========================================

        /// <summary>
        /// 单个目录内部的上传阶段 (与三步链路一一对应, None 表示当前无进行中的目录)
        /// </summary>
        private enum Step { None, PostData, UploadImg, PatchData }

        /// <summary>
        /// 是否正在上传中 (为 true 时禁用编辑操作, 并驱动 Tick 轮询)
        /// </summary>
        private bool _running;

        /// <summary>
        /// 当前正在处理的目录下标 (指向 _dirs)
        /// </summary>
        private int _index;

        /// <summary>
        /// 当前步骤已重试次数 (每进入新步骤清零)
        /// </summary>
        private int _retry;

        /// <summary>
        /// 单个步骤的最大尝试次数 (含首次), 超过则该目录判失败
        /// </summary>
        private const int MaxRetry = 3;

        /// <summary>
        /// 当前目录所处的上传阶段
        /// </summary>
        private Step _step = Step.None;

        /// <summary>
        /// 平台客户端 (StartUpload 时用配置快照构造)
        /// </summary>
        private LqaApiClient _client;

        /// <summary>
        /// 当前进行中的请求句柄 (每帧 Poll, 完成后按 _step 分派处理)
        /// </summary>
        private LqaRequest _req;

        /// <summary>
        /// 当前目录整理出的上传素材 (data json + 截图路径)
        /// </summary>
        private LqaUploadPayload.Payload _payload;

        /// <summary>
        /// 当前目录第1步 (建 data) 拿到的 data_id, 供第 3 步回填
        /// </summary>
        private string _curDataId;

        /// <summary>
        /// 当前目录第 2 步 (传截图) 拿到的 file_path, 供第 3 步回填
        /// </summary>
        private string _curFilePath;

        /// <summary>
        /// 成功计数 (含 "仅建 data 成功" 的部分成功)
        /// </summary>
        private int _okCount;

        /// <summary>
        /// 失败计数 (整理失败/达重试上限/非采集目录被跳过)
        /// </summary>
        private int _failCount;

        /// <summary>
        /// 目录列表滚动位置
        /// </summary>
        private Vector2 _scrollDirs;

        /// <summary>
        /// 日志区滚动位置
        /// </summary>
        private Vector2 _scrollLog;

        /// <summary>
        /// 累积日志文本 (逐行 AppendLine)
        /// </summary>
        private readonly StringBuilder _log = new StringBuilder();

        /// <summary>
        /// 文件夹选择的 "待办" 意图: 单目录还是父目录 (扫子目录)
        /// </summary>
        private enum PendingPick { None, Single, Parent }

        /// <summary>
        /// 按钮点击时只记录意图, 待本帧 GUI 画完后 (delayCall) 再真正弹对话框
        /// 直接在 OnGUI 按钮回调里同步调 OpenFolderPanel 会打断 IMGUI 事件循环, 导致"偶尔弹不出来"
        /// </summary>
        private PendingPick _pendingPick = PendingPick.None;

        /// <summary>
        /// 是否已挂上延迟回调, 防止重复 delayCall
        /// </summary>
        private bool _pickScheduled;

        /// <summary>
        /// 窗口重新获得焦点时刷新配置快照 (上传进行中不刷, 避免中途换配置)
        /// </summary>
        private void OnFocus() { if (!_running) Refresh(); }

        /// <summary>
        /// 窗口关闭/禁用时的清理
        /// </summary>
        private void OnDisable()
        {
            // 窗口关闭时摘除可能仍挂着的延迟回调, 避免窗口销毁后仍被触发
            if (_pickScheduled)
            {
                EditorApplication.delayCall -= DoPendingPick;
                _pickScheduled = false;
            }
        }

        /// <summary>
        /// 重新从磁盘加载四份配置, 刷新界面用的只读快照
        /// </summary>
        private void Refresh()
        {
            _conn = LqaPlatformConfig.Load();
            _proj = LqaProjectConfig.Load();
            _job = LqaJobConfig.Load();
            _upload = LqaUploadConfig.Load();
        }

        /// <summary>
        /// 绘制窗口: 配置摘要 + 目录列表 + 操作区 + 状态 + 日志 (IMGUI)
        /// </summary>
        private void OnGUI()
        {
            // 修复 "按钮偶尔点了没反应": 界面上有多个可获得焦点的 SelectableLabel (摘要/目录/日志, 为了可复制)
            // 当键盘焦点正停在某个 SelectableLabel 上时, 对按钮的第一次 MouseDown 会先被用于 "移走该焦点",
            // 这一次点击即被消耗掉、按钮不触发 (焦点在哪个控件是随机的, 故表现为偶发)
            // 解决: 在事件到达任何控件之前, 于 MouseDown 时先清掉键盘焦点, 使点击能正常命中按钮
            if (Event.current != null && Event.current.type == EventType.MouseDown)
            {
                GUIUtility.keyboardControl = 0;
            }

            EditorGUILayout.LabelField("上传采集数据到平台", EditorStyles.boldLabel);
            // 用 "固定高度" 方式画 HelpBox: EditorGUILayout.HelpBox 的自动高度在 Layout 趟与 Repaint 趟
            // 可能算出不同行数 (含图标+多行中文、窗口宽度临界时尤甚), 两趟高度不一致会把其下方所有控件的
            // 点击热区整体推移 (表现为 "按钮的点击区跑到按钮下方"), 固定高度可彻底消除该偏移
            Rect helpRect = EditorGUILayout.GetControlRect(false, 56f);
            EditorGUI.HelpBox(helpRect,
                "把一个或多个 LQATool 采集产物目录 (含 ui_data_text.json + ScreenShot_*.png) 上传到平台\n" +
                "上传三步: 建 data -> 传截图 -> 回填, 项目ID/任务ID/ 上传字段分别取自 项目配置/任务配置/上传配置",
                MessageType.Info);

            // 配置摘要 (只读, 供核对上传去向)
            EditorGUILayout.Space(2);
            DrawReadonly("平台 Host (仅查看)", string.IsNullOrEmpty(_conn.Host) ? "(未配置)" : _conn.Host);
            DrawReadonly("项目 ID (仅查看)", _proj.ProjectId);
            DrawReadonly("任务 ID (仅查看)", _job.JobId);
            DrawReadonly("模块ID / 版本 (仅查看)",
                (string.IsNullOrEmpty(_upload.ModuleId) ? "(空)" : _upload.ModuleId) + " / " +
                (string.IsNullOrEmpty(_upload.ResourceVersion) ? "(空)" : _upload.ResourceVersion));

            EditorGUILayout.Space(6);

            // 待上传目录列表 (含添加/清空按钮, 上传中禁用编辑)
            EditorGUILayout.LabelField("待上传目录 (" + _dirs.Count + ")", EditorStyles.boldLabel);
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
                // 非有效采集目录 (缺 ui_data_text.json) 前面标 ⚠ 提示, 上传时会被跳过
                bool ok = LqaUploadPayload.IsDumpDir(_dirs[i]);
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
            // 遍历中不能改集合, 记下待移除下标, 循环结束后再删
            if (removeAt >= 0) _dirs.RemoveAt(removeAt);

            EditorGUILayout.Space(6);

            // 操作区: 开始上传 / (上传中) 取消
            using (new EditorGUI.DisabledScope(_running || _dirs.Count == 0))
            {
                if (GUILayout.Button("开始上传", GUILayout.Height(28))) StartUpload();
            }
            if (_running && GUILayout.Button("取消", GUILayout.Height(22))) CancelUpload("已取消");

            // 状态行: 运行中显示进度, 结束后显示汇总, 否则 "就绪"
            string status = _running
                ? string.Format("上传中 {0}/{1} [{2}] (成功 {3}, 失败 {4})",
                    _index + 1, _dirs.Count, _step, _okCount, _failCount)
                : (_okCount + _failCount > 0
                    ? string.Format("完成: 成功 {0}, 失败 {1}", _okCount, _failCount)
                    : "就绪");
            EditorGUILayout.LabelField("状态", status);

            // 日志区 (可复制的 SelectableLabel)
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
        /// 画一行 "标签 + 只读可复制值" (用 SelectableLabel 呈现, 方便复制核对)
        /// </summary>
        /// <param name="label">左侧标签文本</param>
        /// <param name="value">右侧只读值 (null 视为空串)</param>
        private void DrawReadonly(string label, string value)
        {
            EditorGUILayout.BeginHorizontal();
            float savedLabelWidth = EditorGUIUtility.labelWidth;
            EditorGUIUtility.labelWidth = 180f;  // 容纳 "Module Id / Version (仅查看)" 这类较长标签
            EditorGUILayout.PrefixLabel(label);
            EditorGUIUtility.labelWidth = savedLabelWidth;  // 立即还原, 不影响其它区域
            EditorGUILayout.SelectableLabel(value ?? "", EditorStyles.textField,
                GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();
        }

        // ==========================================
        // 添加目录
        // ==========================================

        /// <summary>
        /// 记录 "要弹文件夹选择框" 的意图, 并调度到本帧 GUI 处理完之后执行 (EditorApplication.delayCall)
        /// 关键: 不能在 OnGUI 的按钮回调里同步调 OpenFolderPanel —— 那会在 IMGUI 事件处理中途
        /// 弹出模态系统对话框, 打断事件循环, 造成 "偶尔能弹、偶尔弹不出" 的时序问题
        /// </summary>
        /// <param name="which">本次要弹的选择类型 (单目录 / 父目录)</param>
        private void SchedulePick(PendingPick which)
        {
            _pendingPick = which;
            if (_pickScheduled) return;  // 已调度则不重复
            _pickScheduled = true;
            EditorApplication.delayCall += DoPendingPick;
        }

        /// <summary>
        /// 在 GUI 帧外真正弹出文件夹选择框 (由 delayCall 触发)
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
        /// 弹文件夹选择框并把结果加入待上传列表 (去重)
        /// </summary>
        /// <param name="asParent">
        /// true: 选父目录并扫描其下的采集子目录(父目录本身若也是采集目录一并加入);
        /// false: 直接把所选目录当作单个采集目录加入(非采集目录也加, 仅提示上传时会跳过)
        /// </param>
        private void AddDir(bool asParent)
        {
            string picked = EditorUtility.OpenFolderPanel(
                asParent ? "选择父目录 (将扫描其下的采集子目录)" : "选择一个采集产物目录", "", "");
            if (string.IsNullOrEmpty(picked)) return;

            if (asParent)
            {
                int added = 0;
                foreach (var sub in Directory.GetDirectories(picked))
                {
                    if (LqaUploadPayload.IsDumpDir(sub) && !_dirs.Contains(sub)) { _dirs.Add(sub); added++; }
                }
                // 父目录本身也可能就是一个采集目录
                if (LqaUploadPayload.IsDumpDir(picked) && !_dirs.Contains(picked)) { _dirs.Add(picked); added++; }
                AppendLog("从父目录扫描到 " + added + " 个采集子目录。");
            }
            else
            {
                if (_dirs.Contains(picked)) return;
                _dirs.Add(picked);
                if (!LqaUploadPayload.IsDumpDir(picked))
                    AppendLog("⚠ 该目录缺少 ui_data_text.json, 上传时会被跳过: " + picked);
            }
            Repaint();
        }

        // ==========================================
        // 上传流程
        // ==========================================

        /// <summary>
        /// 开始上传: 校验配置 -> 构造客户端 -> 重置计数 -> 挂 Tick 轮询 -> 处理第一个目录
        /// 任一必需配置缺失时直接终止 (Fatal 记日志, 不进入运行态)
        /// </summary>
        private void StartUpload()
        {
            Refresh();
            if (string.IsNullOrEmpty(_conn.Host)) { Fatal("平台 Host 未配置, 去 Tools/LQA/平台/配置/平台连接 设置"); return; }
            if (_job.IsIdle) { Fatal("任务ID 未配置或为 0, 去 Tools/LQA/平台/配置/任务配置 设置"); return; }
            if (string.IsNullOrEmpty(_proj.ProjectId) || _proj.ProjectId == "0") { Fatal("项目ID 未配置, 去 Tools/LQA/平台/配置/项目配置 设置"); return; }

            _client = new LqaApiClient(_conn);
            _running = true;
            _index = 0; _retry = 0; _okCount = 0; _failCount = 0;
            _log.Length = 0;
            AppendLog("开始上传, 共 " + _dirs.Count + " 个目录");

            // 先摘再挂, 防止重复订阅导致 Tick 一帧被调多次
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
            BeginDir();
        }

        /// <summary>
        /// 开始处理当前目录: 整理素材 -> 发起第1步 (整理失败/非采集目录则计失败并跳下一个)
        /// </summary>
        private void BeginDir()
        {
            if (_index >= _dirs.Count) { Finish(); return; }

            string dir = _dirs[_index];
            _retry = 0;
            _curDataId = null; _curFilePath = null; _payload = null;

            AppendLog(string.Format("[{0}/{1}] {2}", _index + 1, _dirs.Count, dir));

            if (!LqaUploadPayload.IsDumpDir(dir))
            {
                _failCount++;
                AppendLog("  -> 跳过: 不是有效采集目录 (缺 ui_data_text.json)");
                NextDir();
                return;
            }

            try { _payload = LqaUploadPayload.Build(dir); }
            catch (System.Exception e)
            {
                _failCount++;
                AppendLog("  -> 整理失败: " + e.Message);
                NextDir();
                return;
            }

            BeginPostData();
        }

        /// <summary>
        /// 第1步: 建数据 (POST /api/data/entity), 成功后取 data_id 进第 2 步
        /// </summary>
        private void BeginPostData()
        {
            _step = Step.PostData;
            AppendLog("  1) 建数据 (POST /api/data/entity) ...");
            _req = _client.UploadDataJson(_proj.ProjectId, _job.JobId, _payload.DataJson);
            Repaint();
        }

        /// <summary>
        /// 第2步: 传截图 (POST /api/upload_file); 目录无截图时视为部分成功并跳过后两步
        /// </summary>
        private void BeginUploadImg()
        {
            if (string.IsNullOrEmpty(_payload.ShotImagePath) || !File.Exists(_payload.ShotImagePath))
            {
                // 无截图: 建数据 已成功, 视为部分成功, 跳过后两步
                _okCount++;
                AppendLog("  -> 无截图文件, 仅建数据成功 (data_id=" + _curDataId + "), 跳过传图/回填");
                NextDir();
                return;
            }
            _step = Step.UploadImg;
            _retry = 0;
            byte[] bytes = File.ReadAllBytes(_payload.ShotImagePath);
            string fileName = Path.GetFileName(_payload.ShotImagePath);
            AppendLog("  2) 传截图 " + fileName + " (POST /api/upload_file) ...");
            _req = _client.UploadFile(bytes, fileName);
            Repaint();
        }

        /// <summary>
        /// 第3步: 回填截图路径与 module_id/resource_version (PATCH /api/data/entity)
        /// </summary>
        private void BeginPatchData()
        {
            _step = Step.PatchData;
            _retry = 0;
            AppendLog("  3) 回填截图路径 (PATCH /api/data/entity) ...");
            _req = _client.UpdateDataImage(_curDataId, _curFilePath, _upload.ModuleId, _upload.ResourceVersion);
            Repaint();
        }

        /// <summary>
        /// 每帧轮询当前请求 (挂在 EditorApplication.update): 未完成直接返回, 完成则按 _step 分派到对应回调
        /// </summary>
        private void Tick()
        {
            if (!_running || _req == null || !_req.Poll()) return;

            switch (_step)
            {
                case Step.PostData:  OnPostDataDone();  break;
                case Step.UploadImg: OnUploadImgDone(); break;
                case Step.PatchData: OnPatchDataDone(); break;
            }
        }

        /// <summary>
        /// 第 1 步完成回调: 解析 data_id 成功则进第 2 步, 否则按重试策略处理
        /// </summary>
        private void OnPostDataDone()
        {
            if (_req.Kind == LqaResponseKind.Success)
            {
                string dataId = ExtractDataId(_req.Text);
                _req = null;
                if (string.IsNullOrEmpty(dataId))
                {
                    AppendLog("  -> 建数据成功但未解析到 数据ID, 响应: " + Trunc(_lastText));
                    RetryOrFailStep(BeginPostData);
                    return;
                }
                _curDataId = dataId;
                AppendLog("  -> 数据ID = " + dataId);
                BeginUploadImg();
            }
            else
            {
                AppendLog("  -> 建数据失败: " + Describe(_req));
                _req = null;
                RetryOrFailStep(BeginPostData);
            }
        }

        /// <summary>
        /// 第 2 步完成回调: 解析 file_path 成功则进第 3 步, 否则按重试策略处理
        /// </summary>
        private void OnUploadImgDone()
        {
            if (_req.Kind == LqaResponseKind.Success)
            {
                string filePath = ExtractFilePath(_req.Text);
                _req = null;
                if (string.IsNullOrEmpty(filePath))
                {
                    AppendLog("  -> 传图成功但未解析到 文件路径, 响应: " + Trunc(_lastText));
                    RetryOrFailStep(BeginUploadImg);
                    return;
                }
                _curFilePath = filePath;
                AppendLog("  -> 文件路径 = " + filePath);
                BeginPatchData();
            }
            else
            {
                AppendLog("  -> 传图失败: " + Describe(_req));
                _req = null;
                RetryOrFailStep(BeginUploadImg);
            }
        }

        /// <summary>
        /// 第 3 步完成回调: 回填成功计一次成功并进下一目录, 否则按重试策略处理
        /// </summary>
        private void OnPatchDataDone()
        {
            if (_req.Kind == LqaResponseKind.Success)
            {
                _req = null;
                _okCount++;
                AppendLog("  -> 上传成功 (数据ID=" + _curDataId + ")");
                NextDir();
            }
            else
            {
                AppendLog("  -> 回填失败: " + Describe(_req));
                _req = null;
                RetryOrFailStep(BeginPatchData);
            }
        }

        /// <summary>
        /// 当前步骤重试或当前目录失败并跳到下一个
        /// </summary>
        /// <param name="retryStep">
        /// 重试时要重新发起的步骤 (BeginPostData/BeginUploadImg/BeginPatchData)
        /// </param>
        private void RetryOrFailStep(System.Action retryStep)
        {
            if (_retry < MaxRetry - 1)
            {
                _retry++;
                AppendLog("  -> 重试 " + _retry + "/" + (MaxRetry - 1) + " ...");
                retryStep();
            }
            else
            {
                _failCount++;
                AppendLog("  -> 达重试上限, 该目录失败");
                NextDir();
            }
        }

        /// <summary>
        /// 推进到下一个目录 (下标 +1, 阶段归零, 重新进入 BeginDir)
        /// </summary>
        private void NextDir()
        {
            _index++;
            _step = Step.None;
            BeginDir();
        }

        /// <summary>
        /// 全部目录处理完毕: 摘除 Tick 轮询, 退出运行态并打印汇总
        /// </summary>
        private void Finish()
        {
            EditorApplication.update -= Tick;
            _running = false;
            _step = Step.None;
            AppendLog(string.Format("== 完成: 成功 {0}, 失败 {1} ==", _okCount, _failCount));
            Repaint();
        }

        /// <summary>
        /// 用户取消: 摘除 Tick 轮询, 中止在途请求并退出运行态
        /// </summary>
        /// <param name="reason">取消原因 (写入日志)</param>
        private void CancelUpload(string reason)
        {
            EditorApplication.update -= Tick;
            if (_req != null) { _req.Abort(); _req = null; }
            _running = false;
            _step = Step.None;
            AppendLog("== " + reason + " ==");
            Repaint();
        }

        /// <summary>致命前置错误 (配置缺失等): 记日志但不进入运行态</summary>
        /// <param name="msg">错误描述</param>
        private void Fatal(string msg)
        {
            AppendLog("[错误] " + msg);
            Repaint();
        }

        // ==========================================
        // 响应解析 & 辅助
        // ==========================================

        /// <summary>
        /// 最近一次响应体原文 (解析失败时用于打印排查)
        /// </summary>
        private string _lastText;

        /// <summary>
        /// 从建 data 响应 { code, data:{ data:{ id } } } 取 id
        /// </summary>
        /// <param name="body">第 1 步响应体 JSON 文本</param>
        /// <returns>解析到的 data_id (正整数字符串), 未解析到返回空串</returns>
        private string ExtractDataId(string body)
        {
            _lastText = body;
            var root = MiniJson.Parse(body ?? "") as Dictionary<string, object>;
            var data = root.Get<Dictionary<string, object>>("data");
            var inner = data.Get<Dictionary<string, object>>("data");
            if (inner == null) return "";
            int id = inner.GetInnerInt("id", 0);
            return id > 0 ? id.ToString() : "";
        }

        /// <summary>
        /// 从传图响应 { code, data:{ file_path } } 取 file_path
        /// </summary>
        /// <param name="body">第 2 步响应体 JSON 文本</param>
        /// <returns>解析到的 file_path, 未解析到返回空串</returns>
        private string ExtractFilePath(string body)
        {
            _lastText = body;
            var root = MiniJson.Parse(body ?? "") as Dictionary<string, object>;
            var data = root.Get<Dictionary<string, object>>("data");
            return data != null ? data.GetInnerString("file_path", "") : "";
        }

        /// <summary>
        /// 把请求失败信息翻译成可读文案 (业务归类 + HTTP 码 + 底层错误), 供日志展示
        /// </summary>
        /// <param name="req">已完成且非成功的请求句柄</param>
        private static string Describe(LqaRequest req)
        {
            var sb = new StringBuilder();
            switch (req.Kind)
            {
                case LqaResponseKind.AuthFailed:  sb.Append("鉴权未通过 (JWT无效/过期)"); break;
                case LqaResponseKind.NetworkError:  sb.Append("网络不可达 (检查Host/内网)"); break;
                case LqaResponseKind.ServerError:  sb.Append("服务端错误"); break;
                default:  sb.Append("未知"); break;
            }
            if (req.Code > 0) sb.Append(" [HTTP ").Append(req.Code).Append("]");
            if (!string.IsNullOrEmpty(req.Error)) sb.Append(" ").Append(req.Error);
            return sb.ToString();
        }

        /// <summary>
        /// 截断过长文本 (超 200 字符加省略号), 避免日志被超大响应体撑爆
        /// </summary>
        /// <param name="s">原始文本</param>
        private static string Trunc(string s)
        {
            if (string.IsNullOrEmpty(s)) return "(空)";
            return s.Length > 200 ? s.Substring(0, 200) + "..." : s;
        }

        /// <summary>
        /// 追加一行日志并请求重绘 (使日志实时可见)
        /// </summary>
        /// <param name="line">日志行文本</param>
        private void AppendLog(string line) { _log.AppendLine(line); Repaint(); }
    }
}