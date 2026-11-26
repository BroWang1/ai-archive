// ==========================================
// 文件: LQATool\Utils\JsonBuilder.cs
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
    /// 本分部 (partial) 文件负责 JsonBuilder 的核心序列化逻辑:
    /// 把 UIDumpResult (整棵 UI 树 + 环境元数据) 手动拼接成带缩进的 JSON 字符串
    /// 底层的格式化原子方法 (FormatVector2 / EscapeJson / FormatRect / FormatColor 等)
    /// 定义在同类的另一个分部文件 JsonBuilder.Format.cs 中
    /// </summary>
    public static partial class JsonBuilder
    {
        /// <summary>
        /// 序列化入口, 将一份完整的 UI 导出结果 (UIDumpResult) 转换为格式化的 JSON 字符串
        /// 先输出屏幕/引擎/画质等环境元数据字段, 再递归输出 nodes 里的整棵 UI 树
        /// </summary>
        /// <param name="result">待序列化的 UI 导出结果根对象</param>
        /// <returns>带 2 空格缩进的完整 JSON 文本</returns>
        public static string Serialize(UIDumpResult result)
        {
            // 使用 StringBuilder 做增量拼接, 避免大量字符串 "+" 拼接带来的内存开销
            StringBuilder sb = new StringBuilder();

            // JSON 根对象起始
            sb.AppendLine("{");
            // 场景名称 (字符串, 需转义防止内含引号/换行破坏 JSON)
            sb.AppendLine($"  \"sceneName\": \"{EscapeJson(result.sceneName)}\",");
            // 游戏客户端版本号
            sb.AppendLine($"  \"appVersion\": \"{EscapeJson(result.appVersion)}\",");
            // Unity 引擎版本号
            sb.AppendLine($"  \"unityVersion\": \"{EscapeJson(result.unityVersion)}\",");
            // 屏幕宽度 (int, 数值直接输出, 无需引号)
            sb.AppendLine($"  \"screenWidth\": {result.screenWidth},");
            // 屏幕高度 (int)
            sb.AppendLine($"  \"screenHeight\": {result.screenHeight},");
            // 屏幕 DPI (float): 用 F3 保留 3 位小数, 并强制 InvariantCulture 使小数点为 "."
            // 防止非英语系系统把小数点渲染成 "," 破坏 JSON 语法
            sb.AppendLine($"  \"screenDpi\": {result.screenDpi.ToString("F3", System.Globalization.CultureInfo.InvariantCulture)},");
            // 系统语言 (字符串)
            sb.AppendLine($"  \"systemLanguage\": \"{EscapeJson(result.systemLanguage)}\",");

            // activeLayerNames 是字符串数组, 需手动拼接 JSON 数组 "[...]"
            sb.Append("  \"activeLayerNames\": [");
            // 判空保护: 数组可能为 null, 为空时直接输出 "[]"
            if (result.activeLayerNames != null)
            {
                for (int i = 0; i < result.activeLayerNames.Length; i++)
                {
                    // 每个元素都是字符串, 同样需要转义
                    sb.Append($"\"{EscapeJson(result.activeLayerNames[i])}\"");

                    // 除最后一个元素外, 元素之间用 ", " 分隔
                    if (i < result.activeLayerNames.Length - 1) sb.Append(", ");
                }
            }
            // 数组闭合, 并补上后续字段的逗号
            sb.AppendLine("],");

            // 屏幕方向 (字符串)
            sb.AppendLine($"  \"orientation\": \"{EscapeJson(result.orientation)}\",");
            // 安全区域 (Rect): 交给 FormatRect 输出 {"x":..,"y":..,"width":..,"height":..} 片段
            sb.AppendLine($"  \"safeArea\": {FormatRect(result.safeArea)},");
            // 画质等级索引 (int)
            sb.AppendLine($"  \"qualityLevel\": {result.qualityLevel},");
            // 画质等级名称 (字符串)
            sb.AppendLine($"  \"qualityLevelName\": \"{EscapeJson(result.qualityLevelName)}\",");
            // 颜色空间 Linear / Gamma (字符串)
            sb.AppendLine($"  \"colorSpace\": \"{EscapeJson(result.colorSpace)}\",");
            // 目标帧率 (int, -1 表示未限制)
            sb.AppendLine($"  \"targetFrameRate\": {result.targetFrameRate},");

            // nodes 是 UI 树的根节点数组, 开始输出数组
            sb.AppendLine($"  \"nodes\": [");
            // 逐个序列化根节点, indentLevel 传 2, 让根节点内容相对根对象再缩进两级
            for (int i = 0; i < result.nodes.Count; i++)
            {
                SerializeNode(sb, result.nodes[i], 2);

                // 非最后 1 个节点在其后补逗号, 最后 1 个节点仅换行, 避免出现非法的尾逗号
                if (i < result.nodes.Count - 1)
                {
                    sb.AppendLine(",");
                }
                else
                {
                    sb.AppendLine();
                }
            }
            // nodes 数组闭合
            sb.AppendLine("  ]");

            // 根对象闭合 (用 Append 不换行, 让 JSON 以 "}" 精确结尾)
            sb.Append("}");

            return sb.ToString();
        }

        /// <summary>
        /// 递归序列化单个 UI 节点 (UINodeData), 输出其基础信息、组件属性字典以及所有子节点
        /// 通过 indentLevel 逐层加深缩进, 使输出的 JSON 保持与 UI 树一致的层级美观
        /// </summary>
        /// <param name="sb">共享的字符串构建器, 序列化结果追加于此</param>
        /// <param name="node">当前待序列化的 UI 节点</param>
        /// <param name="indentLevel">当前缩进层级 (每层 2 个空格), 子节点在此基础上 +2</param>
        private static void SerializeNode(StringBuilder sb, UINodeData node, int indentLevel)
        {
            // 依据缩进层级计算本节点的基准缩进字符串 (每级 2 空格)
            string indent = new string(' ', indentLevel * 2);

            // 节点对象起始
            sb.AppendLine(indent + "{");

            // 节点三个基础字段: 名称 / 层级路径 / 主组件类型 (均为字符串, 需转义)
            sb.AppendLine(indent + $"  \"name\": \"{EscapeJson(node.name)}\",");
            sb.AppendLine(indent + $"  \"path\": \"{EscapeJson(node.path)}\",");
            sb.AppendLine(indent + $"  \"objectType\": \"{EscapeJson(node.objectType)}\",");

            // ObjectData 是两层字典 (组件名 -> (属性名 -> 已格式化的 JSON 片段)), 输出为嵌套对象
            sb.AppendLine(indent + $"  \"ObjectData\": {{");

            // 计数器: 用于判断当前组件是否为最后一个, 从而决定要不要补逗号
            int compCount = 0;
            // 遍历外层字典: 每个 Key 是一个子组件 (如 Transform / Text / Canvas)
            foreach (var compKvp in node.ObjectData)
            {
                // 组件名作为 Key, 值是一个属性对象 "{...}"
                sb.AppendLine(indent + $"    \"{EscapeJson(compKvp.Key)}\": {{");

                // 内层属性计数器, 逻辑同上
                int propCount = 0;

                // 遍历内层字典: 每条是 "属性名 -> 已格式化好的 JSON 值片段"
                // 注意 propKvp.Value 已是合法 JSON 片段 (数字/字符串/对象), 因此直接输出不再加引号或转义
                foreach (var propKvp in compKvp.Value)
                {
                    sb.Append(indent + $"      \"{propKvp.Key}\": {propKvp.Value}");

                    // 非最后一个属性补逗号, 最后一个仅换行 (规避尾逗号)
                    if (propCount < compKvp.Value.Count - 1) sb.AppendLine(",");
                    else sb.AppendLine();

                    propCount++;
                }

                // 单个组件对象闭合
                sb.Append(indent + "    }");

                // 非最后一个组件补逗号, 最后一个仅换行
                if (compCount < node.ObjectData.Count - 1) sb.AppendLine(",");
                else sb.AppendLine();

                compCount++;
            }

            // ObjectData 对象整体闭合 (后面还有 ChildNodes 字段, 故补逗号)
            sb.AppendLine(indent + $"  }},");

            // ChildNodes 子节点数组开始
            sb.AppendLine(indent + $"  \"ChildNodes\": [");
            // 递归序列化每个子节点, 缩进层级 +2 (进入更深一层)
            for (int i = 0; i < node.ChildNodes.Count; i++)
            {
                SerializeNode(sb, node.ChildNodes[i], indentLevel + 2);

                // 非最后一个子节点补逗号, 最后一个仅换行
                if (i < node.ChildNodes.Count - 1) sb.AppendLine(",");
                else sb.AppendLine();
            }
            // ChildNodes 数组闭合
            sb.AppendLine(indent + $"  ]");

            // 当前节点对象闭合 (用 Append 不换行, 逗号/换行交由上层调用方按位置补齐)
            sb.Append(indent + "}");
        }
    }
}