// ==========================================
// 文件: LQARestore\Core\Runtime\Json\JsonWriter.cs
// 模块: Core.Json (核心层 JSON 数据读写)
// ==========================================

using System.Collections.Generic;
using System.Globalization;
using System.Text;

/// <summary>
/// LQARestore 核心层 JSON 数据读写命名空间
/// </summary>
namespace LQARestore.Core.Json
{
    /// <summary>
    /// 极简 JSON 序列化器 (与 MiniJson 对称: MiniJson 只解析, 本类只写出)
    /// 用途: 把 MiniJson.Parse 得到的对象树 (Dictionary / List / string / bool / double / null)
    ///       重新序列化为 JSON 文本, 供 "文本人工显示" 窗口把 manualShow 标记写回磁盘
    /// 为什么需要单独写一个: MiniJson 只负责解析没有序列化能力; 而通用 JSON 库的输出
    ///       (缩进风格 / 数字格式 / 键顺序) 与采集侧 LQATool.Utils.JsonBuilder 生成的原始文件不一致,
    ///       回写后会与原文件产生大量无意义的 diff, 故这里刻意 "复刻" 采集侧的排版与数字模板
    /// 排版规则 (复刻采集侧 JsonBuilder 的固定模板, 保证回写前后风格一致):
    ///   采集侧并非按数据结构递归决定换行, 而是只有固定的 "结构骨架" 层级才多行展开:
    ///     根对象 / nodes[] / 每个节点对象 / ObjectData / 组件块 / ChildNodes[]
    ///   这些骨架之外的一切 (组件块内部的属性值, 无论标量还是对象/数组) 一律单行内联,
    ///   例如 color / font / localEulerAngles / safeArea / activeLayerNames / visibilityDebug 等
    ///   另外: 骨架层级的空容器 (如空 ChildNodes / 空 ObjectData) 仍换行为 "[\n<indent>]" / "{\n<indent>}",
    ///        而内联层级的空容器保持紧凑 "[]" / "{}"
    /// 数字格式 (复刻采集侧不同字段的固定小数位, 见 _fmtByKey / ResolveInnerFmt):
    ///   MiniJson 把所有 JSON 数字统一解析为 double, 丢失了采集侧写入时的小数位模板
    ///   (采集侧对不同字段分别用了 F3 / F2 / 原生), 故这里按 "字段键名" 反查模板还原,
    ///   使浮点数文本 (如 1.000 / 1.00 / 1920) 与原始文件一致
    /// 值格式约定 (与采集侧一致):
    ///   - 缩进单位 2 空格; 键值分隔 "key": value (冒号后一个空格);
    ///   - 字符串转义 \ " \n \r \t 五类, 其余字符 (含中文) 原样输出;
    ///   - bool: true / false; null: null
    /// 实现方式: 递归下降写出, 用 Level 参数标识当前所处骨架层级以决定 "展开 or 内联",
    ///           用 NumFmt 参数沿内联子树向下传递数字小数位模板
    /// </summary>
    public static class JsonWriter
    {
        // ==========================================
        // 骨架键常量: 决定多行展开时机的固定键名 (与采集侧的树结构约定一一对应)
        // ==========================================

        /// <summary>
        /// 根对象下需要展开的节点数组键
        /// </summary>
        private const string KEY_NODES = "nodes";

        /// <summary>
        /// 节点对象下需要展开的组件容器键 (其子对象为各组件块)
        /// </summary>
        private const string KEY_OBJECT_DATA = "ObjectData";

        /// <summary>
        /// 节点对象下需要展开的子节点数组键
        /// </summary>
        private const string KEY_CHILD_NODES = "ChildNodes";

        /// <summary>
        /// 骨架层级枚举: 标识当前正在写出的对象处于树的哪一层, 用于决定其子值是否继续展开
        /// (只有骨架层级会多行展开, Inline 层级及更深一律单行内联)
        /// </summary>
        private enum Level
        {
            Root,  // 根对象: 仅 nodes 展开
            Node,  // 节点对象: 仅 ObjectData / ChildNodes 展开
            ObjectData,  // ObjectData: 其下各组件块全部展开
            Inline  // 其它: 一律内联 (组件块内部及更深)
        }

