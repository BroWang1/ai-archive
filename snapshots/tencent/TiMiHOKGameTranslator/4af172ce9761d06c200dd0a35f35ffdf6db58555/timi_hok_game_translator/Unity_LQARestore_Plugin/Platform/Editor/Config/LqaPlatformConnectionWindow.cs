// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaPlatformConnectionWindow.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;
using UnityEngine;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 平台连接配置窗口 (EditorWindow)
    /// 职责单一: 管理 "连接 LQA 平台" 的凭证 (Host + Authorization) 并测试连通性
    ///   - 编辑并保存 Host / JWT (落 EditorPrefs, 见 LqaPlatformConfig);
    ///   - 一键 "测试连通性": 通过 LqaApiClient 发一次带鉴权探测, 判定 网络可达 + 服务存活 + JWT 是否有效
    /// 本窗口只负责 UI 与交互; 所有与服务器的交互都委托给 LqaApiClient(见该类), 不含任务信息,
    /// 也不做下载/还原 —— 那些属于后续功能, 届时同样复用 LqaApiClient
    /// 编辑器内无 MonoBehaviour 主循环, 故用 EditorApplication.update 轮询 LqaRequest.Poll 完成状态
    /// </summary>
    public class LqaPlatformConnectionWindow : EditorWindow
    {
        /// <summary>
        /// 当前编辑中的平台连接配置 (OnEnable 时从 EditorPrefs 载入, 点 "保存" 时写回)
        /// 仅含连接凭证 Host + Authorization, 不含任何任务/筛选参数
        /// </summary>
        private LqaPlatformConfig _config;

        /// <summary>
        /// 与平台交互的客户端 (每次发起测试时基于当前 _config 新建)
        /// 所有 HTTP 交互都经由它, 本窗口不直接碰 UnityWebRequest
        /// </summary>
        private LqaApiClient _client;

        /// <summary>
        /// 测试连通性的进行中请求句柄 (null 表示当前无测试在跑)
        /// 由 StartTest 创建, Tick 每帧轮询, 完成/取消后置回 null
        /// </summary>
        private LqaRequest _testReq;

        /// <summary>
        /// 测试结果的展示类别; 决定结果区用哪种 HelpBox 图标 (信息/警告/错误) 以及按钮禁用状态
        /// </summary>
        private enum ResultKind { None, Testing, Success, Warning, Error }

        /// <summary>
        /// 当前结果类别 (默认 None = 不显示结果区); Testing 期间会禁用 "测试" 按钮、启用 "取消" 按钮
        /// </summary>
        private ResultKind _resultKind = ResultKind.None;

        /// <summary>
        /// 结果区展示的文案 (与 _resultKind 配套)
        /// </summary>
        private string _resultMsg = "";

        /// <summary>
        /// 是否显示 "明文 HTTP 被 Player Settings 拦截" 的引导 (含跳转/一键放开按钮)
        /// 仅当本次失败被判定为明文 HTTP 被禁用时置 true (见 IsInsecureHttpError)
        /// </summary>
        private bool _showInsecureHttpHint;

        /// <summary>
        /// 整个面板的滚动位置 (内容超出窗口高度时可滚动)
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// JWT 输入框样式: 基于 textArea 开启自动换行 (懒初始化, 因 GUIStyle 依赖 EditorStyles, 只能在 OnGUI 期间构造)
        /// </summary>
        private GUIStyle _wrapTextAreaStyle;

        /// <summary>
        /// 菜单入口: Tools/LQA/平台/配置/平台连接...
        /// 打开 (或聚焦已存在的) 窗口, 并锁定为 800x500 固定大小且在主编辑器窗口内居中
        /// </summary>
        [MenuItem("Tools/LQA/平台/配置/平台连接...", false, 300)]
        private static void Open()
        {
            var win = GetWindow<LqaPlatformConnectionWindow>(false, "LQA 平台连接", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 500);
            win.Show();
        }

        /// <summary>
        /// 窗口启用时: 从 EditorPrefs 载入已存的连接配置到 _config
        /// </summary>
        private void OnEnable()
        {
            _config = LqaPlatformConfig.Load();
        }

        /// <summary>
        /// 窗口关闭/禁用时清理: 中止进行中的测试请求并摘除每帧轮询回调
        /// 避免窗口关掉后回调仍被触发或请求句柄泄漏
        /// </summary>
        private void OnDisable()
        {
            // 窗口关闭时清理进行中的测试请求与轮询回调
            CancelTest();
        }

        /// <summary>
        /// 绘制面板: Host / Authorization 输入 + 保存/测试/取消按钮 + 存储位置说明 + 结果区 + 使用须知
        /// </summary>
        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            EditorGUILayout.LabelField("平台连接信息", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            // Host / Authorization: 一旦编辑内容, 清掉旧的结果/错误提示 (但测试进行中不打断)
            EditorGUI.BeginChangeCheck();

            // Host
            _config.Host = EditorGUILayout.TextField(
                new GUIContent("Host", "平台地址, 仅含 http:// 与端口 (不含路径前缀), 例: http://127.0.0.1:8080"),
                _config.Host);

            // 平台接口路径: 拼在 Host 与具体接口之间
            _config.ApiPath = EditorGUILayout.TextField(
                new GUIContent("平台接口路径",
                    "接口公共前缀, 例: /api-pro; 留空则直接拼 Host"),
                _config.ApiPath);

            // 数据下载路径: 拼在 Host 与 file_path 之间
            _config.DownloadPath = EditorGUILayout.TextField(
                new GUIContent("数据下载路径",
                    "资源/下载公共前缀, 留空则直接拼 Host"),
                _config.DownloadPath);

            // Authorization (JWT) —— 用多行自动换行区域, 便于查看/粘贴很长的 token
            // 样式懒初始化: GUIStyle 依赖 EditorStyles, 只能在 OnGUI 期间构造
            if (_wrapTextAreaStyle == null)
                _wrapTextAreaStyle = new GUIStyle(EditorStyles.textArea) { wordWrap = true };
            EditorGUILayout.LabelField(new GUIContent("Authorization (JWT)", "放入请求头 LQA-Authorization 的令牌"));
            _config.Authorization = EditorGUILayout.TextArea(
                _config.Authorization, _wrapTextAreaStyle, GUILayout.MinHeight(64));

            // 输入有变化且当前不在测试中: 清掉上次结果, 避免旧提示与新输入不一致
            if (EditorGUI.EndChangeCheck() && _resultKind != ResultKind.Testing)
                SetResult(ResultKind.None, "");

            EditorGUILayout.Space(6);

            using (new EditorGUILayout.HorizontalScope())
            {
                // 保存: 只写回 EditorPrefs, 不发起网络请求
                if (GUILayout.Button("保存", GUILayout.Height(24)))
                {
                    _config.Save();
                    ShowNotification(new GUIContent("已保存"));
                }

                // 测试进行中时禁用按钮, 避免重复发起
                EditorGUI.BeginDisabledGroup(_resultKind == ResultKind.Testing);
                if (GUILayout.Button("保存并测试连通性", GUILayout.Height(24)))
                {
                    _config.Save();
                    StartTest();
                }
                EditorGUI.EndDisabledGroup();

                // "取消测试" 只在测试进行中可用
                EditorGUI.BeginDisabledGroup(_resultKind != ResultKind.Testing);
                if (GUILayout.Button("取消测试", GUILayout.Width(90), GUILayout.Height(24)))
                {
                    CancelTest();
                    SetResult(ResultKind.None, "");
                }
                EditorGUI.EndDisabledGroup();
            }

            EditorGUILayout.Space(6);

            // 配置存储位置说明 (只读, 复用共享工具): 配置存 EditorPrefs 而非磁盘文件
            LqaConfigGuiUtil.DrawStorageLocation(
                LqaPlatformConfig.KEY_HOST + " , " + LqaPlatformConfig.KEY_AUTH + " , " +
                LqaPlatformConfig.KEY_API_PATH + " , " + LqaPlatformConfig.KEY_DOWNLOAD_PATH);

            EditorGUILayout.Space(6);

            // 结果区: 按 _resultKind 展示测试结果 (含明文 HTTP 引导)
            DrawResult();

            EditorGUILayout.Space(6);
            // 使用须知: 说明测试探测的行为、各返回码含义, 以及本窗口的职责边界
            EditorGUILayout.HelpBox(
                "测试会向 {Host}/api/test 发一次带鉴权 (LQA-Authorization) 的探测请求:\n" +
                "· 成功 (2xx) = 网络可达 + 服务存活 + 鉴权通过;\n· 302 跳登录页/401/403 = 能连上但鉴权未通过 (检查 JWT);\n· 连接错误 = 网络不通或 Host 填错 (注意内网可达);\n" +
                "本窗口只负责连接配置与连通性验证, 不含任务信息, 也不下载/还原",
                MessageType.Info);

            EditorGUILayout.EndScrollView();
        }

        /// <summary>
        /// 绘制结果区: 按 _resultKind 映射到对应图标的 HelpBox;
        /// 当本次失败为 "明文 HTTP 被禁用" 时, 追加放开步骤说明与快捷入口按钮
        /// </summary>
        private void DrawResult()
        {
            // None: 无结果可显示, 直接返回 (不占版面)
            if (_resultKind == ResultKind.None) return;

            // 结果类别 -> HelpBox 图标类型
            MessageType mt;
            switch (_resultKind)
            {
                case ResultKind.Success: mt = MessageType.Info; break;
                case ResultKind.Warning: mt = MessageType.Warning; break;
                case ResultKind.Error:   mt = MessageType.Error; break;
                default:                 mt = MessageType.None; break; // Testing
            }
            EditorGUILayout.HelpBox(_resultMsg, mt);

            // 明文 HTTP 被工程禁用时, 显示放开步骤与快捷入口
            if (_showInsecureHttpHint)
            {
                EditorGUILayout.HelpBox(
                    "允许明文 HTTP 连接的步骤:\n" +
                    "1. 菜单 Edit → Project Settings\n" +
                    "2. 左侧选 Player → Other Settings\n" +
                    "3. 找到 Configuration 分组下的 Insecure HTTP Option (部分版本叫 \"Allow downloads over HTTP\")\n" +
                    "4. 由 Not allowed 改为 Always allowed, 然后重新测试",
                    MessageType.Info);

                using (new EditorGUILayout.HorizontalScope())
                {
                    // 快捷入口: 直接打开 Player Settings, 省去用户手动翻菜单
                    if (GUILayout.Button("打开 Player Settings", GUILayout.Height(22)))
                        SettingsService.OpenProjectSettings("Project/Player");

#if UNITY_2022_1_OR_NEWER
                    // 2022.1+ 才有 insecureHttpOption API: 一键把设置改为始终允许并存盘
                    if (GUILayout.Button("一键允许 HTTP 连接", GUILayout.Height(22)))
                    {
                        PlayerSettings.insecureHttpOption = InsecureHttpOption.AlwaysAllowed;
                        AssetDatabase.SaveAssets();
                        ShowNotification(new GUIContent("已允许 HTTP 连接, 请重新测试"));
                        _showInsecureHttpHint = false;
                    }
#endif
                }
            }
        }

        // ==========================================
        // 连通性测试: 通过 LqaApiClient 发起 -> 每帧轮询 -> 按归类给出提示
        // ==========================================

        /// <summary>
        /// 发起连通性测试: 先做前置校验 (Host / Authorization 非空), 再用 LqaApiClient 发探测请求,
        /// 并挂上每帧轮询回调 Tick 等待完成 (编辑器内无协程, 用 update 轮询)
        /// </summary>
        private void StartTest()
        {
            _showInsecureHttpHint = false;  // 每次新测试前清掉上次的 HTTP 引导

            // 前置校验: 缺 Host 或 JWT 都无法发起, 提示后直接返回
            if (string.IsNullOrEmpty(_config.Host))
            {
                SetResult(ResultKind.Error, "请先填写 Host");
                return;
            }

            if (_config.Authorization == null || _config.Authorization.Trim().Length == 0)
            {
                SetResult(ResultKind.Error, "请先填写 Authorization(JWT)");
                return;
            }

            CancelTest();  // 保险: 清掉可能残留的上一次请求

            _client = new LqaApiClient(_config);
            _testReq = _client.TestConnection();
            SetResult(ResultKind.Testing, "正在测试连通性...");

            // 先摘再挂, 保证同一回调只注册一次 (避免重复订阅)
            EditorApplication.update -= Tick;
            EditorApplication.update += Tick;
        }

        /// <summary>
        /// 每帧轮询测试请求: 未完成则直接返回; 完成后摘除回调,
        /// 按 LqaResponseKind 把结果归类成 成功/鉴权失败/网络错误/服务端错误 并给出对应提示
        /// </summary>
        private void Tick()
        {
            // 请求为空或尚未完成: 本帧不处理
            if (_testReq == null || !_testReq.Poll()) return;

            // 已完成: 立即摘除回调
            EditorApplication.update -= Tick;

            long code = _testReq.Code;
            string err = _testReq.Error;

            switch (_testReq.Kind)
            {
                // 2xx: 网络 + 服务 + 鉴权全部正常
                case LqaResponseKind.Success:
                    SetResult(ResultKind.Success,
                        "连通成功 (HTTP " + code + "): 网络可达、平台服务存活、鉴权通过, 连接可用");
                    break;

                // 302 跳登录页 / 401 / 403: 能连上但 JWT 无效或过期
                case LqaResponseKind.AuthFailed:
                    SetResult(ResultKind.Warning,
                        "能连上平台, 但鉴权未通过 (HTTP " + code + "): \n" +
                        "请检查 Authorization(JWT) 是否已填写且未过期 (平台对未鉴权请求会跳登录页 302)");
                    break;

                // 网络层失败: 进一步区分 "明文 HTTP 被禁用" 与 普通不可达, 前者给放开引导
                case LqaResponseKind.NetworkError:
                    if (IsInsecureHttpError(_config.Host, err))
                    {
                        _showInsecureHttpHint = true;
                        SetResult(ResultKind.Error,
                            "连接失败: 平台地址是明文 HTTP, 但当前工程禁止了非安全 (HTTP) 连接, 请求未发出\n" +
                            "请按下方步骤在 Player Settings 中允许 HTTP 连接后重试");
                    }
                    else
                    {
                        _showInsecureHttpHint = false;
                        SetResult(ResultKind.Error,
                            "连接失败: " + (string.IsNullOrEmpty(err) ? "网络不可达" : err) +
                            "\n请检查 Host 是否正确、是否在可访问该地址的网络环境 (如内网)");
                    }
                    break;

                // 其它 4xx/5xx: 网络本身通, 但服务端返回错误
                default:  // ServerError
                    SetResult(ResultKind.Warning,
                        "能连上平台, 但服务端返回 HTTP " + code + (string.IsNullOrEmpty(err) ? "" : (": " + err)) +
                        "\n(网络本身是通的; 若为 4xx/5xx 请与平台侧确认服务状态)");
                    break;
            }

            _testReq = null;
            Repaint();
        }

        /// <summary>
        /// 中止进行中的测试: 摘除每帧轮询回调, 并 Abort + 清空请求句柄
        /// 供 "取消测试" 按钮、窗口关闭、以及新测试发起前的清理复用
        /// </summary>
        private void CancelTest()
        {
            EditorApplication.update -= Tick;
            if (_testReq != null) { _testReq.Abort(); _testReq = null; }
        }

        /// <summary>
        /// 设置结果类别与文案并请求重绘 (统一入口, 避免各处漏掉 Repaint)
        /// </summary>
        private void SetResult(ResultKind kind, string msg)
        {
            _resultKind = kind;
            _resultMsg = msg;
            Repaint();
        }

        /// <summary>
        /// 判断本次失败是否为 "明文 HTTP 被 Player Settings 禁止" 所致
        /// </summary>
        private static bool IsInsecureHttpError(string host, string err)
        {
            // 优先看底层错误文案 (不同 Unity 版本略有差异, 做宽松匹配)
            if (!string.IsNullOrEmpty(err) &&
                err.IndexOf("Insecure", System.StringComparison.OrdinalIgnoreCase) >= 0)
                return true;

            // 兜底: Host 是明文 http 且工程当前禁用了 HTTP
#if UNITY_2022_1_OR_NEWER
            if (!string.IsNullOrEmpty(host) &&
                host.TrimStart().StartsWith("http://", System.StringComparison.OrdinalIgnoreCase) &&
                PlayerSettings.insecureHttpOption == InsecureHttpOption.NotAllowed)
                return true;
#endif
            return false;
        }
    }
}