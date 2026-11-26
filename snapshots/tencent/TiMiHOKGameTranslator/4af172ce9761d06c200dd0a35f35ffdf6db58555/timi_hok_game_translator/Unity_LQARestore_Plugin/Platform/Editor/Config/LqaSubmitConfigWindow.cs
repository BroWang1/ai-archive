// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaSubmitConfigWindow.cs
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
    /// LQA 提交结果配置窗口 (EditorWindow)
    /// 管理 "提交还原结果" (POST /api/image/entity) 的配套开关: ai_sign (见 LqaSubmitConfig)
    /// 该开关被 "提交还原结果" 与 "自动化流水线" 两处提交步骤共用; 纯本地配置编辑, 不涉及网络
    /// </summary>
    public class LqaSubmitConfigWindow : EditorWindow
    {
        /// <summary>
        /// 当前编辑中的提交配置 (OnEnable 时从 EditorPrefs 载入, 点 "保存" 时写回)
        /// </summary>
        private LqaSubmitConfig _config;

        /// <summary>
        /// 整个面板的滚动位置 (内容超出窗口高度时可滚动)
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 菜单入口: Tools/LQA/平台/配置/提交配置...
        /// 打开 (或聚焦已存在的) 窗口, 并锁定为 800x500 固定大小且在主编辑器窗口内居中
        /// </summary>
        [MenuItem("Tools/LQA/平台/配置/提交配置...", false, 305)]
        private static void Open()
        {
            var win = GetWindow<LqaSubmitConfigWindow>(false, "LQA 提交配置", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 500);
            win.Show();
        }

        /// <summary>
        /// 窗口启用时: 从 EditorPrefs 载入已存的提交配置到 _config
        /// </summary>
        private void OnEnable()
        {
            _config = LqaSubmitConfig.Load();
        }

        /// <summary>
        /// 绘制面板: 触发 AI 勾选框 + 保存 + 存储位置说明 + 使用须知
        /// </summary>
        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            EditorGUILayout.LabelField("提交结果配置 (提交还原结果时生效)", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            _config.TriggerAI = EditorGUILayout.Toggle(
                new GUIContent("提交后触发 AI 检测",
                    "勾选则提交图片时 AI标记=1, 平台触发 AI 检测/建bug; 取消则只存图与框 (AI标记=0)"), _config.TriggerAI);

            EditorGUILayout.Space(6);

            // 保存: 把当前 _config 写回 EditorPrefs, 并弹出短暂提示
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }

            EditorGUILayout.Space(6);
            // 复用公共小工具展示 "配置存哪 (EditorPrefs 键名 + 实际落点)"
            LqaConfigGuiUtil.DrawStorageLocation(LqaSubmitConfig.KEY_TRIGGER_AI);

            EditorGUILayout.Space(6);
            // 使用须知: 说明本开关作用于提交还原结果与自动流水线的提交步骤
            EditorGUILayout.HelpBox(
                "本开关作用于 \"提交还原结果\" 与 \"自动化流水线\" 的提交步骤 (POST /api/image/entity)\n" +
                "勾选: 平台收到图后触发 AI 检测/建bug; 取消: 只存图与框",
                MessageType.Info);

            EditorGUILayout.EndScrollView();
        }
    }
}