        /// <summary>
        /// 数字格式模式: 对应采集侧不同字段所用的固定小数位
        /// </summary>
        private enum NumFmt
        {
            Raw,  // InvariantCulture 原生: 整数不带小数点, 小数保留原值 (localScale / 坐标 / 各整型字段等)
            F2,  // 保留 2 位小数 (lineSpacing)
            F3  // 保留 3 位小数 (color / safeArea / screenDpi / ratio 等)
        }

        /// <summary>
        /// "属性键名 -> 该属性数字的小数位模板" 映射, 复刻采集侧 JsonBuilder / ComponentExtractors 的格式
        /// 说明:
        ///   - color / outlineColor / shadowColor / safeArea 等本身是 "内联对象", 其模板作用于该对象内部的
        ///     所有数字子值 (故这里登记的是 "父键", 由 WriteInline 沿子树继承);
        ///   - screenDpi / lineSpacing 等 "标量数字字段" 直接以自身键名登记;
        ///   - 未登记的键一律走 Raw (覆盖整型字段与 localScale 等原生浮点)
        /// </summary>
        private static readonly Dictionary<string, NumFmt> _fmtByKey = new Dictionary<string, NumFmt>
        {
            // F3 标量字段
            { "screenDpi", NumFmt.F3 },
            { "referencePixelsPerUnit", NumFmt.F3 },
            { "matchWidthOrHeight", NumFmt.F3 },
            // F3 内联对象 (模板作用于其内部所有数字)
            { "safeArea", NumFmt.F3 },
            { "color", NumFmt.F3 },
            { "outlineColor", NumFmt.F3 },
            { "shadowColor", NumFmt.F3 },
            // F2 标量字段
            { "lineSpacing", NumFmt.F2 },
        };

        /// <summary>
        /// visibilityDebug 是 "混合模板" 的内联对象: 其内部只有 ratio / ratioThreshold 两键用 F3,
        /// 其余 (id / maskTotal / diffCount / aabb ...) 用 Raw, 故单独用此集合识别需 F3 的子键
        /// </summary>
        private static readonly HashSet<string> _visDebugF3 = new HashSet<string> { "ratio", "ratioThreshold" };

        /// <summary>
        /// 序列化入口: 把对象树转换为 JSON 文本
        /// </summary>
        /// <param name="value">对象树 (根通常为 Dictionary, 由 MiniJson.Parse 产生)</param>
        /// <returns>格式化后的 JSON 字符串</returns>
        public static string Serialize(object value)
        {
            var sb = new StringBuilder();
            // 根为对象则按 Root 骨架层级展开; 否则 (极少见) 直接内联写出, 保证鲁棒
            if (value is Dictionary<string, object> root)
                WriteObject(sb, root, 0, Level.Root);
            else
                WriteInline(sb, value);
            return sb.ToString();
        }

        /// <summary>
        /// 单行内联序列化: 把对象树压成紧凑单行 JSON (对象/数组递归内联)
        /// 供调用方自行控制外层换行缩进时, 对 "叶子对象" 做内联序列化 (如 rect_locations 的每个文本框)
        /// 复用与 Serialize 相同的字符串转义与数字格式化规则
        /// </summary>
        /// <param name="value">对象树 (Dictionary / List / string / bool / double / null)</param>
        /// <returns>单行紧凑 JSON 字符串</returns>
        public static string SerializeInline(object value)
        {
            var sb = new StringBuilder();
            WriteInline(sb, value);
            return sb.ToString();
        }

