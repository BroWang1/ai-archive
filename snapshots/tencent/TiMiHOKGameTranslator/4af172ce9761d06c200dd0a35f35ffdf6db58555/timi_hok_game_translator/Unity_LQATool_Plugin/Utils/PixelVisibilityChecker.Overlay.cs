// ==========================================
// 文件: LQATool\Utils\PixelVisibilityChecker.Overlay.cs
// 模块: Utils (工具箱)
// ==========================================

using System.IO;
using UnityEngine;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 像素级文本可见性判定器 —— 可视化调试输出部分
    /// 在 Full 截图上按判定结果给每个文本的 AABB 描边, 输出 ScreenShot_VisDebug.png
    /// (SaveVisibilityOverlay 生成叠加图, DrawRectOutline 绘制矩形边框)
    /// </summary>
    public static partial class PixelVisibilityChecker
    {
        /// <summary>
        /// 生成可见性判定的可视化调试图: 在 Full 截图上按判定结果给每个文本 AABB 描边,
        /// 输出为 ScreenShot_VisDebug.png
        /// 颜色含义:
        ///   绿色 = 可见且差异明显
        ///   黄色 = 可见但差异像素很少 (临界/可疑)
        ///   红色 = 不可见: 有足迹但差异占比低 (被遮挡/未画出)
        ///   紫色 = 不可见: 足迹被其它文本覆盖 (与别的文字重叠)
        ///   青色 = 不可见: 足迹过弱 (小字号/抗锯齿边缘未达 alpha 阈值, 可下调 PureMaskAlphaThreshold)
        ///   灰色 = 不可见: 足迹为空 (被裁剪/未渲染/被非文本图形遮挡)
        /// </summary>
        /// <param name="dumpDir">截图目录 (读取 Full, 写出 VisDebug)</param>
        /// <param name="width">期望图像宽度 (与缓存构建时一致)</param>
        /// <param name="height">期望图像高度</param>
        public static void SaveVisibilityOverlay(string dumpDir, int width, int height)
        {
            // 可见但差异像素低于该数量时, 用红色高亮提示 "勉强可见/需人工复核"
            const int LowDiffHighlight = 35;

            string fullPath = Path.Combine(dumpDir, "ScreenShot_Full.png");
            if (!File.Exists(fullPath)) return;

            // 用 RGBA32 以便描边覆盖不透明色
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            try
            {
                tex.LoadImage(File.ReadAllBytes(fullPath));
                // 尺寸与缓存不一致则放弃 (AABB 坐标无法对齐)
                if (tex.width != width || tex.height != height) return;

                var px = tex.GetPixels32();

                Color32 green = new Color32(0, 220, 0, 255);  // 可见且差异明显
                Color32 yellow = new Color32(255, 235, 0, 255);  // 可见但差异很少 (临界/可疑)
                Color32 red = new Color32(255, 40, 40, 255);  // 不可见: 有足迹但差异占比低 (被遮挡/未画出)
                Color32 purple = new Color32(180, 60, 220, 255);  // 不可见: 足迹被其它文本覆盖
                Color32 cyan = new Color32(0, 200, 220, 255);  // 不可见: 足迹过弱 (小字号/抗锯齿未达 alpha 阈值)
                Color32 gray = new Color32(140, 140, 140, 255);  // 不可见: 足迹为空 (裁剪/未渲染/非文本遮挡)

                // 遍历所有调试快照, 按判定结果选色并描边
                // 不可见的三种 total==0 成因判据与 BuildCacheForScene 里的 reason 分流保持一致
                foreach (var d in _debug.Values)
                {
                    if (!d.aabbValid) continue;  // 没有有效包围盒无法画框
                    Color32 c;
                    if (d.verdict)
                        c = d.diffCount < LowDiffHighlight ? yellow : green;  // 可见: 临界黄 / 明显绿
                    else if (d.maskTotal > 0)
                        c = red;  // 有足迹但差异占比低 (被遮挡/未画出)
                    else if (d.coveredByOther > d.weakAlpha && d.coveredByOther > 0)
                        c = purple;  // 足迹被其它文本覆盖
                    else if (d.weakAlpha > 0)
                        c = cyan;  // 足迹过弱 (小字号/抗锯齿)
                    else
                        c = gray;  // 足迹为空
                    DrawRectOutline(px, width, height, d.aabb, c);
                }

                // 写回像素并编码为 PNG 落盘
                tex.SetPixels32(px);
                tex.Apply();
                File.WriteAllBytes(Path.Combine(dumpDir, "ScreenShot_VisDebug.png"), tex.EncodeToPNG());
            }
            finally
            {
                // 释放临时纹理内存
                Object.Destroy(tex);
            }
        }

        /// <summary>
        /// 在像素数组上绘制一个矩形的边框 (仅描边, 不填充)
        /// </summary>
        /// <param name="px">目标像素数组 (会被就地修改)</param>
        /// <param name="w">图像宽度</param>
        /// <param name="h">图像高度</param>
        /// <param name="r">矩形区域</param>
        /// <param name="c">描边颜色</param>
        private static void DrawRectOutline(Color32[] px, int w, int h, RectInt r, Color32 c)
        {
            // 计算并裁剪矩形四条边的端点到图像合法范围内
            int x0 = Mathf.Clamp(r.xMin, 0, w - 1), x1 = Mathf.Clamp(r.xMin + r.width - 1, 0, w - 1);
            int y0 = Mathf.Clamp(r.yMin, 0, h - 1), y1 = Mathf.Clamp(r.yMin + r.height - 1, 0, h - 1);
            if (x1 < x0 || y1 < y0) return;  // 裁剪后退化则不画

            // 画上下两条水平边
            for (int x = x0; x <= x1; x++) { px[y0 * w + x] = c; px[y1 * w + x] = c; }
            // 画左右两条垂直边
            for (int y = y0; y <= y1; y++) { px[y * w + x0] = c; px[y * w + x1] = c; }
        }
    }
}