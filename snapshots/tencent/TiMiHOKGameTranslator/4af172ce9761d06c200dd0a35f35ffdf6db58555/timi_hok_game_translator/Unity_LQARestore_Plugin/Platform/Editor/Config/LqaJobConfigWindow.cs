// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaJobConfigWindow.cs
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
    /// LQA 任务配置窗口 (EditorWindow)
    /// 只管理 "当前操作的是哪个任务批次" —— job_id 这一个任务标识
    /// 任务从属于项目, 故窗口顶部只读显示当前所属 project_id (取自 LqaProjectConfig), 提醒用户
    /// 正在为哪个项目配任务, 避免张冠李戴; 若要改项目请去 "项目配置" 窗口
    /// 纯本地配置编辑, 不涉及网络 (需要与服务器交互时统一走 LqaApiClient)
    /// </summary>
    public class LqaJobConfigWindow : EditorWindow
    {
        /// <summary>
        /// 当前编辑中的任务配置 (OnEnable 时从 EditorPrefs 载入, 点 "保存" 时写回)
        /// </summary>
        private LqaJobConfig _config;

        /// <summary>
        /// 只读展示用的当前所属项目 ID (取自 LqaProjectConfig, 非本窗口编辑)
        /// 仅用于顶部提示 "任务属于哪个 project_id"; 缺省/未配置时为 "0"
        /// </summary>
        private string _ownerProjectId = "0";  // 只读展示: 当前所属项目

        /// <summary>
        /// 整个面板的滚动位置 (内容超出窗口高度时可滚动)
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 菜单入口: Tools/LQA/平台/配置/任务配置...
        /// 打开 (或聚焦已存在的) 窗口, 并锁定为 800x500 固定大小且在主编辑器窗口内居中
        /// </summary>
        [MenuItem("Tools/LQA/平台/配置/任务配置...", false, 302)]
        private static void Open()
        {
            var win = GetWindow<LqaJobConfigWindow>(false, "LQA 任务配置", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 500);
            win.Show();
        }

        /// <summary>
        /// 窗口启用时: 从 EditorPrefs 载入已存任务标识, 并读取当前所属项目 ID 用于顶部只读展示
        /// </summary>
        private void OnEnable()
        {
            _config = LqaJobConfig.Load();
            _ownerProjectId = LqaProjectConfig.Load().ProjectId;
        }

        /// <summary>
        /// 窗口重新获得焦点时: 刷新所属项目 ID
        /// 防止用户在 "项目配置" 窗口改了 project_id 后, 本窗口顶部仍显示旧值
        /// </summary>
        private void OnFocus()
        {
            // 重新聚焦时刷新所属项目, 保证与 "项目配置" 窗口的改动同步
            _ownerProjectId = LqaProjectConfig.Load().ProjectId;
        }

        /// <summary>
        /// 绘制面板: 顶部只读展示所属项目上下文 + Job ID 文本框 + 保存 + 存储位置说明 + 使用须知
        /// </summary>
        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            // 只读: 所属项目上下文
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PrefixLabel(new GUIContent("所属项目 (仅查看)", "任务从属于该 项目ID; 修改请去 项目配置 窗口"));
            // 未配置 (空或 "0") 时给出引导文案, 否则显示 project_id 原值; SelectableLabel 只读可复制不回写
            EditorGUILayout.SelectableLabel(
                string.IsNullOrEmpty(_ownerProjectId) || _ownerProjectId == "0"
                    ? "(未配置, 请先在 Tools/LQA/平台/配置/项目配置 设置 项目ID)"
                    : "project_id = " + _ownerProjectId,
                EditorStyles.textField, GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(4);
            EditorGUILayout.LabelField("任务配置", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            // Job ID: 本窗口唯一可编辑项, 空或 "0" 视为无远程任务
            _config.JobId = EditorGUILayout.TextField(
                new GUIContent("任务 ID", "任务 ID; \"0\" 表示无远程任务"), _config.JobId);

            EditorGUILayout.Space(6);

            // 保存: 把当前 _config 写回 EditorPrefs, 并弹出短暂提示
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }

            EditorGUILayout.Space(6);
            // 复用公共小工具展示 "配置存哪 (EditorPrefs 键名 + 实际落点)", 本窗口只有 Job ID 一个键
            LqaConfigGuiUtil.DrawStorageLocation(LqaJobConfig.KEY_JOB_ID);

            EditorGUILayout.Space(6);
            // 使用须知: 说明本窗口与筛选变量/项目配置的分工边界, 以及 Job ID 为空/0 时的空闲语义
            EditorGUILayout.HelpBox(
                "本窗口只管任务标识 任务ID, 筛选变量 (语言/数量/最小ID/模块ID) 在 \"筛选配置\" 窗口; " +
                "稳定的 项目ID / 模块ID / 资源版本 在 \"项目配置\" 窗口,\n" +
                "任务ID 为空或 0 时视为无远程任务, 后续拉取不会发起",
                MessageType.Info);

            EditorGUILayout.EndScrollView();
        }
    }
}