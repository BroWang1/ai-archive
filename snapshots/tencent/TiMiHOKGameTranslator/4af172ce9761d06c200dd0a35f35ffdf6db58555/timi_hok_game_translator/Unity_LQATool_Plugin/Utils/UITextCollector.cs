// ==========================================
// 文件: LQATool\Utils\UITextCollector.cs
// 模块: Utils (工具箱)
// ==========================================

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 文本集合收集器: 提供本次 Dump 的 "唯一权威文本集合"
    /// 
    /// 一次 Dump 流程中有 3 个环节都需要遍历场景里的文本 (旧版 UGUI Text 与 TMP):
    ///   1) NoText 隐藏 —— 把文本 alpha 设为 0, 截取 "无文字" 画面 (ScreenShot_NoText.png);
    ///   2) 文本 ID 图染色 —— 对文本染色生成 textToId 映射;
    ///   3) 像素可见性判定 —— 逐像素判断文本是否真正可见 (依赖 _cache);
    /// 若这三处各自调用 FindObjectsOfType / GetComponentsInChildren 遍历口径会 "漂移":
    ///   - 可能会包含 disabled Canvas (已禁用画布) 下的文本;
    ///   - 嵌套 Canvas 中的文本可能被重复统计;
    ///   - active (激活) / inactive (未激活) 的判定边界可能会不一致;
    /// 口径一旦不一致, textToId 与 _cache 的 key 集合就会错位, 导致可见性判定不可靠
    /// 
    /// [本类的职责]
    /// 把 "待处理文本" 的定义收敛到这一个方法里, 3 个环节共用同一份 List 实例,
    /// 从根源上消除口径不一致的问题
    /// 
    /// [口径定义 (契约)]
    /// 返回 "场景中所有 active 的文本 (旧版 UGUI Text 与 TMP, 统一包装为 TextLike), 排除工具自身 Canvas 子树"
    ///   - inactive (未激活) 文本必然不可见, 不进入判定流水线, 因此不收集;
    ///   - 节点树中的 inactive (未激活) 文本, 由 "缓存未命中 → 判为不可见" 这一兜底逻辑覆盖,
    ///     与此处 "只收集 active" 的口径自洽, 不会漏判也不会误判
    /// 
    /// 静态类: 无状态, 仅提供纯函数式的收集能力
    /// </summary>
    public static class UITextCollector
    {
        /// <summary>
        /// 收集本帧待处理的文本集合 (active Text, 排除工具 Canvas 子树)
        /// 
        /// [调用时机]
        /// 必须在 Dump "冻结时间 / 冻结屏幕" 之后调用一次 (即 WaitForEndOfFrame 之后),
        /// 保证拿到的是当前帧最终呈现的文本状态, 收集结果在整个 Dump 流程中复用,
        /// 不要在各环节重新收集, 否则失去 "统一口径" 的意义
        /// </summary>
        /// <param name="toolCanvas">
        /// 工具自身的 Canvas (画布), 其子树下的所有 Text 都会被排除,
        /// 避免把工具 UI 自己的文字当成被测画面的一部分, 传 null 表示不做工具 UI 排除
        /// </param>
        /// <returns>
        /// 本帧待处理的 TextLike 列表 (仅 active, 已剔除工具 Canvas 子树)
        /// 返回的是新建 List, 调用方可安全持有与遍历
        /// </returns>
        public static List<TextLike> CollectVisibilityCandidates(Canvas toolCanvas)
        {
            var result = new List<TextLike>();

            // FindObjectsOfType<Graphic>() 默认只返回 active 的组件, 保持 "仅收集 active 文本" 的口径;
            // 同时覆盖旧版 Text 与 TMP: 二者都派生自 Graphic, 遍历 Graphic 再按类型筛选
            Transform toolRoot = toolCanvas != null ? toolCanvas.transform : null;

            foreach (var g in Object.FindObjectsOfType<Graphic>())
            {
                // 非文本图形 (Image / RawImage 等) 无法包装为 TextLike, 跳过
                if (!TextLike.TryWrap(g, out var wrapped)) continue;

                // 用 transform 父链 (IsChildOf) 判定归属, 不受 Canvas.enabled 影响, 结果稳定可靠
                if (toolRoot != null && g.transform.IsChildOf(toolRoot)) continue;

                result.Add(wrapped);
            }

            return result;
        }
    }
}