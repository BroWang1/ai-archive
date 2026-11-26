// ==========================================
// 文件: LQARestore\Core\Runtime\FontVariantResolver.cs
// 模块: Core (核心层)
// ==========================================

using System.Collections.Generic;
using UnityEngine;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 语言变体字体解析装饰器 (装饰 IFontResolver):
    /// 用用户配置的模板 (含 {name} 占位符) 把字体名改写为变体名后再解析,
    /// 如模板 "{name}@th" 会把 MyGameFont → MyGameFont@th
    /// 设计要点:
    ///   - 只改写字体名并清空 assetPath/guid, 强制走内层的 "按名反查" 分支;
    ///     原因: 不同语言字体扩展名可能不同 (中文 .otf / 泰语 .ttf), 且 dump 里的 guid 指向原字体,
    ///     若不清空会命中原字体, 达不到变体替换目的;
    ///   - 逐级回退, 保证文本始终可渲染, 且 "匹配不到即等于当前逻辑":
    ///       模板为空 / 不含 {name} / 改写后与原名相同 / 变体在工程查不到 → 均回退原始 fontRef;
    /// </summary>
    public class FontVariantResolver : IFontResolver
    {
        /// <summary>
        /// 模板占位符: 代表原始字体名, 会被替换为 dump 中记录的字体名
        /// </summary>
        public const string PLACEHOLDER = "{name}";

        /// <summary>
        /// 被装饰的内层解析器 (通常是 EditorFontResolver), 真正的字体加载委托给它
        /// </summary>
        private readonly IFontResolver _inner;

        /// <summary>
        /// 变体模板, 含 {name} 占位符, 如 "{name}@th"; 为空/无占位符时本装饰器不介入
        /// </summary>
        private readonly string _template;

        /// <summary>
        /// 构造装饰器
        /// </summary>
        /// <param name="inner">被装饰的内层字体解析器, 不可为 null 才有意义</param>
        /// <param name="template">含 {name} 占位符的变体模板, 如 "{name}@th"</param>
        public FontVariantResolver(IFontResolver inner, string template)
        {
            _inner = inner;
            _template = template;
        }

        /// <summary>
        /// 按变体模板改写字体名后解析; 任一环节不满足条件即回退到原始字体引用
        /// </summary>
        /// <param name="fontRef">dump 中的字体引用字典 (含 name / assetPath / guid)</param>
        /// <returns>解析到的变体字体; 变体不可用时回退内层对原始引用的解析结果</returns>
        public Font Resolve(Dictionary<string, object> fontRef)
        {
            if (_inner == null) return null;

            // 模板无效 (空 / 不含占位符) 或无字体引用 → 完全直通, 等价于未启用变体
            if (fontRef == null || string.IsNullOrEmpty(_template)
                || _template.IndexOf(PLACEHOLDER, System.StringComparison.Ordinal) < 0)
                return _inner.Resolve(fontRef);

            string name = fontRef.Get<string>("name");
            if (string.IsNullOrEmpty(name)) return _inner.Resolve(fontRef);

            // 按模板生成变体名
            string variantName = _template.Replace(PLACEHOLDER, name);

            // 改写后与原名相同 (理论上不会发生, 防御性处理) → 直通
            if (string.Equals(variantName, name, System.StringComparison.Ordinal))
                return _inner.Resolve(fontRef);

            // 只携带 name (丢弃 assetPath/guid), 强制内层按名在工程内反查变体字体
            var variantRef = new Dictionary<string, object> { { "name", variantName } };
            var variant = _inner.Resolve(variantRef);
            if (variant != null) return variant;

            // 变体缺失 → 回退原始字体引用 (即当前逻辑), 保证文本仍可渲染
            return _inner.Resolve(fontRef);
        }
    }
}