// ==========================================
// 文件: LQARestore\Core\Editor\LqaTranslationConfig.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// 译文文件配置 (编辑器侧持久化)
    /// 职责: 保存/读取 "还原时使用的 i18n_translation_xx.json (示例) 路径"
    ///   设置一次即持久化 (EditorPrefs), 供 "从 Dump 文件还原" 菜单与 "自动化流水线" 共同复用;
    ///   路径为空 → 还原回退到原文模式 (直接用 dump 里的 textContent)
    /// 存储: EditorPrefs, 键 LQA_Restore_TranslationJsonPath
    /// </summary>
    public class LqaTranslationConfig
    {
        public const string KEY_TRANSLATION_PATH = "LQA_Restore_TranslationJsonPath";

        /// <summary>
        /// 译文文件 (i18n_translation_xx.json) 绝对路径; 空表示未配置 → 原文还原
        /// </summary>
        public string TranslationJsonPath = "";

        /// <summary>
        /// 从 EditorPrefs 读取
        /// </summary>
        public static LqaTranslationConfig Load()
        {
            var c = new LqaTranslationConfig();
            c.TranslationJsonPath = EditorPrefs.GetString(KEY_TRANSLATION_PATH, "");
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_TRANSLATION_PATH, TranslationJsonPath ?? "");
        }

        /// <summary>
        /// 便捷读取: 直接拿到持久化的译文路径 (无则空串)
        /// </summary>
        public static string GetPath()
        {
            return EditorPrefs.GetString(KEY_TRANSLATION_PATH, "");
        }
    }
}