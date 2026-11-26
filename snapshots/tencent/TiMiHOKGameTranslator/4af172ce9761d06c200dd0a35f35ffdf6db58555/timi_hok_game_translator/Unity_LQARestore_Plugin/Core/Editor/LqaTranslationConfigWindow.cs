// ==========================================
// 文件: LQARestore\Core\Editor\LqaTranslationConfigWindow.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using System.IO;
using UnityEditor;
using UnityEngine;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// 译文文件配置窗口 (EditorWindow)
    /// 设置一次即持久化 (见 LqaTranslationConfig), 供 "从 Dump 文件还原" 与 "自动化流水线"复用:
    ///   配了有效路径 → 按 keyHash / original 匹配译文还原; 留空/清除 → 回退原文还原
    /// 纯本地配置编辑, 不涉及网络
    /// </summary>
    public class LqaTranslationConfigWindow : EditorWindow
    {
        private LqaTranslationConfig _config;

        [MenuItem("Tools/LQA/还原/译文文件配置...", false, 202)]
        private static void Open()
        {
            var win = GetWindow<LqaTranslationConfigWindow>(false, "LQA 译文文件配置", true);
            LqaWindowLayout.ApplyFixedCentered(win, 800, 200);
            win.Show();
        }

        private void OnEnable()
        {
            _config = LqaTranslationConfig.Load();
        }

        private void OnGUI()
        {
            EditorGUILayout.LabelField("译文文件配置 (持久化)", EditorStyles.boldLabel);
            EditorGUILayout.Space(2);

            EditorGUILayout.BeginHorizontal();
            _config.TranslationJsonPath = EditorGUILayout.TextField(
                new GUIContent("译文文件", "i18n_translation_xx.json (示例) 绝对路径; 留空则用原文还原"),
                _config.TranslationJsonPath);
            if (GUILayout.Button("浏览...", GUILayout.Width(70)))
            {
                // 不设默认起始目录
                string p = EditorUtility.OpenFilePanel("选择 i18n_translation_xx.json (示例)", "", "json");
                if (!string.IsNullOrEmpty(p)) _config.TranslationJsonPath = p;
            }
            if (GUILayout.Button("清除", GUILayout.Width(50)))
            {
                _config.TranslationJsonPath = "";
                GUIUtility.keyboardControl = 0;
            }
            EditorGUILayout.EndHorizontal();

            // 当前状态提示
            string path = _config.TranslationJsonPath;
            if (string.IsNullOrEmpty(path))
                EditorGUILayout.HelpBox("未配置译文文件: 还原将直接使用 dump 中的原文 (textContent)", MessageType.None);
            else if (!File.Exists(path))
                EditorGUILayout.HelpBox("路径不存在: 还原时会回退为原文还原", MessageType.Warning);
            else
                EditorGUILayout.HelpBox("已配置: 还原将按 keyHash / original 匹配译文", MessageType.Info);

            EditorGUILayout.Space(6);
            if (GUILayout.Button("保存", GUILayout.Height(24)))
            {
                _config.Save();
                ShowNotification(new GUIContent("已保存"));
            }
        }
    }
}