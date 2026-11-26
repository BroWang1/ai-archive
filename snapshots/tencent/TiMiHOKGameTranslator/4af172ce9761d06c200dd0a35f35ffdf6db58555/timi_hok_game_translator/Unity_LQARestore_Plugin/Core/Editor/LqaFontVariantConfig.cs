// ==========================================
// 文件: LQARestore\Core\Editor\LqaFontVariantConfig.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// 字体变体规则配置 (编辑器侧持久化)
    /// 职责: 保存/读取 "还原时字体名的变体模板" (含 {name} 占位符, 如 "{name}@th")
    ///   设置一次即持久化 (EditorPrefs), 供 "从 Dump 文件还原" 菜单与 "自动化流水线" 共同复用;
    ///   模板为空 → 字体走 dump 原样解析 (不做变体替换); 与译文文件配置相互独立
    /// 存储: EditorPrefs, 键 LQA_Restore_FontVariantTemplate
    /// </summary>
    public class LqaFontVariantConfig
    {
        public const string KEY_FONT_VARIANT_TEMPLATE = "LQA_Restore_FontVariantTemplate";

        /// <summary>
        /// 字体变体模板 (含 {name} 占位符); 空表示未启用 → 字体按 dump 原样还原
        /// </summary>
        public string FontVariantTemplate = "";

        /// <summary>
        /// 从 EditorPrefs 读取
        /// </summary>
        public static LqaFontVariantConfig Load()
        {
            var c = new LqaFontVariantConfig();
            c.FontVariantTemplate = EditorPrefs.GetString(KEY_FONT_VARIANT_TEMPLATE, "");
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_FONT_VARIANT_TEMPLATE, FontVariantTemplate ?? "");
        }

        /// <summary>
        /// 便捷读取: 直接拿到持久化的变体模板 (无则空串)
        /// </summary>
        public static string GetTemplate()
        {
            return EditorPrefs.GetString(KEY_FONT_VARIANT_TEMPLATE, "");
        }
    }
}