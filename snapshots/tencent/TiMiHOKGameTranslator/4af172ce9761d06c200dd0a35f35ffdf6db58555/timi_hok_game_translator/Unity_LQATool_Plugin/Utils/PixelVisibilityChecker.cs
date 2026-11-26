// ==========================================
// 文件: LQATool\Utils\PixelVisibilityChecker.cs
// 模块: Utils (工具箱)
// ==========================================

using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 像素级文本可见性判定器 (静态工具类)
    /// 通过对整个场景一次性构建缓存 (BuildCacheForScene), 之后可用
    /// TryGetCached / TryGetDebug 快速查询每个文本的判定结果与调试信息
    ///
    /// 本部分: 判定结果与调试数据的存储及查询接口
    /// (VisibilityDebug 调试快照结构、缓存字典, 以及 TryGetCached / TryGetDebug / ClearCache)
    /// </summary>
    public static partial class PixelVisibilityChecker
    {
        /// <summary>
        /// 单个文本的可见性判定调试快照
        /// 记录判定过程中的关键中间量, 便于问题定位与可视化叠加 (SaveVisibilityOverlay)
        /// </summary>
        public struct VisibilityDebug
        {
            public bool useMask;  // 本次是否具备做掩码判定的条件 (ID 图齐全且尺寸匹配)
            public bool hasId;  // 该文本是否成功取到了 ID
            public int id;  // 该文本的 ID (无则为 -1)
            public bool aabbValid;  // 屏幕包围盒是否计算成功 (未失败/未完全出屏)
            public RectInt aabb;  // 该文本在屏幕像素坐标下的轴对齐包围盒
            public int maskTotal;  // 足迹像素总数 (AABB 内属于该 ID 的像素数)
            public int diffCount;  // 足迹内 Full 与 NoText 颜色差异显著的像素数
            public int weakAlpha;  // 非全透明但未达 alpha 门槛的像素数 (小字号/抗锯齿边缘)
            public int coveredByOther;  // alpha 达标但解码为别的有效 ID 的像素数 (被其它文本覆盖)
            public float ratio;  // 差异占比 = diffCount / maskTotal
            public float ratioThreshold;  // 判定为可见所需的差异占比阈值
            public bool verdict;  // 最终判定: true=可见
            public string reason;  // 判定原因的可读文字说明 (用于日志/调试)
        }

        // 判定结果缓存: Text 所在 Transform -> 是否可见
        // 由 BuildCacheForScene 一次性填充, 供后续逐个查询, 避免重复计算
        private static readonly Dictionary<Transform, bool> _cache = new Dictionary<Transform, bool>();

        // 调试信息缓存: Text 所在 Transform -> 该文本的判定调试快照
        // 与 _cache 同步填充, 生命周期一致
        private static readonly Dictionary<Transform, VisibilityDebug> _debug = new Dictionary<Transform, VisibilityDebug>();

        /// <summary>
        /// 尝试取出指定 Transform 的缓存判定结果 (是否可见)
        /// </summary>
        /// <param name="t">目标文本所在的 Transform</param>
        /// <param name="isVisible">输出: 是否可见</param>
        /// <returns>缓存中存在则返回 true</returns>
        public static bool TryGetCached(Transform t, out bool isVisible)
        {
            return _cache.TryGetValue(t, out isVisible);
        }

        /// <summary>
        /// 尝试取出指定 Transform 的判定调试快照
        /// </summary>
        /// <param name="t">目标文本所在的 Transform</param>
        /// <param name="dbg">输出: 对应的调试快照</param>
        /// <returns>缓存中存在则返回 true</returns>
        public static bool TryGetDebug(Transform t, out VisibilityDebug dbg)
        {
            return _debug.TryGetValue(t, out dbg);
        }

        /// <summary>
        /// 清空判定结果与调试信息缓存
        /// 在重新构建缓存前, 或场景切换后调用, 避免残留旧数据
        /// </summary>
        public static void ClearCache()
        {
            _cache.Clear();
            _debug.Clear();
        }
    }
}