        /// <summary>
        /// 写出一个对象: 依据 level 决定多行展开还是单行内联
        /// </summary>
        /// <param name="sb">共享的字符串构建器</param>
        /// <param name="dict">待写出的对象</param>
        /// <param name="indentLevel">当前缩进层级 (每级 2 空格)</param>
        /// <param name="level">当前骨架层级, 决定本对象与其子值的展开策略</param>
        private static void WriteObject(StringBuilder sb, Dictionary<string, object> dict, int indentLevel, Level level)
        {
            // 仅 Inline 层级单行输出; 骨架层级 (Root/Node/ObjectData) 即使为空也换行展开,
            // 以与采集侧 JsonBuilder 的固定模板一致 (如空 ObjectData 输出为 "{\n<indent>}")
            if (level == Level.Inline)
            {
                WriteInline(sb, dict);
                return;
            }

            // 子项缩进 (深一级) 与闭合括号缩进 (本级)
            string childIndent = new string(' ', (indentLevel + 1) * 2);
            string closeIndent = new string(' ', indentLevel * 2);

            sb.Append("{\n");
            int i = 0;
            foreach (var kvp in dict)
            {
                // 输出 "key": 再由 WriteChild 依据 "父层级 + 键名" 决定其值如何写
                sb.Append(childIndent).Append('"').Append(Escape(kvp.Key)).Append("\": ");
                WriteChild(sb, kvp.Key, kvp.Value, indentLevel + 1, level);
                // 非最后一项补逗号, 规避非法尾逗号
                if (i < dict.Count - 1) sb.Append(',');
                sb.Append('\n');
                i++;
            }
            sb.Append(closeIndent).Append('}');
        }

        /// <summary>
        /// 写出对象的某个子值: 依据 "父层级 + 键名" 判定该子值应展开 (骨架) 还是内联, 并分派到对应写法
        /// </summary>
        /// <param name="sb">共享的字符串构建器</param>
        /// <param name="key">子值对应的键名</param>
        /// <param name="value">子值本身</param>
        /// <param name="indentLevel">子值所在的缩进层级</param>
        /// <param name="parentLevel">父对象的骨架层级</param>
        private static void WriteChild(StringBuilder sb, string key, object value, int indentLevel, Level parentLevel)
        {
            // 依据 "父层级 + 键名" 推断子值的目标骨架层级 (缺省 Inline: 即不展开)
            Level childLevel = Level.Inline;
            switch (parentLevel)
            {
                case Level.Root:
                    // 根对象下只有 nodes 展开 (其元素为节点对象)
                    if (key == KEY_NODES) childLevel = Level.Node;
                    break;
                case Level.Node:
                    // 节点对象下: ObjectData 展开为组件块容器, ChildNodes 展开为节点数组
                    if (key == KEY_OBJECT_DATA) childLevel = Level.ObjectData;
                    else if (key == KEY_CHILD_NODES) childLevel = Level.Node;
                    break;
                case Level.ObjectData:
                    // ObjectData 下的每个键都是组件块 (由下方 Dict 分支单独处理为组件块写法)
                    childLevel = Level.Inline;
                    break;
            }

            if (value is Dictionary<string, object> childDict)
            {
                if (parentLevel == Level.ObjectData)
                    // ObjectData 的直接子对象即 "组件块": 自身多行展开, 但内部属性一律内联
                    WriteComponentBlock(sb, childDict, indentLevel);
                else if (childLevel == Level.Inline)
                    // 内联对象 (如 safeArea): 按父键模板单行内联写出
                    WriteInline(sb, childDict, ResolveFmt(key, NumFmt.Raw));
                else
                    // 骨架对象 (如 ObjectData 容器本身)
                    WriteObject(sb, childDict, indentLevel, childLevel);
            }
            else if (value is List<object> childList)
            {
                // 只有 nodes / ChildNodes 是需要展开的 "节点数组", 其余数组内联 (如 activeLayerNames)
                if (childLevel == Level.Node)
                    WriteNodeArray(sb, childList, indentLevel);
                else
                    WriteInline(sb, childList, ResolveFmt(key, NumFmt.Raw));
            }
            else
            {
                // 标量 (string / bool / double / null): 内联写出, 并按键名解析其数字模板
                WriteInline(sb, value, ResolveFmt(key, NumFmt.Raw));
            }
        }

