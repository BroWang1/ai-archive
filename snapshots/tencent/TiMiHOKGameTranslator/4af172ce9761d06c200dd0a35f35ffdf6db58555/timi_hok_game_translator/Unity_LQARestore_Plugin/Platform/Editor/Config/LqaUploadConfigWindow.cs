// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaUploadConfigWindow.cs
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
    /// LQA 上传配置窗口 (EditorWindow)
    /// 管理 "上传数据时随数据带上" 的字段: module_id / resource_version (见 LqaUploadConfig)
    /// 这两项仅在上传回填 (PATCH /api/data/entity) 时用到, 与 "项目标识" (project_id, Project Config)
    /// 分开管理, 互不混合; 纯本地配置编辑, 不涉及网络
    /// </summary>
    public class LqaUploadConfigWindow : EditorWindow
    {
        /// <summary>
        /// 当前编辑中的上传配置 (OnEnable 时从 EditorPrefs 载入, 点 "保存" 时写回)
        /// </summary>
        private LqaUploadConfig _config;

        /// <summary>
        /// 整个面板的滚动位置 (内容超出窗口高度时可滚动)
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 菜单入口: Tools/LQA/平台/配置/上传配置...
        /// 打开 (或聚焦已存在的) 窗口, 并锁定为 800x500 固定大小且在主编辑器窗口内居中
        /// </summary>
        [MenuItem("Tools/LQA/平台/配置/上传配置...", false, 304)]
        private static void Open()
        {
            var win = GetWindow<LqaUploadConfigWindow>(false, "LQA 上传配置", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 500);
            win.Show();
        }

        /// <summary>
        /// 窗口启用时: 从 EditorPrefs 载入已存的上传字段到 _config
        /// </summary>
        private void OnEnable()
        {
            _config = LqaUploadConfig.Load();
        }

        /// <summary>
        /// 绘制面板: Module ID / Resource Version 文本框 + 保存 + 存储位置说明 + 使用须知
        /// </summary>
        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            EditorGUILayout.LabelField("上传配置 (上传时随数据带上)", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            // Module ID / Resource Version: 纯文本输入, 空则上传时不带该字段, 语义见各 GUIContent 的 tooltip
            _config.ModuleId = EditorGUILayout.TextField(
                new GUIContent("模块ID", "上传回填时随数据带上的模块 ID; 空则不带"), _config.ModuleId);
            _config.ResourceVersion = EditorGUILayout.TextField(
                new GUIContent("资源版本", "资源版本号, 如 0.20142.29.0; 上传回填时随数据带上; 空则不带"), _config.ResourceVersion);

            EditorGUILayout.Space(6);

            // 保存: 把当前 _config 写回 EditorPrefs, 并弹出短暂提示
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }

            EditorGUILayout.Space(6);
            // 复用公共小工具展示 "配置存哪 (EditorPrefs 键名 + 实际落点)", 这里把本组两个键名拼给它
            LqaConfigGuiUtil.DrawStorageLocation(
                LqaUploadConfig.KEY_MODULE_ID + " , " + LqaUploadConfig.KEY_RESOURCE_VERSION);

            EditorGUILayout.Space(6);
            // 使用须知: 说明本窗口字段仅用于上传回填, 与项目标识的分工边界, 以及留空时的语义
            EditorGUILayout.HelpBox(
                "上传配置仅在上传数据的回填步骤 (PATCH /api/data/entity) 用到, 项目标识 项目ID 在 \"项目配置\" 窗口\n" +
                "留空则上传时不带该字段",
                MessageType.Info);

            EditorGUILayout.EndScrollView();
        }
    }
}