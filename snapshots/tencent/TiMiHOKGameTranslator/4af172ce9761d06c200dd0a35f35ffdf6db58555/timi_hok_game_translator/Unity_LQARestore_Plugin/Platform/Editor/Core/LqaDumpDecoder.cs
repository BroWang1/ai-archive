// ==========================================
// 文件: LQARestore\Platform\Editor\Core\LqaDumpDecoder.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System;
using System.IO;
using System.IO.Compression;
using System.Text;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// dump 数据解码器 (编辑器侧)
    /// 平台下发的 dump 数据是 gzip 压缩后的 json
    /// 从 DownloadHost 下载得到的原始字节需经 "三连解码" 才能得到干净的 dump json:
    ///   1. 魔数判定: 前两字节是否 0x1F 0x8B (gzip) —— 是则解压, 否则视为明文 json;
    ///   2. 解压: GZipStream 解为 UTF-8 文本;
    ///   3. 截断: 截到最后一个 '}' 为止 —— gzip 尾部可能带 padding/多余字节, 不截会导致
    ///      JSON 解析在末尾报错 (曾实际踩过的坑, 必须保留处理)
    /// </summary>
    public static class LqaDumpDecoder
    {
        /// <summary>
        /// 判定原始字节流是否为 gzip 压缩数据: 依据 gzip 固定文件头魔数 0x1F 0x8B (前两字节)
        /// 用于 Decode 决定走 "解压" 还是 "按明文处理" 分支
        /// </summary>
        /// <param name="data">待判定的原始字节数组</param>
        /// <returns>前两字节为 gzip 魔数时返回 true; data 为 null 或长度不足 2 时返回 false</returns>
        private static bool IsGzip(byte[] data)
        {
            // 先做空/长度保护 (不足 2 字节无从比对魔数), 再逐字节比对 gzip 头 0x1F 0x8B
            return data != null && data.Length >= 2 && data[0] == 0x1F && data[1] == 0x8B;
        }

        /// <summary>
        /// 把下载得到的原始字节解码为 dump json 文本, 失败时抛异常 (调用方捕获给出提示)
        /// 流程: 空内容校验 → gzip 魔数判定 (是则解压, 否则按明文) → 截断尾部多余字节
        /// </summary>
        /// <param name="raw">从 DownloadHost 下载得到的原始字节 (可能是 gzip 压缩, 也可能是明文 json)</param>
        /// <returns>解码并截断后的干净 dump json 文本</returns>
        /// <exception cref="Exception">raw 为 null 或空时抛出 "下载内容为空"</exception>
        public static string Decode(byte[] raw)
        {
            // 空内容直接判失败: 后续解压/解析都无意义, 提前抛异常让调用方给出明确提示
            if (raw == null || raw.Length == 0)
                throw new Exception("下载内容为空");

            string text;
            if (IsGzip(raw))
            {
                // gzip 分支: 用 GZipStream 解压, CopyTo 到内存流后按 UTF-8 还原文本
                // using 逐层释放三个流 (输入源流 / 解压流 / 输出流), 避免句柄/内存泄漏
                using (var input = new MemoryStream(raw))
                using (var gz = new GZipStream(input, CompressionMode.Decompress))
                using (var output = new MemoryStream())
                {
                    gz.CopyTo(output);
                    text = Encoding.UTF8.GetString(output.ToArray());
                }
            }
            else
            {
                // 非 gzip, 视为明文 json (兼容平台未压缩下发的情况)
                text = Encoding.UTF8.GetString(raw);
            }

            // 无论走哪个分支, 统一截断尾部多余字节后再返回 (见 TrimToLastBrace)
            return TrimToLastBrace(text);
        }

        /// <summary>
        /// 截断到最后一个 '}' (含), 去掉尾部可能的 padding/多余字节
        /// 若文本中没有 '}', 原样返回 (交给上层 JSON 解析去报错)
        /// </summary>
        /// <param name="text">解压/解码后的原始文本</param>
        /// <returns>截断到最后一个 '}' 的文本; text 为空或不含 '}' 时原样返回</returns>
        private static string TrimToLastBrace(string text)
        {
            // 空文本无需处理, 原样返回避免 LastIndexOf/Substring 越界
            if (string.IsNullOrEmpty(text)) return text;
            // 定位最后一个 '}': gzip 解压后尾部可能残留 padding/多余字节, 以最后一个右花括号作为 json 结尾
            int idx = text.LastIndexOf('}');
            // 找到则截到该 '}' (含, 故 +1); 未找到说明本就不是合法 json, 原样交给上层解析报错
            return idx >= 0 ? text.Substring(0, idx + 1) : text;
        }
    }
}