        /// <summary>
        /// 写出组件块 (ObjectData 下的直接子对象, 如 Text / Canvas / XxxxText):
        /// 组件块自身多行展开 (空块也换行), 但其内部每个属性值一律内联
        /// (属性值内联时按属性键名解析数字模板, 如 color -> F3、lineSpacing -> F2)
        /// </summary>
        /// <param name="sb">共享的字符串构建器</param>
        /// <param name="dict">组件块对象</param>
        /// <param name="indentLevel">组件块所在的缩进层级</param>
        private static void WriteComponentBlock(StringBuilder sb, Dictionary<string, object> dict, int indentLevel)
        {
            string childIndent = new string(' ', (indentLevel + 1) * 2);
            string closeIndent = new string(' ', indentLevel * 2);

            sb.Append("{\n");
            int i = 0;
            foreach (var kvp in dict)
            {
                sb.Append(childIndent).Append('"').Append(Escape(kvp.Key)).Append("\": ");
                // 组件块内部属性一律内联; 传入属性键名以便按模板表选择数字小数位
                WriteInline(sb, kvp.Value, ResolveFmt(kvp.Key, NumFmt.Raw));
                if (i < dict.Count - 1) sb.Append(',');
                sb.Append('\n');
                i++;
            }
            sb.Append(closeIndent).Append('}');
        }

        /// <summary>
        /// 写出节点数组 (nodes / ChildNodes): 多行展开, 每个元素为节点对象 (按 Node 层级展开);
        /// 即使为空也换行为 "[\n<indent>]", 与采集侧固定模板一致 (不压成 "[]")
        /// </summary>
        /// <param name="sb">共享的字符串构建器</param>
        /// <param name="list">节点数组</param>
        /// <param name="indentLevel">数组所在的缩进层级</param>
        private static void WriteNodeArray(StringBuilder sb, List<object> list, int indentLevel)
        {
            string childIndent = new string(' ', (indentLevel + 1) * 2);
            string closeIndent = new string(' ', indentLevel * 2);

            sb.Append("[\n");
            for (int i = 0; i < list.Count; i++)
            {
                sb.Append(childIndent);
                // 元素正常应为节点对象, 按 Node 层级展开; 其它类型 (理论上不会出现) 内联兜底
                if (list[i] is Dictionary<string, object> nodeDict)
                    WriteObject(sb, nodeDict, indentLevel + 1, Level.Node);
                else
                    WriteInline(sb, list[i]);
                if (i < list.Count - 1) sb.Append(',');
                sb.Append('\n');
            }
            sb.Append(closeIndent).Append(']');
        }

        // ==========================================
        // 内联写出 (单行): 对象 / 数组 / 标量
        // ==========================================

        /// <summary>
        /// 单行内联写出任意值 (对象/数组递归内联, 元素间用 ", " 分隔)
        /// </summary>
        /// <param name="sb">共享的字符串构建器</param>
        /// <param name="value">待写出的值</param>
        /// <param name="fmt">该值 (及其内部数字) 的小数位模板, 缺省 Raw</param>
        private static void WriteInline(StringBuilder sb, object value, NumFmt fmt = NumFmt.Raw)
        {
            switch (value)
            {
                case null:
                    sb.Append("null");
                    break;
                case string s:
                    // 字符串: 加引号并转义
                    sb.Append('"').Append(Escape(s)).Append('"');
                    break;
                case bool b:
                    // 布尔: 小写 true/false 以符合 JSON 规范
                    sb.Append(b ? "true" : "false");
                    break;
                case Dictionary<string, object> dict:
                    // 内联对象: {"k": v, ...}
                    sb.Append('{');
                    int di = 0;
                    foreach (var kvp in dict)
                    {
                        sb.Append('"').Append(Escape(kvp.Key)).Append("\": ");
                        // 内部子值的模板: 优先按子键自身模板 (处理 visibilityDebug 混合情形),
                        // 否则继承父对象的 fmt (处理 color / safeArea 整体 F3)
                        WriteInline(sb, kvp.Value, ResolveInnerFmt(kvp.Key, fmt));
                        if (di < dict.Count - 1) sb.Append(", ");
                        di++;
                    }
                    sb.Append('}');
                    break;
                case List<object> list:
                    // 内联数组: [v, ...] (元素统一继承同一 fmt)
                    sb.Append('[');
                    for (int i = 0; i < list.Count; i++)
                    {
                        WriteInline(sb, list[i], fmt);
                        if (i < list.Count - 1) sb.Append(", ");
                    }
                    sb.Append(']');
                    break;
                default:
                    // 其余一律当作数字处理 (MiniJson 解析出的数字为 double)
                    WriteNumber(sb, value, fmt);
                    break;
            }
        }

