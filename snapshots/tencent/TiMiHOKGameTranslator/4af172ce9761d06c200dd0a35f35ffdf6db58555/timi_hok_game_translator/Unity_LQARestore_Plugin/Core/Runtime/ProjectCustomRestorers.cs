// ==========================================
// 文件: LQARestore\Core\Runtime\ProjectCustomRestorers.cs
// 模块: Core (核心层)
// ==========================================

using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 项目专属组件的还原器注册入口 (与通用 TextNodeBuilder 解耦)
    /// 设计目的:
    ///   - 通用 UI 组件 (Text / Canvas / RectTransform 等) 的还原由 TextNodeBuilder 直接完成;
    ///   - 而项目专属特效 (如 Xxxx 系列文本的描边 / 阴影) 只在特定工程里出现,
    ///     因此单独放到本文件, 通过 NodePostProcessors.Register 以 "后处理器回调" 的松耦合方式挂入,
    ///     使 NodePostProcessors / TextNodeBuilder 无需感知任何项目专属键名;
    /// 对称设计: 与采集侧 ProjectCustomExtractors 一一对应 ——
    ///   采集侧把项目专属组件属性抽成 JSON (专属键名 "XxxxText" 只在采集侧那份文件出现),
    ///   还原侧则在此把同一份 JSON 还原回 Unity 组件/特效 (专属键名 "XxxxText" 也只在本文件出现)
    /// 调用链: NodePostProcessors 的静态构造函数会调用 RegisterAll
    /// </summary>
    internal static class ProjectCustomRestorers
    {
        /// <summary>
        /// 注册所有项目专属组件的还原器
        /// 由 NodePostProcessors 的静态构造在初始化时调用一次
        /// </summary>
        internal static void RegisterAll()
        {
            // 在此按需注册本项目的自定义还原器 (对应 JSON 块缺失时后处理器会直接 return, 不影响其它节点)
            // 可直接复用的辅助工具:
            //   NodePostProcessors.Register((go, objectData) => {...}) 挂入后处理回调, go 为还原出的节点, objectData 为其 JSON 属性;
            //   objectData.Get<Dictionary<string, object>>("组件键") 取某组件的属性块 (缺失返回 null 即代表该节点无此组件);
            //   dict.GetInnerString / GetInnerFloat (属性键[, 默认值]) 从属性块读取标量值;
            //   本类私有 ReadColor(dict) 由含 r/g/b/a 的字典构造 Color
            // 用法示例: 仿照下方 RegisterXxxxLocalize / RegisterXxxxText, 新增一个 private static void RegisterYourComp() 方法,
            // 在其中 NodePostProcessors.Register(...) 写还原逻辑, 再在上方本方法里补一行 RegisterYourComp() 调用, 并改成你自己的 JSON 键名:

            /*
            // 本地化组件: 把 keyHash 作为数据还原到 LQAKeyInfo 组件, 供 Inspector 查看
            RegisterXxxxLocalize();
            // 富文本组件: 用于还原描边 / 阴影等文本视觉特效
            RegisterXxxxText();
            */

        }

        /*
        // ==========================================
        // XxxxLocalize 组件 [键名 "XxxxLocalize"]
        // ==========================================

        /// <summary>
        /// 注册 XxxxLocalize 的还原后处理器
        /// 从采集侧导出的 keyHash 中读取本地化 key, 挂一个轻量的 LQAKeyInfo 组件承载它,
        /// 使还原出的文本对象在 Inspector 中可直接查看其对应的本地化 key
        /// 注意: 不还原原工程的 XxxxLocalize 组件本身 (类型不在本还原工程引用范围内, 且无本地化配置表驱动),
        /// 仅把 keyHash 作为数据还原, 与 XxxxText 用内置 Outline/Shadow 近似而不还原组件本身的取舍一致
        /// </summary>
        private static void RegisterXxxxLocalize()
        {
            NodePostProcessors.Register((go, objectData) =>
            {
                // 读取该节点 JSON 中的 "XxxxLocalize" 属性块; 缺失说明此节点没有该组件, 直接跳过
                var locProps = objectData.Get<Dictionary<string, object>>("XxxxLocalize");
                if (locProps == null) return;

                // 取 keyHash; 为空则不挂组件 (避免产生无意义的空信息组件)
                string keyHash = locProps.GetInnerString("keyHash");
                if (string.IsNullOrEmpty(keyHash)) return;

                // 挂轻量说明组件, 回填 keyHash 供 Inspector 查看
                var info = go.AddComponent<LQAKeyInfo>();
                info.keyHash = keyHash;
            });
        }

        // ==========================================
        // XxxxText 组件 [键名 "XxxxText"]
        // ==========================================

        /// <summary>
        /// 注册 XxxxText 的还原后处理器
        /// 根据采集侧导出的 textEffectType, 在还原后的节点上附加 Outline (描边) 或 Shadow (阴影) 组件,
        /// 并回填其颜色与距离参数, 以 1:1 复刻原工程的文本视觉效果
        /// 注意: 原工程的 Xxxx.XxxxText 类型不在本还原插件的引用范围内,
        /// 因此这里不还原该组件本身, 而是用 Unity 内置的 Outline / Shadow 近似其视觉结果
        /// </summary>
        private static void RegisterXxxxText()
        {
            NodePostProcessors.Register((go, objectData) =>
            {
                // 读取该节点 JSON 中的 "XxxxText" 属性块; 缺失说明此节点没有该特效, 直接跳过
                var projectProps = objectData.Get<Dictionary<string, object>>("XxxxText");
                if (projectProps == null) return;
                // Outline / Shadow 继承自 BaseMeshEffect, 通过修改 Graphic 的网格顶点生效, 仅作用于旧版 UGUI Text;
                // TMP 自行生成网格, 不走该管线, 挂这两个特效无效, 故这里仅在存在旧版 Text 时附加
                // (TMP 的描边/阴影需在其材质层面还原, 超出当前近似还原范围)
                if (!go.TryGetComponent<Text>(out _)) return;

                // 特效类型: 与采集侧 AddEnum 写入的枚举名对应 (忽略大小写以增强容错)
                string effect = projectProps.GetInnerString("textEffectType");
                if (string.Equals(effect, "Outline", StringComparison.OrdinalIgnoreCase))
                {
                    // 描边: 附加 Outline, 回填颜色与偏移距离
                    var outline = go.AddComponent<Outline>();
                    var oc = projectProps.Get<Dictionary<string, object>>("outlineColor");
                    if (oc != null) outline.effectColor = ReadColor(oc);
                    var od = projectProps.Get<Dictionary<string, object>>("outlineDistance");
                    // 缺省距离 (1, -1) 对应 Unity Outline 的默认效果距离
                    if (od != null) outline.effectDistance = new Vector2(od.GetInnerFloat("x", 1f), od.GetInnerFloat("y", -1f));
                }
                else if (string.Equals(effect, "Shadow", StringComparison.OrdinalIgnoreCase))
                {
                    // 阴影: 附加 Shadow, 回填颜色与偏移距离
                    var shadow = go.AddComponent<Shadow>();
                    var sc = projectProps.Get<Dictionary<string, object>>("shadowColor");
                    if (sc != null) shadow.effectColor = ReadColor(sc);
                    var sd = projectProps.Get<Dictionary<string, object>>("shadowDistance");
                    // 缺省距离 (1, -1) 对应 Unity Shadow 的默认效果距离
                    if (sd != null) shadow.effectDistance = new Vector2(sd.GetInnerFloat("x", 1f), sd.GetInnerFloat("y", -1f));
                }
                // 其它 (无特效 / 描边+阴影 等) 暂不还原
            });
        }
        */

        // ==========================================
        // 辅助方法
        // ==========================================

        /// <summary>
        /// 从颜色属性字典 (含 r/g/b/a) 读取并构造 Color
        /// 独立保留一份, 避免依赖 TextNodeBuilder 的私有 ReadColor, 使本文件可与其解耦
        /// </summary>
        /// <param name="d">颜色属性字典, 为 null 时返回白色 (Color.white)</param>
        /// <returns>解析出的 Color, 各通道缺省值均为 1</returns>
        private static Color ReadColor(Dictionary<string, object> d)
        {
            if (d == null) return Color.white;
            return new Color(d.GetInnerFloat("r", 1), d.GetInnerFloat("g", 1),
                             d.GetInnerFloat("b", 1), d.GetInnerFloat("a", 1));
        }
    }
}