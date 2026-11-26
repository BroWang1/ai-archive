// ==========================================
// 文件: LQATool\Services\ProjectCustomExtractors.cs
// 模块: Services (业务)
// ==========================================

using System;
using UnityEngine;

// 通过 using static 让 H.AddXxx / H.TryGetFieldValue 写起来更紧凑
// 这样下面就可以直接调用 TryGetFieldValue / AddEnum / AddColor / AddVector2 等,
// 而无需前缀 CustomExtractorHelpers
using static LQATool.Services.CustomExtractorHelpers;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// 项目自定义组件的属性提取器注册入口 (与通用 Unity 组件的 ComponentExtractors 解耦)
    ///
    /// 设计目的:
    ///   - 通用 UI 组件 (Canvas / Text / Image / ScrollRect 等) 在 ComponentExtractors 中集中注册;
    ///   - 而项目专属脚本 (如 XxxxLocalize / Xxxx.XxxxText) 由于类型可能不在本插件的引用范围内,
    ///     因此单独放到本文件, 通过 ComponentExtractors.RegisterByTypeName(string, Action{Component, UINodeData})
    ///     以 "字符串类型名 + 反射读字段" 的松耦合方式注册, 避免直接依赖项目程序集;
    ///   - 目标类型若不存在于当前工程, 会被 RegisterByTypeName 静默跳过, 不影响插件其他功能;
    ///
    /// 调用链: ComponentExtractors 的静态构造函数会调用 RegisterAll
    /// </summary>
    internal static class ProjectCustomExtractors
    {
        /// <summary>
        /// 注册所有项目自定义组件的提取器
        /// 由 ComponentExtractors 的静态构造在通用提取器注册之后调用一次
        /// </summary>
        internal static void RegisterAll()
        {
            // 在此按需注册本项目的自定义组件 (目标类型不存在于当前工程时会被静默跳过, 不影响其它功能)
            // 可直接复用的辅助方法 (均来自 using static CustomExtractorHelpers):
            //   TryGetFieldValue<T>(comp, "字段名", out value) 反射读字段;
            //   AddEnum / AddColor / AddVector2 (node, 组件键, 属性键, 值) 类型化写入
            // 用法示例: 删掉下方 /* */ 这对块注释符即可启用示例调用,
            // 同时需一并放开本类末尾被 /* */ 包裹的 RegisterXxxxLocalize / RegisterXxxxText 方法体, 并改成你自己的组件名与字段名:
            
            /*
            // 本地化组件: 用于导出翻译时匹配 keyHash → 译文
            RegisterXxxxLocalize();
            // 富文本组件: 用于还原描边 / 阴影 / 特效等文本视觉参数
            RegisterXxxxText();
            */

        }

        /*
        // ==========================================
        // XxxxLocalize 组件 [XxxxLocalize]
        // ==========================================

        /// <summary>
        /// 注册 XxxxLocalize 组件的字段提取器
        /// 只导出 keyHash 一个字段, 供 LQA 侧根据哈希值反查原始翻译 Key
        /// </summary>
        private static void RegisterXxxxLocalize()
        {
            // 使用短类型名 "XxxxLocalize" 注册, RegisterByTypeName 会遍历已加载程序集找到匹配的 Component 子类
            ComponentExtractors.RegisterByTypeName("XxxxLocalize", (comp, node) =>
            {
                // 去掉注释可以打印所有字段 (调试用):
                // DumpAllFieldsForDebug(comp, true);
                // DumpAllFieldsForDebug(comp, false);
                // 在不清楚目标组件的字段名 / 属性名时, 打开这两行可以在控制台一次性看到所有可读成员

                // 反射读取 keyHash 字段 (存在性未知, 用 object 兜底以兼容 string / int / long / 自定义结构等各种实际类型)
                // 找不到字段、异常或值为 null 时直接放弃, 不写入 ObjectData
                if (!TryGetFieldValue<object>(comp, "keyHash", out var val) || val == null) return;

                // 统一按 ToString() 序列化, 对于数字型哈希, 结果就是十进制字符串, 对于字符串哈希, 就是其原文
                string s = val.ToString();
                // 空串直接跳过, 避免面板 / JSON 中出现无意义的空字段
                if (string.IsNullOrEmpty(s)) return;

                // 写入 ObjectData["XxxxLocalize"]["keyHash"] = "\"xxx\""
                // 外层双引号是 JSON 字符串字面量的一部分, 保证最终 JSON 中该值形如 "8X88XX8X88X888X8"
                node.AddComponentProperty("XxxxLocalize", "keyHash", $"\"{s}\"");
            });
        }

        // ==========================================
        // XxxxText 组件 [Xxxx.XxxxText]
        // ==========================================

        /// <summary>
        /// 注册 Xxxx.XxxxText 组件的字段提取器
        /// 导出文本特效类型、当前描边颜色/距离、当前阴影颜色/距离, 用于外部还原工程按 1:1 复刻文本视觉
        ///
        /// 采集的都是 "Current*" 字段: 说明 XxxxText 内部会根据主题 / 状态动态计算最终样式,
        /// 直接读运行时值比读原始序列化字段更贴近玩家实际看到的效果
        /// </summary>
        private static void RegisterXxxxText()
        {
            // 使用带命名空间的全名注册, 避免与其他项目里同名的 "XxxxText" 短名冲突
            ComponentExtractors.RegisterByTypeName("Xxxx.XxxxText", (comp, node) =>
            {
                // 组件键统一使用短名 "XxxxText" (与外部 JSON 表结构约定一致)
                const string K = "XxxxText";

                // 文本特效类型 (枚举: 无 / 描边 / 阴影 / 描边+阴影 等)
                // 用基类 Enum 接住, 避免在此处硬引用具体枚举类型 (不同版本可能改名 / 加值)
                if (TryGetFieldValue<Enum>(comp, "TextEffectType", out var effectType))
                {
                    AddEnum(node, K, "textEffectType", effectType);
                }

                // 当前描边颜色 (RGBA)
                if (TryGetFieldValue<Color>(comp, "CurrentOutlineColor", out var outlineColor))
                {
                    AddColor(node, K, "outlineColor", outlineColor);
                }

                // 当前描边距离 (X / Y 方向的像素偏移量)
                if (TryGetFieldValue<Vector2>(comp, "CurrentOutlineDistance", out var outlineDistance))
                {
                    AddVector2(node, K, "outlineDistance", outlineDistance);
                }

                // 当前阴影颜色 (RGBA)
                if (TryGetFieldValue<Color>(comp, "CurrentShadowColor", out var shadowColor))
                {
                    AddColor(node, K, "shadowColor", shadowColor);
                }

                // 当前阴影距离 (X / Y 方向的像素偏移量)
                if (TryGetFieldValue<Vector2>(comp, "CurrentShadowDistance", out var shadowDistance))
                {
                    AddVector2(node, K, "shadowDistance", shadowDistance);
                }
            });
        }
        */

    }
}