// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaProjectConfigWindow.cs
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
    /// LQA 项目配置窗口 (EditorWindow)
    /// 只管理"当前测试项目"的核心标识 project_id (见 LqaProjectConfig) —— 拉取/上传共享的上级上下文
    /// 上传随数据带的 module_id / resource_version 已拆到"上传配置"窗口 (LqaUploadConfigWindow)
    /// 纯本地配置编辑, 不涉及网络 (需要与服务器交互时统一走 LqaApiClient)
    /// </summary>
    public class LqaProjectConfigWindow : EditorWindow
    {
        /// <summary>
        /// 当前编辑中的项目配置 (OnEnable 时从 EditorPrefs 载入, 点 "保存" 时写回)
        /// </summary>
        private LqaProjectConfig _config;

        /// <summary>
        /// 整个面板的滚动位置 (内容超出窗口高度时可滚动)
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 菜单入口: Tools/LQA/平台/配置/项目配置...
        /// 打开 (或聚焦已存在的) 窗口, 并锁定为 800x500 固定大小且在主编辑器窗口内居中
        /// </summary>
        [MenuItem("Tools/LQA/平台/配置/项目配置...", false, 301)]
        private static void Open()
        {
            var win = GetWindow<LqaProjectConfigWindow>(false, "LQA 项目配置", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 500);
            win.Show();
        }

        /// <summary>
        /// 窗口启用时: 从 EditorPrefs 载入已存的项目标识到 _config
        /// </summary>
        private void OnEnable()
        {
            _config = LqaProjectConfig.Load();
        }

        /// <summary>
        /// 绘制面板: Project ID 文本框 + 保存 + 存储位置说明 + 使用须知
        /// </summary>
        private void OnGUI()
        {
            _scroll = EditorGUILayout.BeginScrollView(_scroll);

            EditorGUILayout.LabelField("项目配置 (稳定上下文)", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            // Project ID: 本窗口唯一可编辑项, 平台项目实体主键, 拉取/上传都要用
            _config.ProjectId = EditorGUILayout.TextField(
                new GUIContent("项目ID", "平台项目实体主键; 拉取/上传均需"), _config.ProjectId);

            EditorGUILayout.Space(6);

            // 保存: 把当前 _config 写回 EditorPrefs, 并弹出短暂提示
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }

            EditorGUILayout.Space(6);
            // 复用公共小工具展示 "配置存哪 (EditorPrefs 键名 + 实际落点)", 本窗口只有 Project ID 一个键
            LqaConfigGuiUtil.DrawStorageLocation(LqaProjectConfig.KEY_PROJECT_ID);

            EditorGUILayout.Space(6);
            // 使用须知: 说明本窗口只管项目标识, 以及与上传/任务/筛选各配置窗口的分工边界
            EditorGUILayout.HelpBox(
                "本窗口只管项目标识 项目ID (拉取/上传共享), 上传随数据带的 模块ID / 资源版本 在 \"上传配置\" 窗口; " +
                "任务批次 任务ID 在 \"任务配置\" 窗口; 筛选变量在 \"筛选变量\" 窗口",
                MessageType.Info);

            EditorGUILayout.EndScrollView();
        }
    }
}