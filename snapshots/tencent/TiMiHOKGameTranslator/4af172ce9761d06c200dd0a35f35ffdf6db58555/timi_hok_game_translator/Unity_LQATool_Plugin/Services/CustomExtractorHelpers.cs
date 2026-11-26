// ==========================================
// 文件: LQATool\Services\CustomExtractorHelpers.cs
// 模块: Services (业务)
// ==========================================

using System;
using System.Collections;
using System.Globalization;
using System.Reflection;
using System.Text;
using UnityEngine;
using LQATool.Models;
using LQATool.Utils;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// 项目自定义组件提取器 (ProjectCustomExtractors) 的通用辅助工具集
    ///
    /// 为什么单独抽出:
    ///   - 项目自定义组件 (如 XxxxLocalize / Xxxx.XxxxText) 的类型未必在本插件的引用范围内,
    ///     因此只能通过反射读字段, 而非强类型访问;
    ///   - 这类反射 + 字段写入是高度重复的样板代码, 集中封装可以让 ProjectCustomExtractors
    ///     里的每个提取器保持 "读字段 → 写 JSON" 的短小结构;
    ///   - 同时保留与 ComponentExtractors (通用 Unity 组件提取器) 完全一致的
    ///     AddComponentProperty(componentName, propertyKey, propertyJsonValue) 写入风格,
    ///     产出的 JSON 片段格式统一, 方便下游解析;
    ///
    /// 关于 internal 可见性: 仅供本程序集内 ProjectCustomExtractors 使用,
    /// 外部调用请走 ComponentExtractors 的公开注册入口
    /// </summary>
    internal static class CustomExtractorHelpers
    {
        /// <summary>
        /// 反射查找字段时统一使用的 BindingFlags 组合:
        /// 公共 + 非公共 + 实例字段, 需要遍历继承链时再按需追加 BindingFlags.DeclaredOnly,
        /// 以避免同名字段被父类覆盖导致读到错误的成员
        /// </summary>
        internal const BindingFlags k_FieldFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;

        // ==========================================
        // 反射读取: 字段
        // ==========================================

        /// <summary>
        /// 按字段名反射读取 comp 上的字段值, 并尝试转换为 T
        ///
        /// 行为要点:
        ///   1. 沿继承链自子类向基类逐层查找 (使用 BindingFlags.DeclaredOnly),
        ///      这样即使父类存在同名 private 字段也能正确命中当前类中最 "近" 的那个;
        ///   2. 命中字段后:
        ///      - 值可直接 as 成 T → 返回 true;
        ///      - 值为 null 且 T 是引用类型 → 视为"存在但为空", 返回 true, out 参数保持默认;
        ///      - 类型不匹配 (例如字段是 int 但 T 是 string) → 返回 false, 不继续沿链查找;
        ///   3. FieldInfo.GetValue 抛出异常时静默返回 false, 保证一个字段的失败不会中断整个提取流程;
        ///
        /// 特别提醒: 若不确定字段的真实类型, 建议以 object 作为 T, 由调用方再做 ToString() 或类型判断,
        /// 参见 ProjectCustomExtractors 中 XxxxLocalize.keyHash 的读取方式
        /// </summary>
        /// <typeparam name="T">期望的字段类型</typeparam>
        /// <param name="comp">目标组件实例, 允许为 null (直接返回 false)</param>
        /// <param name="fieldName">字段名, 大小写敏感, 允许 null/空 (直接返回 false)</param>
        /// <param name="value">读取成功时返回字段值, 失败时为 default</param>
        /// <returns>是否成功读取到符合 T 语义的字段值</returns>
        internal static bool TryGetFieldValue<T>(Component comp, string fieldName, out T value)
        {
            value = default;
            if (comp == null || string.IsNullOrEmpty(fieldName)) return false;

            // 沿继承链逐层向上查找, 直到 System.Object 之前停止
            for (Type t = comp.GetType(); t != null && t != typeof(object); t = t.BaseType)
            {
                // DeclaredOnly: 只看当前类自己声明的字段, 避免与父类同名字段互相干扰
                var f = t.GetField(fieldName, k_FieldFlags | BindingFlags.DeclaredOnly);
                if (f == null) continue;

                try
                {
                    object raw = f.GetValue(comp);
                    if (raw is T tVal)
                    {
                        // 直接命中期望类型
                        value = tVal;
                        return true;
                    }
                    if (raw == null && !typeof(T).IsValueType)
                    {
                        // 引用类型字段允许为 null: 视作 "字段存在, 值为空", 由调用方自行决定是否写入
                        value = default;
                        return true;
                    }
                    // 字段已找到但类型对不上, 没必要再沿继承链继续查找同名字段
                    return false;
                }
                catch
                {
                    // 反射读取异常 (如属性访问器抛错、字段被优化剥离等) 一律吞掉, 保证提取流程不被打断
                    return false;
                }
            }
            return false;
        }

        // ==========================================
        // 字段写入: 与 ComponentExtractors 中既有风格保持完全一致
        // ==========================================

        /// <summary>
        /// 将枚举值以 JSON 字符串字面量的形式写入节点组件属性表
        /// 输出形如 "SomeEnumValue", 与 ComponentExtractors 中
        /// $"\"{sel.transition}\"" 的写法完全一致
        ///
        /// 说明: 参数 value 允许为 null, 此时会写入空字符串 "",
        /// 保持 JSON 结构完整 (调用方若不希望写入空值, 应在外层自行判空过滤)
        /// </summary>
        /// <param name="node">目标节点数据 (提取结果的承载对象)</param>
        /// <param name="compKey">组件键名, 例如 "XxxxText"</param>
        /// <param name="propKey">属性键名, 例如 "textEffectType"</param>
        /// <param name="value">枚举值, 通常用基类 Enum 接住以避免硬引用具体枚举类型</param>
        internal static void AddEnum(UINodeData node, string compKey, string propKey, Enum value)
        {
            node.AddComponentProperty(compKey, propKey, $"\"{(value != null ? value.ToString() : string.Empty)}\"");
        }

        /// <summary>
        /// 将 Color (RGBA) 序列化后写入节点组件属性表
        /// 具体的 JSON 格式由 JsonBuilder.FormatColor 统一负责,
        /// 与通用组件 (如 Text.color / Image.color) 的输出保持一致, 便于下游按同一 schema 解析
        /// </summary>
        internal static void AddColor(UINodeData node, string compKey, string propKey, Color value)
        {
            node.AddComponentProperty(compKey, propKey, JsonBuilder.FormatColor(value));
        }

        /// <summary>
        /// 将 Vector2 序列化后写入节点组件属性表
        /// 具体的 JSON 格式由 JsonBuilder.FormatVector2 统一负责
        /// (与 CanvasScaler.referenceResolution 等既有属性使用同一序列化器)
        /// </summary>
        internal static void AddVector2(UINodeData node, string compKey, string propKey, Vector2 value)
        {
            node.AddComponentProperty(compKey, propKey, JsonBuilder.FormatVector2(value));
        }

        // ==========================================
        // [临时调试] 全字段转储, 完成自定义字段映射后请删除调用
        // ==========================================

        /// <summary>
        /// [仅用于开发期调试] 把 comp 所有 (含私有) 实例字段按继承链逐层打印到 Unity Console
        ///
        /// 使用场景: 在为一个新的项目自定义组件编写提取器时, 通常不清楚字段真实名称 (可能是 CamelCase / camelCase /
        /// m_XXX 等多种风格), 在提取器回调里临时调一次本方法, 就能在 Console 里看到该组件的所有字段名 / 类型 / 当前值,
        /// 从而据此确定 TryGetFieldValue{T} 的入参
        ///
        /// 注意: 生产环境下不应保留调用, 完成映射后请从 ProjectCustomExtractors 中移除相关 DumpAllFieldsForDebug 语句,
        /// 以免每帧 (或每次 Dump UI 时) 刷屏并造成反射开销
        /// </summary>
        /// <param name="comp">要转储的组件, 允许为 null (直接返回)</param>
        /// <param name="includeUnityBaseFields">
        /// 是否包含 UnityEngine.* / UnityEditor.* 基类中声明的字段
        /// 默认 false: 只关心项目自定义脚本自身声明的字段, 屏蔽 MonoBehaviour / Behaviour / Component 等基类噪声
        /// </param>
        internal static void DumpAllFieldsForDebug(Component comp, bool includeUnityBaseFields = false)
        {
            if (comp == null) return;

            var sb = new StringBuilder();
            // (Unity 6000.4+ 原生 GetInstanceID() 已被标记为编译错误, 改走 UIHelper.GetStableInstanceId 做版本兼容)
            sb.Append("[LQATool][CustomExtractorHelpers] 转储组件 ").Append(comp.GetType().FullName).Append(" 位于 '").Append(comp.name).Append("' (InstanceID=").Append(UIHelper.GetStableInstanceId(comp)).Append(")\n");

            // 收集从子类到基类 (Object 除外) 的完整继承链, 后续按声明层级分块打印
            var chain = new System.Collections.Generic.List<Type>();
            for (Type t = comp.GetType(); t != null && t != typeof(object); t = t.BaseType)
            {
                chain.Add(t);
            }

            int totalFieldCount = 0;
            for (int i = 0; i < chain.Count; i++)
            {
                var t = chain[i];

                // 默认跳过 Unity 引擎基类, 避免打印 MonoBehaviour / Behaviour / Component 等无关字段
                if (!includeUnityBaseFields && t.FullName != null && (t.FullName.StartsWith("UnityEngine.") || t.FullName.StartsWith("UnityEditor.")))
                {
                    continue;
                }

                // DeclaredOnly: 严格只列出当前类声明的字段, 防止与父类同名字段重复打印
                var fields = t.GetFields(k_FieldFlags | BindingFlags.DeclaredOnly);
                if (fields == null || fields.Length == 0) continue;

                sb.Append("  ── 类 ").Append(t.FullName).Append(" (声明了 ").Append(fields.Length).Append(" 个字段) ──\n");

                for (int j = 0; j < fields.Length; j++)
                {
                    var f = fields[j];
                    object val;
                    // 逐字段捕获异常: 属性/字段 getter 抛错时仅标记为读取失败, 不影响其它字段的输出
                    try { val = f.GetValue(comp); }
                    catch (Exception ex) { val = "<read failed: " + ex.GetType().Name + ">"; }

                    sb.Append("    ").Append(f.IsPublic ? "public " : "private").Append(' ').Append(GetFriendlyTypeName(f.FieldType)).Append(' ').Append(f.Name).Append(" = ").Append(FormatValueForDebug(val)).Append('\n');

                    totalFieldCount++;
                }
            }

            sb.Append("  已转储字段总数: ").Append(totalFieldCount);

            // 传入 context 参数 (comp), 在 Console 里点击日志可高亮到对应 GameObject / Component
            Debug.Log(sb.ToString(), comp);
        }

        /// <summary>
        /// 将 Type 转成便于阅读的短名字符串, 供 DumpAllFieldsForDebug 打印使用
        ///
        /// 处理规则:
        ///   - null → "?";
        ///   - 数组 → 递归输出元素类型 + "[]" (支持多维数组的元素部分, 但不再区分秩);
        ///   - 泛型 → 去掉 "`N" 后缀并递归展开泛型参数, 例如 List<int> 而非 List`1;
        ///   - 其它情况直接取 Type.Name (不含命名空间, 保持简洁);
        /// </summary>
        internal static string GetFriendlyTypeName(Type t)
        {
            if (t == null) return "?";
            if (t.IsArray) return GetFriendlyTypeName(t.GetElementType()) + "[]";

            if (t.IsGenericType)
            {
                // 泛型名形如 "List`1", 去掉反引号后缀
                var def = t.GetGenericTypeDefinition().Name;
                int tick = def.IndexOf('`');
                if (tick >= 0) def = def.Substring(0, tick);

                var args = t.GetGenericArguments();
                var inner = new string[args.Length];
                for (int i = 0; i < args.Length; i++) inner[i] = GetFriendlyTypeName(args[i]);
                return def + "<" + string.Join(", ", inner) + ">";
            }

            return t.Name;
        }

        /// <summary>
        /// 将任意字段值格式化为便于人眼阅读的字符串, 供 DumpAllFieldsForDebug 打印使用
        ///
        /// 特殊处理:
        ///   - null → 字面量 "null";
        ///   - string → 加双引号, 直观区分字符串和其它类型 (不做转义, 调试用足够);
        ///   - UnityEngine.Object → 打印 "TypeName(\"objectName\")", 并额外识别 "伪 null"
        ///     (Unity 对象被销毁后 ==null 为 true, 但托管引用非空);
        ///   - ICollection → 只输出类型 + 元素数量, 避免大集合刷屏;
        ///   - 其它类型 → 回退到 ToString();
        /// </summary>
        internal static string FormatValueForDebug(object val)
        {
            if (val == null) return "null";
            if (val is string s) return "\"" + s + "\"";

            if (val is UnityEngine.Object uo)
            {
                // 处理 Unity 对象的"伪 null": 托管引用尚在但底层原生对象已销毁
                if (uo == null) return "<destroyed UnityObject>";
                return uo.GetType().Name + "(\"" + uo.name + "\")";
            }

            if (val is ICollection col)
            {
                // 集合仅显示元素个数, 避免把上万条数据打进日志
                return GetFriendlyTypeName(val.GetType()) + " { Count = " + col.Count + " }";
            }

            return val.ToString();
        }
    }
}