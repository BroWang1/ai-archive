// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaFilterConfigWindow.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System.Collections.Generic;
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
    /// LQA 筛选变量配置窗口 (EditorWindow)
    /// 集中管理 "从某个任务里怎么筛数据" 的查询过滤变量:
    ///   language / count / minID / module_ids (见 LqaFilterConfig, 对应 GET /api/job/datas 的 query)
    /// Language 是这里唯一的语言来源: 平台的 GET /api/job/datas 与提交 image 的 /api/image/entity
    ///   都要 "平台内部语言码(数字 value)", 二者同一套码, 故本窗口用下拉从平台动态拉语言列表选择,
    ///   存的是数字码; 其它窗口 (如提交还原) 只读复用该值, 不再单独输入语言
    /// 与 "任务标识" (job_id, Job Config)、"项目上下文" (project_id 等, Project Config) 分开管理, 互不混合
    /// </summary>
    public class LqaFilterConfigWindow : EditorWindow
    {
        /// <summary>
        /// 当前编辑中的筛选变量配置 (OnEnable 时从 EditorPrefs 载入, 点 "保存" 时写回)
        /// </summary>
        private LqaFilterConfig _config;

        /// <summary>
        /// 整个面板的滚动位置 (内容超出窗口高度时可滚动)
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 下拉显示用的语言名数组 (形如 "en (1)"), 与 _langCodes 一一对应; 未拉取时为空
        /// </summary>
        private string[] _langNames = new string[0];

        /// <summary>
        /// 下拉各项对应的平台数字语言码数组, 与 _langNames 索引对齐; 选中项的码写入 _config.Language
        /// </summary>
        private string[] _langCodes = new string[0];

        /// <summary>
        /// 当前下拉选中项索引; -1 表示尚未选择 (通常因为还没拉取列表)
        /// </summary>
        private int _langIndex = -1;

        /// <summary>
        /// 正在进行的 "拉取语言" 请求句柄; null 表示当前无请求 (完成/取消后置回 null)
        /// </summary>
        private LqaRequest _langReq;

        /// <summary>
        /// 拉取语言进行中标志; 用于禁用按钮并显示 "拉取中..."
        /// </summary>
        private bool _langLoading;

        /// <summary>
        /// 菜单入口: Tools/LQA/平台/配置/筛选变量...
        /// 打开 (或聚焦已存在的) 窗口, 并锁定为 800x500 固定大小且在主编辑器窗口内居中
        /// </summary>
        [MenuItem("Tools/LQA/平台/配置/筛选变量...", false, 303)]
        private static void Open()
        {
            var win = GetWindow<LqaFilterConfigWindow>(false, "LQA 筛选变量", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 500);
            win.Show();
        }

        /// <summary>
        /// 窗口启用时: 从 EditorPrefs 载入已存的筛选变量到 _config
        /// </summary>
        private void OnEnable()
        {
            _config = LqaFilterConfig.Load();
        }

        /// <summary>
        /// 窗口关闭/禁用时清理: 摘除每帧轮询回调, 并中止未完成的拉取语言请求
        /// 避免窗口关掉后回调仍被触发或请求句柄泄漏
        /// </summary>
        private void OnDisable()
        {
            EditorApplication.update -= TickLang;
            if (_langReq != null) { _langReq.Abort(); _langReq = null; }
        }

        /// <summary>
        /// 绘制面板: Language 下拉(需先拉取) + Count/MinID/ModuleIds 文本框 + 保存 + 存储位置说明
        /// </summary>
        private void OnGUI()
        {
            // MouseDown 时清键盘焦点, 避免 SelectableLabel 抢焦点吃掉按钮首次点击
            if (Event.current != null && Event.current.type == EventType.MouseDown)
                GUIUtility.keyboardControl = 0;

            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            EditorGUILayout.LabelField("筛选变量 (拉取时的过滤条件)", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            // Language: 下拉选择(需先从平台拉取); 拉到列表后选中项的数字码写入 _config.Language
            EditorGUILayout.BeginHorizontal();
            // 已拉到语言列表: 显示下拉, 切换选项即把对应数字码写入 _config.Language
            if (_langNames != null && _langNames.Length > 0)
            {
                int newIdx = EditorGUILayout.Popup(
                    new GUIContent("语言", "从平台拉取的语言列表; 选中项的数字码即拉取/提交共用的平台语言码"),
                    Mathf.Clamp(_langIndex, 0, _langNames.Length - 1), _langNames);  // Clamp 防越界
                if (newIdx != _langIndex)
                {
                    _langIndex = newIdx;
                    _config.Language = _langCodes[_langIndex];  // 存数字码
                }
            }
            else
            {
                // 未拉取时: 只读显示当前已存的码 + 提示去拉取
                EditorGUILayout.PrefixLabel(new GUIContent("语言", "点右侧 \"拉取语言\" 从平台获取列表后选择"));
                EditorGUILayout.SelectableLabel(
                    string.IsNullOrEmpty(_config.Language) ? "(未选择, 请拉取语言)" : "code = " + _config.Language,
                    EditorStyles.textField, GUILayout.Height(EditorGUIUtility.singleLineHeight));
            }
            // 拉取进行中禁用按钮, 防重复点击发起多个请求
            using (new EditorGUI.DisabledScope(_langLoading))
            {
                if (GUILayout.Button(_langLoading ? "拉取中..." : "拉取语言", GUILayout.Width(80)))
                    StartLoadLanguages();
            }
            EditorGUILayout.EndHorizontal();

            // 其余筛选变量: 纯文本输入, 语义见各 GUIContent 的 tooltip
            _config.Count = EditorGUILayout.TextField(
                new GUIContent("拉取条数", "单次拉取条数"), _config.Count);
            _config.MinID = EditorGUILayout.TextField(
                new GUIContent("最小 ID", "增量游标, 只拉 id 大于它的数据"), _config.MinID);
            _config.ModuleIds = EditorGUILayout.TextField(
                new GUIContent("模块 ID", "模块过滤, 多个用 '_' 分隔 (请求时转 ','); 空=不过滤"), _config.ModuleIds);

            EditorGUILayout.Space(6);

            // 保存: 把当前 _config 写回 EditorPrefs, 并弹出短暂提示
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }

            EditorGUILayout.Space(6);
            // 复用公共小工具展示 "配置存哪 (EditorPrefs 键名 + 实际落点)", 这里把本组全部键名拼给它
            LqaConfigGuiUtil.DrawStorageLocation(
                LqaFilterConfig.KEY_LANGUAGE + " , " +
                LqaFilterConfig.KEY_COUNT + " , " + LqaFilterConfig.KEY_MIN_ID + " , " + LqaFilterConfig.KEY_MODULE_IDS);

            EditorGUILayout.Space(6);
            // 使用须知: 语言码来源、拉取前置条件 (Host/JobId)、以及各配置的分工边界
            EditorGUILayout.HelpBox(
                "语言 需从平台拉取后下拉选择 (存数字码), 拉取与提交共用该码\n" +
                "拉取语言需要有效 Host (平台连接配置) 与 任务ID (任务配置)\n" +
                "筛选变量独立管理: 任务标识在 \"任务配置\", 项目/上传字段在 \"项目配置\"/\"上传配置\"",
                MessageType.Info);

            EditorGUILayout.EndScrollView();
        }

        // ==========================================
        // 拉取语言列表 (GET /api/job/entity?mappings=1)
        // ==========================================

        /// <summary>
        /// 发起 "拉取语言列表" 请求: 校验前置条件 (Host + JobId) 后, 用 LqaApiClient 发请求,
        /// 并挂上每帧轮询回调 TickLang 等待完成 (编辑器内无协程, 用 update 轮询)
        /// </summary>
        private void StartLoadLanguages()
        {
            var conn = LqaPlatformConfig.Load();
            var job = LqaJobConfig.Load();
            // 前置校验: 缺 Host 或 JobId 都无法请求, 提示后直接返回
            if (string.IsNullOrEmpty(conn.Host)) { ShowNotification(new GUIContent("请先配置 Host")); return; }
            if (job.IsIdle) { ShowNotification(new GUIContent("请先配置 任务ID")); return; }

            _langLoading = true;
            _langReq = new LqaApiClient(conn).GetLanguageMappings(job.JobId);
            // 先摘再挂, 保证同一回调只注册一次 (避免重复订阅)
            EditorApplication.update -= TickLang;
            EditorApplication.update += TickLang;
            Repaint();
        }

        /// <summary>
        /// 每帧轮询拉取语言请求: 未完成则直接返回; 完成后摘除回调、按结果分支处理
        /// (成功则解析 body 填充下拉, 失败则提示并记日志)
        /// </summary>
        private void TickLang()
        {
            // 请求为空或尚未完成: 本帧不处理
            if (_langReq == null || !_langReq.Poll()) return;
            // 已完成: 立即摘除回调并清除进行中标志
            EditorApplication.update -= TickLang;
            _langLoading = false;

            // 非 2xx: 视为失败, 提示 + 记录 HTTP 码与错误信息, 清空句柄后重绘
            if (_langReq.Kind != LqaResponseKind.Success)
            {
                ShowNotification(new GUIContent("拉取语言失败"));
                Debug.LogWarning("[LQA] 拉取语言失败: HTTP " + _langReq.Code + " " + _langReq.Error);
                _langReq = null;
                Repaint();
                return;
            }

            // 成功: 先取出响应体再清空句柄 (避免后续解析期间句柄仍被引用), 然后解析填充下拉
            string body = _langReq.Text;
            _langReq = null;
            ParseLanguages(body);
            Repaint();
        }

        /// <summary>
        /// 解析 { data: { mappings: { language: [{name, value, label}] } } } 填充下拉, 并对齐当前已存码的选中项
        /// </summary>
        private void ParseLanguages(string body)
        {
            var names = new List<string>();
            var codes = new List<string>();
            try
            {
                // 逐层安全下钻 (DictExt.Get 命中失败返回 null), 任一层缺失都不会抛异常
                var root = MiniJson.Parse(body ?? "") as Dictionary<string, object>;
                var data = root.Get<Dictionary<string, object>>("data");
                var mappings = data.Get<Dictionary<string, object>>("mappings");
                var langs = mappings != null ? mappings.Get<List<object>>("language") : null;
                if (langs != null)
                {
                    foreach (var o in langs)
                    {
                        var d = o as Dictionary<string, object>;
                        if (d == null) continue;
                        // value 是平台数字语言码 (拉取/提交共用); 为空的项无意义, 跳过
                        string val = d.GetInnerString("value", "");
                        // 显示名优先取 name, 缺失回退 label, 再缺失就用码本身
                        string nm = d.GetInnerString("name", d.GetInnerString("label", val));
                        if (string.IsNullOrEmpty(val)) continue;
                        // 显示项带上码便于辨识, 如 "en (1)", 实际存的仍是纯数字码
                        names.Add(nm + " (" + val + ")");
                        codes.Add(val);
                    }
                }
            }
            catch (System.Exception e) { Debug.LogWarning("[LQA] 解析语言失败: " + e.Message); }

            // 一条都没解析到: 提示并保持原状 (不清空已有下拉)
            if (codes.Count == 0)
            {
                ShowNotification(new GUIContent("未解析到语言"));
                return;
            }
            _langNames = names.ToArray();
            _langCodes = codes.ToArray();
            // 若当前已存码在列表里, 选中它; 否则默认第一项并写回
            _langIndex = 0;
            for (int i = 0; i < _langCodes.Length; i++)
                if (_langCodes[i] == _config.Language) { _langIndex = i; break; }
            _config.Language = _langCodes[_langIndex];
        }
    }
}