        /// <summary>
        /// 写出数字: MiniJson 把所有 JSON 数字解析为 double, 这里按 fmt 还原采集侧的小数位
        /// </summary>
        /// <param name="sb">共享的字符串构建器</param>
        /// <param name="value">数字值 (预期为 double)</param>
        /// <param name="fmt">小数位模板</param>
        private static void WriteNumber(StringBuilder sb, object value, NumFmt fmt)
        {
            if (value is double d)
            {
                switch (fmt)
                {
                    case NumFmt.F3:
                        // 固定 3 位小数 (如 1.000 / 0.698); InvariantCulture 保证小数点为 "."
                        sb.Append(d.ToString("F3", CultureInfo.InvariantCulture));
                        return;
                    case NumFmt.F2:
                        // 固定 2 位小数 (如 1.00)
                        sb.Append(d.ToString("F2", CultureInfo.InvariantCulture));
                        return;
                    default:
                        // Raw: 无小数部分则输出整数 (如 1920 而非 1920.0), 否则用 "R" 往返格式保留原值精度
                        if (d == System.Math.Floor(d) && !double.IsInfinity(d) &&
                            d >= long.MinValue && d <= long.MaxValue)
                            sb.Append(((long)d).ToString(CultureInfo.InvariantCulture));
                        else
                            sb.Append(d.ToString("R", CultureInfo.InvariantCulture));
                        return;
                }
            }
            // 理论上不会走到 (MiniJson 数字均为 double), 兜底以不变文化原样输出
            sb.Append(System.Convert.ToString(value, CultureInfo.InvariantCulture));
        }

        /// <summary>
        /// 按属性键名解析其数字模板 (适用于 "顶层标量" 或 "内联对象的父键"), 未登记则返回 fallback
        /// </summary>
        /// <param name="key">属性键名</param>
        /// <param name="fallback">未登记时的回退模板</param>
        /// <returns>解析出的数字模板</returns>
        private static NumFmt ResolveFmt(string key, NumFmt fallback)
        {
            return _fmtByKey.TryGetValue(key, out var f) ? f : fallback;
        }

        /// <summary>
        /// 内联对象 "内部子键" 的模板解析 (处理内联对象内部的模板差异):
        ///   - visibilityDebug 是混合模板: 子键 ratio / ratioThreshold 用 F3, 其余用 Raw;
        ///   - aabb 是 visibilityDebug 内的子对象, 其内部 x/y/width/height 均为整数 -> Raw;
        ///   - 其它内联对象 (如 color / safeArea) 的子键继承父对象模板 parentFmt
        /// </summary>
        /// <param name="childKey">内联对象内部的子键名</param>
        /// <param name="parentFmt">父对象 (内联对象自身) 的模板</param>
        /// <returns>该子键对应的数字模板</returns>
        private static NumFmt ResolveInnerFmt(string childKey, NumFmt parentFmt)
        {
            if (_visDebugF3.Contains(childKey)) return NumFmt.F3;
            if (childKey == "aabb") return NumFmt.Raw;
            return parentFmt;
        }

        /// <summary>
        /// 对字符串做 JSON 转义 (与采集侧 JsonBuilder.EscapeJson 规则一致)
        /// </summary>
        /// <param name="str">原始字符串 (可为 null/空)</param>
        /// <returns>转义后的字符串; 输入为 null/空时返回空字符串</returns>
        private static string Escape(string str)
        {
            // 空值保护: null/空串统一返回 "", 避免后续 Replace 抛异常
            if (string.IsNullOrEmpty(str)) return "";
            // 转义顺序至关重要: 反斜杠必须最先替换, 否则后续新引入的 "\" 会被重复转义导致结果错误
            return str.Replace("\\", "\\\\")  // 反斜杠 \  -> \\
                      .Replace("\"", "\\\"")  // 双引号 "  -> \"
                      .Replace("\n", "\\n")  // 换行符    -> \n
                      .Replace("\r", "\\r")  // 回车符    -> \r
                      .Replace("\t", "\\t");  // 制表符    -> \t
        }
    }
}