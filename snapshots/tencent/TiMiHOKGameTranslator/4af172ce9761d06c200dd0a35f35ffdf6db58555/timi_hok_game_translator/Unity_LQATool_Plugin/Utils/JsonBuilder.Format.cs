// ==========================================
// 文件: LQATool\Utils\JsonBuilder.Format.cs
// 模块: Utils (工具箱)
// ==========================================

using System.Text;
using System.Globalization;
using UnityEngine;
using LQATool.Models;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 本分部 (partial) 文件负责 JsonBuilder 的底层格式化原子方法:
    /// 把 Unity 的基础值类型 (Vector2 / Vector3 / Rect / Color) 以及原始字符串
    /// 转换为可直接嵌入 JSON 的合法片段
    /// 上层的整树序列化逻辑 (Serialize / SerializeNode) 定义在同类的另一个分部文件
    /// JsonBuilder.cs 中, 会调用这里的方法拼装最终 JSON
    /// 说明: 所有浮点数一律使用 CultureInfo.InvariantCulture, 强制小数点为 "."
    /// 避免在非英语系统上被渲染成 "," 而破坏 JSON 语法
    /// </summary>
    public static partial class JsonBuilder
    {
        /// <summary>
        /// 将 Vector2 格式化为 JSON 对象片段 {"x": .., "y": ..}
        /// </summary>
        /// <param name="v">待格式化的二维向量</param>
        /// <returns>形如 {"x": 1.5, "y": 2} 的 JSON 片段字符串</returns>
        public static string FormatVector2(Vector2 v) => $"{{\"x\": {v.x.ToString(CultureInfo.InvariantCulture)}, \"y\": {v.y.ToString(CultureInfo.InvariantCulture)}}}";

        /// <summary>
        /// 将 Vector3 格式化为 JSON 对象片段 {"x": .., "y": .., "z": ..}
        /// </summary>
        /// <param name="v">待格式化的三维向量</param>
        /// <returns>形如 {"x": 1, "y": 2, "z": 3} 的 JSON 片段字符串</returns>
        public static string FormatVector3(Vector3 v) => $"{{\"x\": {v.x.ToString(CultureInfo.InvariantCulture)}, \"y\": {v.y.ToString(CultureInfo.InvariantCulture)}, \"z\": {v.z.ToString(CultureInfo.InvariantCulture)}}}";

        /// <summary>
        /// 对字符串做 JSON 转义, 使其能安全地放入 JSON 字符串字面量中
        /// </summary>
        /// <param name="str">原始字符串 (可为 null 或空)</param>
        /// <returns>转义后的字符串, 输入为 null/空 时返回空字符串</returns>
        public static string EscapeJson(string str)
        {
            // 空值保护: null 或空串统一返回 "", 避免后续 Replace 抛异常
            if (string.IsNullOrEmpty(str)) return "";

            // 转义顺序至关重要: 反斜杠必须最先替换
            // 否则后续替换新引入的 "\" 会被重复转义, 导致结果错误
            return str.Replace("\\", "\\\\")  // 反斜杠 \  -> \\
                      .Replace("\"", "\\\"")  // 双引号 "  -> \"
                      .Replace("\n", "\\n")  // 换行符    -> \n
                      .Replace("\r", "\\r")  // 回车符    -> \r
                      .Replace("\t", "\\t");  // 制表符    -> \t
        }

        /// <summary>
        /// 将 Rect 格式化为 JSON 对象片段 {"x": .., "y": .., "width": .., "height": ..}
        /// 各分量保留 3 位小数 (F3)
        /// </summary>
        /// <param name="r">待格式化的矩形</param>
        /// <returns>包含 x/y/width/height 四个字段的 JSON 片段字符串</returns>
        private static string FormatRect(Rect r)
        {
            return "{\"x\": " + r.x.ToString("F3", CultureInfo.InvariantCulture) + ", \"y\": " + r.y.ToString("F3", CultureInfo.InvariantCulture) + ", \"width\": " + r.width.ToString("F3", CultureInfo.InvariantCulture) + ", \"height\": " + r.height.ToString("F3", CultureInfo.InvariantCulture) + "}";
        }

        /// <summary>
        /// 将 Color 格式化为 JSON 对象片段 {"r": .., "g": .., "b": .., "a": ..}
        /// 各通道保留 3 位小数 (F3), 取值范围通常为 0~1
        /// </summary>
        /// <param name="c">待格式化的颜色</param>
        /// <returns>包含 r/g/b/a 四个通道的 JSON 片段字符串</returns>
        public static string FormatColor(Color c)
        {
            return "{\"r\": " + c.r.ToString("F3", CultureInfo.InvariantCulture) + ", \"g\": " + c.g.ToString("F3", CultureInfo.InvariantCulture) + ", \"b\": " + c.b.ToString("F3", CultureInfo.InvariantCulture) + ", \"a\": " + c.a.ToString("F3", CultureInfo.InvariantCulture) + "}";
        }
    }
}