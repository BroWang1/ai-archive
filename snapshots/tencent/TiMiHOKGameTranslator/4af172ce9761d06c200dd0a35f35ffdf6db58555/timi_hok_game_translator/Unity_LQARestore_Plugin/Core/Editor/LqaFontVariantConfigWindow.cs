// ==========================================
// 文件: LQARestore\Core\Editor\LqaFontVariantConfigWindow.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using UnityEditor;
using UnityEngine;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// 字体变体配置窗口 (EditorWindow)
    /// 设置一次即持久化 (见 LqaFontVariantConfig), 供 "从 Dump 文件还原" 与 "自动化流水线" 复用:
    ///   配了含 {name} 的模板 → 还原时把字体名改写为变体 (如 {name}@th → MyGameFont@th),
    ///     工程内找不到该变体时回退原字体; 留空/清除 → 字体按 dump 原样还原
    /// 纯本地配置编辑, 不涉及网络
    /// </summary>
    public class LqaFontVariantConfigWindow : EditorWindow
    {
        private LqaFontVariantConfig _config;

        [MenuItem("Tools/LQA/还原/字体变体配置...", false, 203)]
        private static void Open()
        {
            var win = GetWindow<LqaFontVariantConfigWindow>(false, "LQA 字体变体配置", true);
            LqaWindowLayout.ApplyFixedCentered(win, 500, 200);
            win.Show();
        }

        private void OnEnable()
        {
            _config = LqaFontVariantConfig.Load();
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("字体变体配置 (持久化)", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            EditorGUILayout.BeginHorizontal();
            _config.FontVariantTemplate = EditorGUILayout.TextField(
                new GUIContent("字体变体模板",
                    "用 {name} 代表原字体名, 如 {name}@th 会把 MyGameFont 匹配为 MyGameFont@th; 留空则字体按 dump 原样还原"),
                _config.FontVariantTemplate);
            if (GUILayout.Button("清除", GUILayout.Width(50)))
            {
                _config.FontVariantTemplate = "";
                GUIUtility.keyboardControl = 0;
            }
            EditorGUILayout.EndHorizontal();

            // 当前状态提示
            string tpl = _config.FontVariantTemplate;
            if (string.IsNullOrEmpty(tpl))
                EditorGUILayout.HelpBox("未配置变体模板: 字体将按 dump 原样还原", MessageType.None);
            else if (!tpl.Contains(FontVariantResolver.PLACEHOLDER))
                EditorGUILayout.HelpBox("模板缺少 {name} 占位符: 该配置无效, 还原时将被忽略", MessageType.Warning);
            else
                EditorGUILayout.HelpBox("已配置: 还原时字体名将按模板改写, 工程内找不到变体则回退原字体", MessageType.Info);

            EditorGUILayout.Space(6);
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }
        }
    }
}