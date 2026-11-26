// ==========================================
// 文件: LQARestore\Core\Runtime\Json\MiniJson.cs
// 模块: Core.Json (核心层 JSON 数据读写)
// ==========================================

using System;
using System.Collections.Generic;
using System.Text;

/// <summary>
/// LQARestore 核心层 JSON 数据读写命名空间
/// </summary>
namespace LQARestore.Core.Json
{
    /// <summary>
    /// 极简 JSON 解析器 (只解析, 不负责序列化)
    /// 用途: 在不引入第三方 JSON 库的前提下, 把 JSON 文本解析成通用的 C# 对象树,
    ///       供上层 (配合 DictExt 等) 读取
    /// 解析结果的类型映射约定:
    ///   JSON object -> Dictionary<string, object>
    ///   JSON array -> List<object>
    ///   JSON string -> string
    ///   JSON number -> double (统一用 double, 不区分整数/浮点)
    ///   JSON true/false -> bool
    ///   JSON null -> null
    /// 实现方式: 采用单指针 (ref int i) 递归下降解析, i 表示当前扫描位置,
    ///           各 Parse 方法消费掉自己对应的片段后将 i 推进到片段末尾之后
    /// 注意: 这是一个 "宽松" 解析器, 追求实现精简, 对非法 JSON 不做严格校验/报错,
    ///       遇到畸形输入通常会尽力解析或回退, 而不会抛出格式异常
    /// </summary>
    public static class MiniJson
    {
        /// <summary>
        /// 解析入口: 将 JSON 文本解析为对象树
        /// </summary>
        /// <param name="json">JSON 文本, 允许为 null/空</param>
        /// <returns>
        /// 解析出的对象 (Dictionary / List / string / double / bool / null 之一);
        /// 输入为空时返回 null
        /// </returns>
        public static object Parse(string json)
        {
            // 空输入直接返回 null, 避免后续越界访问
            if (string.IsNullOrEmpty(json)) return null;
            // i 为共享的扫描游标, 从头开始解析第一个值
            int i = 0;
            return ParseValue(json, ref i);
        }

        /// <summary>
        /// 解析任意一个 JSON 值, 根据当前字符分派到具体的解析方法
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标 (引用传递, 会被推进)</param>
        /// <returns>解析出的值对象</returns>
        private static object ParseValue(string s, ref int i)
        {
            // 先跳过值前面的空白字符
            SkipWs(s, ref i);
            // 已到末尾, 无值可读
            if (i >= s.Length) return null;
            // 根据首字符判断值的类型 (JSON 各类型的起始字符互不相同)
            char c = s[i];
            if (c == '{') return ParseObject(s, ref i);  // 对象
            if (c == '[') return ParseArray(s, ref i);  // 数组
            if (c == '"') return ParseString(s, ref i);  // 字符串
            if (c == 't' || c == 'f') return ParseBool(s, ref i);  // 布尔 (true/false)
            // null: 直接跳过 4 个字符 ("null" 长度) 并返回 null, 不做逐字符校验
            if (c == 'n') { i += 4; return null; }
            // 其余情况一律当作数字解析
            return ParseNumber(s, ref i);
        }

        /// <summary>
        /// 解析 JSON 对象 (以 '{' 开头), 返回键值字典
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标, 进入时指向 '{'</param>
        /// <returns>键为字符串、值为对象树的字典</returns>
        private static Dictionary<string, object> ParseObject(string s, ref int i)
        {
            var dict = new Dictionary<string, object>();
            // 跳过起始的 '{'
            i++;
            SkipWs(s, ref i);
            // 处理空对象 "{}": 紧跟 '}' 则直接返回空字典
            if (i < s.Length && s[i] == '}') { i++; return dict; }
            // 循环读取 "键: 值" 对, 直到遇到 '}' 或文本结束
            while (i < s.Length)
            {
                SkipWs(s, ref i);
                // 键必然是字符串, 直接按字符串解析
                string key = ParseString(s, ref i);
                SkipWs(s, ref i);
                // 跳过键值之间的冒号分隔符 (宽松处理: 缺失也不报错)
                if (i < s.Length && s[i] == ':') i++;
                // 递归解析该键对应的值
                object val = ParseValue(s, ref i);
                dict[key] = val;
                SkipWs(s, ref i);
                // 逗号: 还有下一对, 继续循环
                if (i < s.Length && s[i] == ',') { i++; continue; }
                // 右括号: 对象结束, 跳过 '}' 并退出
                if (i < s.Length && s[i] == '}') { i++; break; }
            }
            return dict;
        }

