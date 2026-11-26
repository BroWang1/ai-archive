// ==========================================
// 文件: LQATool\Utils\PixelVisibilityChecker.Build.cs
// 模块: Utils (工具箱)
// ==========================================

using System.Collections.Generic;
using System.IO;
using UnityEngine;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 像素级文本可见性判定器 —— 缓存构建与核心判定部分
    /// 读取 Full / NoText 两张截图做像素差分, 结合纯色 ID 图掩码逐个判定每个 Text 是否可见,
    /// 并将结果与调试快照写入缓存 (BuildCacheForScene)
    /// 含掩码差异占比判定 (IsVisibleByPureMask) 与屏幕包围盒计算 (TryComputeScreenAABB)
    /// </summary>
    public static partial class PixelVisibilityChecker
    {
        /// <summary>
        /// 针对整个场景一次性构建所有文本的可见性缓存
        /// 读取 Full / NoText 两张截图做像素差分, 结合纯色 ID 图掩码逐个判定每个 Text
        /// </summary>
        /// <param name="dumpDir">存放截图与 ID 图的目录</param>
        /// <param name="texts">待判定的所有文本 (旧版 Text 与 TMP, 统一包装为 TextLike)</param>
        /// <param name="textIdMap">文本 ID 图 (用于判断掩码是否可用, 本方法主要以尺寸匹配作校验)</param>
        /// <param name="pureIdMap">纯色 ID 图: 每个文本足迹被涂成其专属颜色, 是真正参与判定的掩码</param>
        /// <param name="textToId">Transform -> 文本 ID 的映射</param>
        /// <param name="colorDiffThreshold">单像素 RGB 通道差之和超过该值, 才算 "差异显著"</param>
        /// <param name="maskVisibleRatio">差异像素占足迹像素的比例超过该阈值, 才判为可见</param>
        /// <param name="pureMaskAlphaThreshold">纯色掩码像素被计入足迹所需的最小 alpha (0~255)</param>
        public static void BuildCacheForScene(
            string dumpDir,
            IReadOnlyList<TextLike> texts,
            Color32[] textIdMap,
            Color32[] pureIdMap,
            Dictionary<Transform, int> textToId,
            int colorDiffThreshold,
            float maskVisibleRatio,
            int pureMaskAlphaThreshold)
        {
            // 重新构建前先清空旧缓存, 保证结果与本次输入一致
            _cache.Clear();
            _debug.Clear();

            // 两张关键截图的完整路径
            string fullPath = Path.Combine(dumpDir, "ScreenShot_Full.png");
            string noTextPath = Path.Combine(dumpDir, "ScreenShot_NoText.png");

            // 缺少任一截图则无法做差分, 直接跳过 (所有文本保持无缓存状态)
            if (!File.Exists(fullPath) || !File.Exists(noTextPath))
            {
                Debug.LogWarning("[LQATool][PixelVisibilityChecker] 缺少 ScreenShot_Full.png 或 ScreenShot_NoText.png, 像素差分判定跳过");
                return;
            }

            // 临时纹理: 尺寸随后由 LoadImage 覆盖, 这里 2x2 只是占位
            // 用 RGB24 即可, 差分只关心颜色不关心 alpha
            Texture2D texFull = new Texture2D(2, 2, TextureFormat.RGB24, false);
            Texture2D texNoText = new Texture2D(2, 2, TextureFormat.RGB24, false);

            try
            {
                // 从磁盘字节流解码 PNG 到纹理
                texFull.LoadImage(File.ReadAllBytes(fullPath));
                texNoText.LoadImage(File.ReadAllBytes(noTextPath));

                // 两张图必须同尺寸才能逐像素一一对应, 否则差分无意义
                if (texFull.width != texNoText.width || texFull.height != texNoText.height)
                {
                    Debug.LogWarning($"[LQATool][PixelVisibilityChecker] Full/NoText 尺寸不一致, 跳过差分");
                    return;
                }

                int width = texFull.width;
                int height = texFull.height;

                // 一次性取出全部像素, 后续按行列索引访问, 避免逐像素 API 调用开销
                Color32[] pxFull = texFull.GetPixels32();
                Color32[] pxNoText = texNoText.GetPixels32();

                // 是否具备掩码判定条件: ID 相关数据齐全, 且 ID 图尺寸与截图一致
                // 任一不满足, 则无法确定文本足迹, 本次所有文本将被判为不可见
                bool useMask = textIdMap != null
                                && pureIdMap != null
                                && textToId != null
                                && textIdMap.Length == width * height
                                && pureIdMap.Length == width * height;

                if (!useMask)
                    Debug.LogWarning("[LQATool][PixelVisibilityChecker] 文本 ID 图缺失或与截图尺寸不一致, 本次无法做掩码判定, 所有文本将判为不可见");

                int evaluated = 0;  // 实际参与评估的文本计数
                int markedInvisible = 0;  // 被判为不可见的文本计数

                foreach (var textComp in texts)
                {
                    // 跳过已销毁/空引用 (TextLike 普通类判空 + 底层 graphic 存活判定)
                    if (textComp == null || textComp.graphic == null) continue;
                    // 只处理带 RectTransform 的 UI 文本 (需要计算屏幕包围盒)
                    var rt = textComp.transform as RectTransform;
                    if (rt == null) continue;

                    evaluated++;

                    // 预填调试快照的公共字段, id 先置 -1 表示尚未取到
                    var dbg = new VisibilityDebug { useMask = useMask, ratioThreshold = maskVisibleRatio, id = -1 };

                    // 无掩码条件, 或该文本在 ID 映射中不存在 => 无法判定足迹, 直接记为不可见
                    if (!useMask || !textToId.TryGetValue(textComp.transform, out int id))
                    {
                        dbg.verdict = false;
                        dbg.reason  = !useMask ? "ID图不可用" : "没有ID(idMap阶段被跳过:自身alpha<0.04或超ID容量)";
                        _cache[textComp.transform] = false;
                        _debug[textComp.transform] = dbg;
                        markedInvisible++;
                        continue;
                    }
                    dbg.hasId = true; dbg.id = id;

                    // 确定用于世界坐标->屏幕坐标转换的相机:
                    // ScreenSpaceOverlay 模式不依赖相机 (传 null), 其它模式使用画布的 worldCamera
                    Canvas c = textComp.canvas;
                    Camera cam = (c != null && c.renderMode != RenderMode.ScreenSpaceOverlay) ? c.worldCamera : null;

                    // 计算该文本在屏幕像素坐标系下的包围盒, 失败或完全出屏则记为不可见
                    if (!TryComputeScreenAABB(rt, cam, width, height, out RectInt aabb))
                    {
                        dbg.verdict = false;
                        dbg.reason  = "AABB计算失败/在屏幕外";
                        _cache[textComp.transform] = false;
                        _debug[textComp.transform] = dbg;
                        markedInvisible++;
                        continue;
                    }
                    dbg.aabbValid = true; dbg.aabb = aabb;

                    // 核心判定: 在 AABB 内, 用纯色 ID 掩码筛出该文本足迹像素, 统计 Full 与 NoText 的差异占比
                    bool isVis = IsVisibleByPureMask(pxFull, pxNoText, pureIdMap, width, aabb, id,
                        colorDiffThreshold, maskVisibleRatio, pureMaskAlphaThreshold,
                        out int total, out int diff, out int weakAlpha, out int coveredByOther);

                    // 记录判定中间量与结论
                    dbg.maskTotal = total;
                    dbg.diffCount = diff;
                    dbg.weakAlpha = weakAlpha;
                    dbg.coveredByOther = coveredByOther;
                    dbg.ratio = total > 0 ? (float)diff / total : 0f;
                    dbg.verdict = isVis;
                    // 按成因分流原因文案, 便于区分 "被真遮挡" / "被 alpha 阈值筛空" / "真的空"
                    if (isVis)
                        dbg.reason = "Visible";
                    else if (total > 0)
                        dbg.reason = "差异占比低于阈值(被遮挡/未画出)";
                    else if (coveredByOther > weakAlpha && coveredByOther > 0)
                        dbg.reason = "足迹被其它文本覆盖(与别的文字重叠)";
                    else if (weakAlpha > 0)
                        dbg.reason = "足迹过弱(小字号/抗锯齿边缘未达alpha阈值,可下调PureMaskAlphaThreshold)";
                    else
                        dbg.reason = "足迹为空(区域内无本文本像素:被裁剪/未渲染/被非文本图形遮挡)";

                    _cache[textComp.transform] = isVis;
                    _debug[textComp.transform] = dbg;
                    if (!isVis) markedInvisible++;
                }

                Debug.Log($"[LQATool][PixelVisibilityChecker] 判定完成: 评估 {evaluated} 个 Text, 不可见 {markedInvisible} 个");
            }
            finally
            {
                // 无论成功与否都销毁临时纹理, 释放非托管内存 (Texture2D 不受 GC 自动回收)
                Object.Destroy(texFull);
                Object.Destroy(texNoText);
            }
        }

        /// <summary>
        /// 在给定 AABB 内, 依据纯色 ID 掩码筛出属于指定 id 的足迹像素,
        /// 比较 Full 与 NoText 的颜色差异, 判定该文本是否可见
        /// </summary>
        /// <param name="pxFull">完整画面像素</param>
        /// <param name="pxNoText">去文本画面像素</param>
        /// <param name="pureIdMap">纯色 ID 掩码像素</param>
        /// <param name="width">图像宽度 (用于行列->一维索引换算)</param>
        /// <param name="aabb">该文本的屏幕包围盒 (缩小遍历范围)</param>
        /// <param name="id">目标文本 ID</param>
        /// <param name="colorDiffThreshold">单像素 RGB 通道差之和阈值</param>
        /// <param name="maskVisibleRatio">差异占比阈值</param>
        /// <param name="pureMaskAlphaThreshold">纯色掩码像素被计入足迹所需的最小 alpha (0~255)</param>
        /// <param name="total">输出: 足迹像素总数</param>
        /// <param name="diff">输出: 差异显著的像素数</param>
        /// <param name="weakAlpha">输出: 半透明但未达 alpha 门槛的像素数 (小字号/抗锯齿边缘)</param>
        /// <param name="coveredByOther">输出: alpha 达标但解码为 "别的有效 ID" 的像素数 (被其它文本覆盖)</param>
        /// <returns>差异占比大于阈值则返回 true (可见)</returns>
        private static bool IsVisibleByPureMask(
            Color32[] pxFull, Color32[] pxNoText, Color32[] pureIdMap,
            int width, RectInt aabb, int id, int colorDiffThreshold, float maskVisibleRatio,
            int pureMaskAlphaThreshold,
            out int total, out int diff, out int weakAlpha, out int coveredByOther)
        {
            total = 0;
            diff = 0;
            weakAlpha = 0;
            coveredByOther = 0;

            // AABB 的右边界与上边界 (开区间上限)
            int xEnd = aabb.xMin + aabb.width;
            int yEnd = aabb.yMin + aabb.height;

            // 仅遍历包围盒内的像素, 避免全屏扫描
            for (int y = aabb.yMin; y < yEnd; y++)
            {
                int rowBase = y * width;  // 当前行首在一维数组中的偏移
                for (int x = aabb.xMin; x < xEnd; x++)
                {
                    int idx = rowBase + x;

                    // 掩码判定该像素是否属于本文本足迹
                    Color32 pm = pureIdMap[idx];
                    if (pm.a < pureMaskAlphaThreshold)
                    {
                        // 非全透明却没过 alpha 门槛: 记为 "弱足迹" (常见于小字号抗锯齿边缘)
                        if (pm.a > 0) weakAlpha++;
                        continue;
                    }
                    int decoded = TextIdCodec.Decode(pm.r, pm.g, pm.b);
                    if (decoded != id)
                    {
                        // alpha 达标但解码为别的有效 ID: 该处被其它文本占据 (真遮挡/覆盖)
                        if (decoded != 0) coveredByOther++;
                        continue;  // 解码出的 ID 不匹配: 属于别的文本
                    }

                    total++;

                    // 计算 Full 与 NoText 在该像素上的颜色差异 (RGB 三通道差绝对值之和)
                    Color32 a = pxFull[idx];
                    Color32 b = pxNoText[idx];
                    int d = Mathf.Abs(a.r - b.r) + Mathf.Abs(a.g - b.g) + Mathf.Abs(a.b - b.b);
                    if (d > colorDiffThreshold) diff++;  // 差异显著 => 该处文本确实被画了出来
                }
            }

            // 足迹为空: 该文本足迹被其它文本覆盖或被裁剪, 无法判定为可见
            if (total == 0) return false;

            // 差异像素占比超过阈值即认为可见
            float ratio = (float)diff / total;
            return ratio > maskVisibleRatio;
        }

        /// <summary>
        /// 计算 RectTransform 在屏幕像素坐标系下的轴对齐包围盒 (AABB), 并裁剪到屏幕范围内
        /// </summary>
        /// <param name="rt">目标 UI 元素的 RectTransform</param>
        /// <param name="cam">世界->屏幕转换所用相机 (Overlay 模式为 null)</param>
        /// <param name="screenW">屏幕/图像宽度</param>
        /// <param name="screenH">屏幕/图像高度</param>
        /// <param name="aabb">输出: 裁剪后的屏幕包围盒</param>
        /// <returns>包围盒在屏幕内且有效则返回 true; 完全出屏或退化则返回 false</returns>
        private static bool TryComputeScreenAABB(RectTransform rt, Camera cam, int screenW, int screenH, out RectInt aabb)
        {
            aabb = default;

            // 取 RectTransform 的 4 个世界坐标角点 (顺序: 左下->左上->右上->右下)
            Vector3[] worldCorners = new Vector3[4];
            rt.GetWorldCorners(worldCorners);

            // 逐角点投影到屏幕, 求出四角在屏幕上的最小/最大 X、Y, 得到轴对齐包围盒
            float minX = float.MaxValue, minY = float.MaxValue;
            float maxX = float.MinValue, maxY = float.MinValue;

            for (int i = 0; i < 4; i++)
            {
                Vector2 sp = RectTransformUtility.WorldToScreenPoint(cam, worldCorners[i]);
                if (sp.x < minX) minX = sp.x;
                if (sp.y < minY) minY = sp.y;
                if (sp.x > maxX) maxX = sp.x;
                if (sp.y > maxY) maxY = sp.y;
            }

            // 取整并裁剪到屏幕合法范围: 左下用 Floor 向外扩, 右上用 Ceil 向外扩, 保证足迹不被漏算
            int x0 = Mathf.Max(0, Mathf.FloorToInt(minX));
            int y0 = Mathf.Max(0, Mathf.FloorToInt(minY));
            int x1 = Mathf.Min(screenW - 1, Mathf.CeilToInt(maxX));
            int y1 = Mathf.Min(screenH - 1, Mathf.CeilToInt(maxY));

            // 宽高非正 => 完全出屏或退化, 视为无效
            int w = x1 - x0 + 1;
            int h = y1 - y0 + 1;
            if (w <= 0 || h <= 0) return false;

            aabb = new RectInt(x0, y0, w, h);
            return true;
        }
    }
}