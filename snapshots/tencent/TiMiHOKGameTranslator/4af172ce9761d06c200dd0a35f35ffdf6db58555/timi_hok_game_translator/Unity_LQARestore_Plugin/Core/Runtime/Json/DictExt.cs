// ==========================================
// 文件: LQARestore\Core\Runtime\Json\DictExt.cs
// 模块: Core.Json (核心层 JSON 数据读写)
// ==========================================

using System;
using System.Collections.Generic;

/// <summary>
/// LQARestore 核心层 JSON 数据读写命名空间
/// </summary>
namespace LQARestore.Core.Json
{
    /// <summary>
    /// Dictionary<string, object> 的取值扩展方法集
    /// 用途: JSON 反序列化后通常得到 Dictionary<string, object> 这种松散结构,
    ///       其值类型是 object (可能是 string / long / double / bool 等),
    ///       直接强转易出错, 本类提供一组带默认值、带类型转换、带判空保护的安全取值方法,
    ///       避免调用处到处写重复的判空与 try-catch
    /// 特点: 全部为无状态纯函数, 故声明为 static 扩展方法;
    ///       任何异常/缺键/空值场景都会回退到默认值, 不抛出异常
    /// </summary>
    public static class DictExt
    {
        /// <summary>
        /// 按键取出引用类型的值, 并以指定类型 T 返回
        /// </summary>
        /// <typeparam name="T">期望的引用类型 (约束为 class)</typeparam>
        /// <param name="dict">源字典, 允许为 null</param>
        /// <param name="key">要读取的键</param>
        /// <returns>
        /// 命中且能转为 T 时返回该对象;
        /// 字典为 null、键不存在、值为 null 或类型不匹配时返回 null
        /// </returns>
        public static T Get<T>(this Dictionary<string, object> dict, string key) where T : class
        {
            // 判空保护: 字典为空 / 键不存在 / 值为 null, 任一成立即返回 null
            if (dict == null || !dict.TryGetValue(key, out var v) || v == null) return null;
            // 使用 as 做安全转换, 类型不匹配时返回 null 而非抛异常
            return v as T;
        }

        /// <summary>
        /// 按键取出字符串值
        /// </summary>
        /// <param name="dict">源字典, 允许为 null</param>
        /// <param name="key">要读取的键</param>
        /// <param name="def">取不到时的默认值, 默认空字符串</param>
        /// <returns>
        /// 值本身是字符串则直接返回;
        /// 值为其它类型则调用其 ToString() 转换后返回;
        /// 缺键或值为 null 时返回 def
        /// </returns>
        public static string GetInnerString(this Dictionary<string, object> dict, string key, string def = "")
        {
            // 判空保护, 命中失败直接回退默认值
            if (dict == null || !dict.TryGetValue(key, out var v) || v == null) return def;
            // 已经是字符串则免去 ToString 开销直接返回
            if (v is string s) return s;
            // 其它类型 (数字/布尔等) 统一转成字符串
            return v.ToString();
        }

        /// <summary>
        /// 按键取出 int 值
        /// </summary>
        /// <param name="dict">源字典, 允许为 null</param>
        /// <param name="key">要读取的键</param>
        /// <param name="def">取不到或转换失败时的默认值, 默认 0</param>
        /// <returns>成功转换的 int, 否则返回 def</returns>
        public static int GetInnerInt(this Dictionary<string, object> dict, string key, int def = 0)
        {
            // 判空保护, 命中失败直接回退默认值
            if (dict == null || !dict.TryGetValue(key, out var v) || v == null) return def;
            // JSON 数字反序列化后类型不确定 (可能是 long/double/string),
            // 用 Convert 统一转换; 指定 InvariantCulture 避免不同区域设置下的解析差异;
            // 转换失败 (如非数字字符串) 时吞掉异常并回退默认值
            try { return Convert.ToInt32(v, System.Globalization.CultureInfo.InvariantCulture); } catch { return def; }
        }

        /// <summary>
        /// 按键取出 float 值
        /// </summary>
        /// <param name="dict">源字典, 允许为 null</param>
        /// <param name="key">要读取的键</param>
        /// <param name="def">取不到或转换失败时的默认值, 默认 0f</param>
        /// <returns>成功转换的 float, 否则返回 def</returns>
        public static float GetInnerFloat(this Dictionary<string, object> dict, string key, float def = 0f)
        {
            // 判空保护, 命中失败直接回退默认值
            if (dict == null || !dict.TryGetValue(key, out var v) || v == null) return def;
            // 同 GetInnerInt: 统一用 Convert + InvariantCulture 转换,
            // 避免小数点在某些区域被解析为逗号等问题; 失败则回退默认值
            try { return Convert.ToSingle(v, System.Globalization.CultureInfo.InvariantCulture); } catch { return def; }
        }

        /// <summary>
        /// 按键取出 bool 值
        /// </summary>
        /// <param name="dict">源字典, 允许为 null</param>
        /// <param name="key">要读取的键</param>
        /// <param name="def">取不到或解析失败时的默认值, 默认 false</param>
        /// <returns>
        /// 值本身是 bool 则直接返回;
        /// 否则尝试按字符串解析 ("true"/"false");
        /// 解析失败或缺键时返回 def
        /// </returns>
        public static bool GetInnerBool(this Dictionary<string, object> dict, string key, bool def = false)
        {
            // 判空保护, 命中失败直接回退默认值
            if (dict == null || !dict.TryGetValue(key, out var v) || v == null) return def;
            // 已经是布尔值则直接返回
            if (v is bool b) return b;
            // 其它类型转成字符串后尝试解析, 解析成功用结果, 失败回退默认值
            return bool.TryParse(v.ToString(), out var r) ? r : def;
        }
    }
}