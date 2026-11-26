// ==========================================
// 文件: LQATool\Services\UIDumpService.TextIdMap.cs
// 模块: Services (业务)
// ==========================================

using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using System.Text.RegularExpressions;
using LQATool.Utils;
using LQATool.Config;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// UIDumpService 的分部实现 —— 文本 ID 图 (TextIdMap) 生成模块
    ///
    /// 核心思路: 给场景中每个可见 UI 文本染上一个由整数 ID 编码而来的唯一颜色
    /// (见 LQATool.Utils.TextIdCodec), 再整屏渲染到 RenderTexture 并读回像素
    /// 这样截图里每个像素的颜色都能反解出它属于哪个文本 (ID), 为后续逐像素级的
    /// 文本区域定位 / AABB 计算提供精确依据
    ///
    /// 相比传统 "包围盒差分" 方案, 染色法能天然处理文本被裁剪、遮挡、重叠的情况;
    /// 仅当文本数量超过颜色编码容量 (LQATool.Utils.TextIdCodec.Capacity) 时,
    /// 超出部分会判定为 "不可见", 不染色;
    /// </summary>
    public partial class UIDumpService
    {
        /// <summary>
        /// 单个文本染色前的现场备份
        /// 染色会临时篡改文本的颜色 / 内容 / 透明度, 截图完成后必须逐项还原,
        /// 否则会污染玩家真实看到的游戏画面
        /// </summary>
        private struct TextIdBackup
        {
            /// <summary>
            /// 被染色的目标文本组件
            /// </summary>
            public TextLike text;
            /// <summary>
            /// 染色前的原始文字颜色 (还原时写回)
            /// </summary>
            public Color originalColor;
            /// <summary>
            /// 染色前的原始文字内容 (因为可能被 StripColorTags 改写, 需还原)
            /// </summary>
            public string originalText;
            /// <summary>
            /// 染色前 CanvasRenderer 的原始 alpha (染色时被强制拉到 1, 需还原)
            /// </summary>
            public float originalCrAlpha;
        }

        /// <summary>
        /// 文本 "近乎不可见" 的 alpha 阈值
        /// CanvasRenderer alpha 低于此值的文本视为不可见, 直接跳过不染色 (也不占用 ID)
        /// 避免为屏幕上根本看不到的文本浪费 ID 容量
        /// </summary>
        private const float InvisibleAlphaThreshold = 0.04f;

        /// <summary>
        /// 生成文本 ID 图: 为每个可见文本分配唯一 ID 并染成对应颜色, 渲染整屏后读回像素
        /// </summary>
        /// <param name="cameras">场景所有相机 (已按 depth 升序排序)</param>
        /// <param name="topCamera">最上层相机 (用于把 Overlay Canvas 临时挂到相机模式)</param>
        /// <param name="rt">用于离屏渲染的 RenderTexture (后台画板)</param>
        /// <param name="width">读取宽度 (像素), 通常为 Screen.width</param>
        /// <param name="height">读取高度 (像素), 通常为 Screen.height</param>
        /// <param name="toolCanvas">本工具自身的 Canvas, 需在渲染时排除, 避免把工具 UI 也拍进去</param>
        /// <param name="texts">候选文本列表 (调用方已收集好的待染色文本)</param>
        /// <param name="dumpDir">调试图输出目录</param>
        /// <param name="textToId">[输出] 文本 Transform → 分配到的 ID 的映射</param>
        /// <param name="pureIdMap">[输出] "纯净版" ID 图: 隐藏所有非文本图形后再渲染一次, 排除遮挡干扰</param>
        /// <returns>
        /// 常规 ID 图的逐像素颜色数组 (RGBA32)
        /// 若没有任何可染色文本则返回 null
        /// </returns>
        private Color32[] CaptureTextIdMap(
            Camera[] cameras, Camera topCamera, RenderTexture rt,
            int width, int height, Canvas toolCanvas, IReadOnlyList<TextLike> texts, string dumpDir,
            out Dictionary<Transform, int> textToId, out Color32[] pureIdMap)
        {
            // 初始化输出参数
            textToId = new Dictionary<Transform, int>();
            pureIdMap = null;

            // 记录所有被染色文本的现场, finally 中据此逐一还原
            var textBackups = new List<TextIdBackup>();
            // 记录被临时拉满 alpha 的 CanvasGroup (Key=组件, Value=原始 alpha), 用于还原
            var canvasGroupBackups = new Dictionary<CanvasGroup, float>();

            try
            {
                // ID 从 1 开始编号 (0 在 TextIdCodec 中代表 "无效/无文本")
                int id = 1;
                foreach (var t in texts)
                {
                    // TextLike 普通类判空 + 底层 graphic 存活判定
                    if (t == null || t.graphic == null) continue;

                    // ID 超过颜色编码容量 (Levels^3=729): 无法再分配唯一颜色,
                    // 超出部分的文本将被判为不可见
                    if (id > TextIdCodec.Capacity)
                    {
                        Debug.LogWarning($"[LQATool][UIDumpService] 文本数超过 ID 容量 {TextIdCodec.Capacity}, 超出部分无法分配 ID, 将被判为不可见");
                        break;
                    }

                    // 读取 CanvasRenderer 当前 alpha (它决定文本最终呈现的可见度)
                    var cr = t.canvasRenderer;
                    float crAlpha = cr != null ? cr.GetAlpha() : 1f;

                    // 近乎透明 → 玩家看不到 → 跳过, 既不染色也不占用 ID
                    if (crAlpha < InvisibleAlphaThreshold)
                        continue;

                    // 染色前先完整备份现场
                    textBackups.Add(new TextIdBackup
                    {
                        text = t,
                        originalColor = t.color,
                        originalText = t.text,
                        originalCrAlpha = crAlpha
                    });

                    // 将 ID 编码为唯一颜色并染到文本上 (这是 "染色定位" 的核心一步)
                    Color32 idColor = TextIdCodec.Encode(id);
                    t.color = idColor;

                    // 若文本支持富文本, 去掉内嵌的 <color> 标签,
                    // 否则富文本自带的颜色会覆盖掉我们染上的 ID 颜色, 导致解码失败
                    if (t.supportRichText)
                        t.text = StripColorTags(t.text);
                    // 强制把 CanvasRenderer alpha 拉满, 保证 ID 颜色以最纯净的形态被渲染出来
                    if (cr != null) cr.SetAlpha(1f);

                    // 向上遍历父链, 把路径上所有 CanvasGroup 的 alpha 也临时拉满,
                    // 防止某个祖先节点的半透明把文本 "调暗", 干扰 ID 颜色的准确读取
                    // 用字典去重, 保证每个 CanvasGroup 只备份一次原始 alpha
                    Transform cur = t.transform;
                    while (cur != null)
                    {
                        var cg = cur.GetComponent<CanvasGroup>();
                        if (cg != null && !canvasGroupBackups.ContainsKey(cg))
                        {
                            canvasGroupBackups[cg] = cg.alpha;
                            cg.alpha = 1f;
                        }
                        cur = cur.parent;
                    }

                    // 记录本文本对应的 ID, 并递增编号
                    textToId[t.transform] = id;
                    id++;
                }

                // 没有任何文本被染色 → 无需渲染, 直接返回
                if (textToId.Count == 0) return null;

                // 强制刷新所有 Canvas, 让上面对颜色/文字/alpha 的修改立即生效
                Canvas.ForceUpdateCanvases();

                // 配置相机: 渲染全部图层 (layerMask=-1), 保留各相机原始 cullingMask
                var camStates = SetupCamerasForLayerMask(cameras, rt, -1, preserveCullingMask: true);
                // 把 Overlay 模式的 Canvas 临时改为 Camera 模式 (Overlay 无法渲染进 RT), 并排除工具自身 Canvas
                var overlayStates = SetupOverlayCanvases(topCamera, toolCanvas);
                // 按相机层级把整屏渲染到 RT 上
                RenderCamerasToRT(cameras, rt);

                // 从 RT 读回逐像素颜色, 即常规版文本 ID 图
                Color32[] idMap = ReadRtToColor32(rt, width, height);

                // 调试开关打开时, 把 ID 图另存为 PNG 便于人工核对
                if (LQAUILayerConfig.EmitTextIdMapDebug)
                {
                    SaveTextureFromRT(rt, width, height,
                        System.IO.Path.Combine(dumpDir, "ScreenShot_TextId.png"),
                        TextureFormat.RGBA32);
                }

                // 再生成一张 "纯净版" ID 图: 隐藏所有非文本图形, 消除遮挡影响 (详见方法内注释)
                pureIdMap = CapturePureTextIdMap(cameras, rt, width, height, textBackups, dumpDir);

                // 还原相机与 Overlay Canvas 状态 (文本/CanvasGroup 的还原在 finally 中统一处理)
                RestoreCameras(camStates);
                RestoreOverlayCanvases(overlayStates);

                return idMap;
            }
            finally
            {
                // 无论成功、异常还是提前 return, 都必须还原被篡改的现场:
                // 1) 还原每个被染色文本的颜色 / 内容 / CanvasRenderer alpha
                foreach (var b in textBackups)
                {
                    if (b.text == null || b.text.graphic == null) continue;
                    b.text.color = b.originalColor;
                    b.text.text = b.originalText;
                    var cr = b.text.canvasRenderer;
                    if (cr != null) cr.SetAlpha(b.originalCrAlpha);
                }
                // 2) 还原所有被临时拉满 alpha 的 CanvasGroup
                foreach (var kvp in canvasGroupBackups)
                {
                    if (kvp.Key != null) kvp.Key.alpha = kvp.Value;
                }
                // 3) 再次刷新 Canvas, 让还原后的状态立即回到屏幕
                Canvas.ForceUpdateCanvases();
            }
        }

        /// <summary>
        /// 匹配富文本中会改变字形颜色的标签 (成对/单个): <color> / </color> 与 TMP 的 <gradient> / </gradient>
        /// 使用 Compiled 提升多次调用性能, IgnoreCase 兼容大小写写法
        /// </summary>
        private static readonly Regex _colorTagRegex =
            new Regex("</?(color|gradient)[^>]*>", RegexOptions.IgnoreCase | RegexOptions.Compiled);

        /// <summary>
        /// 剥离字符串中会影响颜色的富文本标签 (<color> / <gradient>), 只保留纯文字
        /// 用于染色前清洗文本, 避免内嵌颜色覆盖我们染上的 ID 颜色
        /// </summary>
        private static string StripColorTags(string s)
        {
            if (string.IsNullOrEmpty(s)) return s;
            return _colorTagRegex.Replace(s, string.Empty);
        }

        /// <summary>
        /// 生成 "纯净版" 文本 ID 图
        /// 做法: 把场景中所有 "非染色文本" 的图形 (Graphic) 临时隐藏 (alpha=0),
        /// 只留下被染色的文本再渲染一次, 这样 ID 颜色不会被前景图片/背景等遮挡,
        /// 得到的像素更干净, 便于精确反解每个文本的可见区域
        /// (注意: Mask 组件不隐藏, 否则会破坏原有的裁剪关系)
        /// </summary>
        /// <param name="cameras">场景所有相机 (已按 depth 升序排序)</param>
        /// <param name="rt">离屏渲染用的 RenderTexture</param>
        /// <param name="width">读取宽度 (像素)</param>
        /// <param name="height">读取高度 (像素)</param>
        /// <param name="textBackups">已染色文本的备份列表 (据此识别哪些是 "染色文本", 不应被隐藏)</param>
        /// <param name="dumpDir">调试图输出目录</param>
        /// <returns>纯净版 ID 图的逐像素颜色数组 (RGBA32)</returns>
        private Color32[] CapturePureTextIdMap(
            Camera[] cameras, RenderTexture rt, int width, int height,
            List<TextIdBackup> textBackups, string dumpDir)
        {
            // 收集所有 "已染色文本" 的 CanvasRenderer, 作为渲染时需保留的白名单
            var dyed = new HashSet<CanvasRenderer>();
            var rendererBuf = new List<CanvasRenderer>();
            foreach (var b in textBackups)
            {
                if (b.text == null || b.text.graphic == null) continue;

                // 收集该文本的所有渲染器 (TMP 含子 SubMesh), 全部加入 "保留" 白名单
                // (否则 fallback 字体的子网格会被当作非文本图形隐藏, 纯净 ID 图上该文本缺字)
                b.text.CollectRenderers(rendererBuf);
                foreach (var cr in rendererBuf)
                    if (cr != null) dyed.Add(cr);
            }

            // 记录被临时隐藏的图形 (CanvasRenderer → 原始 alpha), 用于 finally 还原
            var hidden = new List<KeyValuePair<CanvasRenderer, float>>();
            // 遍历场景中所有 UI 图形
            foreach (var g in UnityEngine.Object.FindObjectsOfType<Graphic>())
            {
                if (g == null) continue;
                var gcr = g.canvasRenderer;
                // 跳过无渲染器的, 以及属于染色文本白名单的 (这些要保留可见)
                if (gcr == null || dyed.Contains(gcr)) continue;
                // 跳过 Mask: 隐藏它会破坏裁剪逻辑, 反而影响文本的可见范围
                if (g.GetComponent<Mask>() != null) continue;
                // 备份原始 alpha 后置 0 (隐藏)
                hidden.Add(new KeyValuePair<CanvasRenderer, float>(gcr, gcr.GetAlpha()));
                gcr.SetAlpha(0f);
            }

            Color32[] pure;
            try
            {
                // 刷新并重新渲染 (此时画面上只剩染色文本), 读回像素
                Canvas.ForceUpdateCanvases();
                RenderCamerasToRT(cameras, rt);
                pure = ReadRtToColor32(rt, width, height);

                // 调试开关打开时另存纯净版 PNG
                if (LQAUILayerConfig.EmitTextIdMapDebug)
                {
                    SaveTextureFromRT(rt, width, height,
                        System.IO.Path.Combine(dumpDir, "ScreenShot_TextId_Pure.png"),
                        TextureFormat.RGBA32);
                }
            }
            finally
            {
                // 还原所有被隐藏图形的 alpha, 并刷新回屏幕
                foreach (var kvp in hidden)
                    if (kvp.Key != null) kvp.Key.SetAlpha(kvp.Value);
                Canvas.ForceUpdateCanvases();
            }
            return pure;
        }

        /// <summary>
        /// 从 RenderTexture 读回全部像素为 Color32 数组。
        /// 通过临时 Texture2D.ReadPixels 完成 GPU→CPU 的像素回读, 读取后立即销毁临时纹理
        /// </summary>
        /// <param name="rt">源 RenderTexture</param>
        /// <param name="width">读取宽度 (像素)</param>
        /// <param name="height">读取高度 (像素)</param>
        /// <returns>逐像素颜色数组 (RGBA32, 按行优先)</returns>
        private Color32[] ReadRtToColor32(RenderTexture rt, int width, int height)
        {
            // 保存当前激活的 RT, 读取完毕后还原, 避免影响后续渲染管线
            var prev = RenderTexture.active;
            RenderTexture.active = rt;

            // 创建临时纹理, 从当前激活的 RT 中读回像素
            var tmp = new Texture2D(width, height, TextureFormat.RGBA32, false);
            tmp.ReadPixels(new Rect(0, 0, width, height), 0, 0);
            tmp.Apply();
            Color32[] px = tmp.GetPixels32();

            // 释放临时纹理并还原激活的 RT
            UnityEngine.Object.Destroy(tmp);
            RenderTexture.active = prev;
            return px;
        }
    }
}