        /// <summary>
        /// 解析 JSON 数组 (以 '[' 开头), 返回元素列表
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标, 进入时指向 '['</param>
        /// <returns>元素为对象树的列表</returns>
        private static List<object> ParseArray(string s, ref int i)
        {
            var list = new List<object>();
            // 跳过起始的 '['
            i++;
            SkipWs(s, ref i);
            // 处理空数组 "[]"
            if (i < s.Length && s[i] == ']') { i++; return list; }
            // 循环读取元素, 直到遇到 ']' 或文本结束
            while (i < s.Length)
            {
                // 递归解析一个元素并加入列表
                list.Add(ParseValue(s, ref i));
                SkipWs(s, ref i);
                // 逗号: 还有下一个元素
                if (i < s.Length && s[i] == ',') { i++; continue; }
                // 右方括号: 数组结束
                if (i < s.Length && s[i] == ']') { i++; break; }
            }
            return list;
        }

        /// <summary>
        /// 解析 JSON 字符串 (以 '"' 开头), 处理转义字符
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标, 进入时指向起始双引号</param>
        /// <returns>去掉引号并还原转义后的字符串内容</returns>
        private static string ParseString(string s, ref int i)
        {
            var sb = new StringBuilder();
            // 跳过起始的双引号
            i++;
            while (i < s.Length)
            {
                // 读取一个字符并推进游标
                char c = s[i++];
                // 遇到结束双引号即完成
                if (c == '"') return sb.ToString();
                // 反斜杠开启转义序列 (且后面还有字符)
                if (c == '\\' && i < s.Length)
                {
                    char esc = s[i++];
                    switch (esc)
                    {
                        case '"': sb.Append('"'); break;  // 转义双引号
                        case '\\': sb.Append('\\'); break;  // 转义反斜杠
                        case '/': sb.Append('/'); break;  // 转义斜杠
                        case 'n': sb.Append('\n'); break;  // 换行
                        case 'r': sb.Append('\r'); break;  // 回车
                        case 't': sb.Append('\t'); break;  // 制表符
                        case 'b': sb.Append('\b'); break;  // 退格
                        case 'f': sb.Append('\f'); break;  // 换页
                        case 'u':
                            // \uXXXX: 取后续 4 位十六进制转为 Unicode 码点
                            if (i + 4 <= s.Length)
                            {
                                sb.Append((char)Convert.ToInt32(s.Substring(i, 4), 16));
                                i += 4;  // 跳过已消费的 4 位十六进制
                            }
                            break;
                        // 未知转义: 宽松处理, 原样保留转义字符本身
                        default: sb.Append(esc); break;
                    }
                }
                else sb.Append(c);  // 普通字符直接追加
            }
            // 未遇到闭合引号就到末尾: 宽松返回已读取的内容
            return sb.ToString();
        }

        /// <summary>
        /// 解析 JSON 数字, 统一返回 double
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标, 进入时指向数字首字符</param>
        /// <returns>
        /// 解析出的 double; 解析失败时 (TryParse 返回 false) d 为 0, 仍返回该值
        /// </returns>
        private static object ParseNumber(string s, ref int i)
        {
            int start = i;
            // 贪婪吞掉所有可能构成数字的字符 (含符号、小数点、科学计数法 e/E)
            while (i < s.Length && "0123456789+-.eE".IndexOf(s[i]) >= 0) i++;
            // 用 InvariantCulture 解析, 保证小数点是 '.' 而不受区域设置影响;
            // NumberStyles.Any 兼容各种数字写法; 失败时 d 默认为 0
            double.TryParse(s.Substring(start, i - start),
                            System.Globalization.NumberStyles.Any,
                            System.Globalization.CultureInfo.InvariantCulture, out double d);
            return d;
        }

        /// <summary>
        /// 解析 JSON 布尔值 (true / false)
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标, 进入时指向 't' 或 'f'</param>
        /// <returns>true 或 false</returns>
        private static bool ParseBool(string s, ref int i)
        {
            // 仅凭首字符判断: 't' 说明是 "true" (长度 4)
            if (s[i] == 't') { i += 4; return true; }
            // 否则是 "false" (长度 5), 直接跳过 5 个字符
            i += 5; return false;
        }

        /// <summary>
        /// 跳过连续的空白字符 (空格、制表、换行等)
        /// </summary>
        /// <param name="s">完整 JSON 文本</param>
        /// <param name="i">扫描游标, 会被推进到首个非空白字符处</param>
        private static void SkipWs(string s, ref int i)
        {
            while (i < s.Length && char.IsWhiteSpace(s[i])) i++;
        }
    }
}