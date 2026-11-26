// ==========================================
// 文件: LQATool\Services\ComponentExtractors.cs
// 模块: Services (业务)
// ==========================================

using System;
using System.Globalization;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using LQATool.Config;
using LQATool.Models;
using LQATool.Utils;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// 组件属性提取器的注册中心 (通用 Unity 组件)
    ///
    /// 职责:
    ///   - 维护一张 "组件类型 -> 提取函数" 的注册表;
    ///   - 提供 ExtractAll: 遍历某个 Transform 上挂载的所有已注册组件, 把它们的属性抽取成
    ///     JSON 片段写入 UINodeData.ObjectData, 最终由 JsonBuilder 序列化成导出 JSON;
    ///
    /// 设计要点:
    ///   - 采用注册表模式, 新增一种组件的支持只需 Register, 无需改动遍历逻辑;
    ///   - 通用 Unity 组件 (Canvas / Text 等) 在本类的 RegisterAllExtractors 中集中注册;
    ///   - 项目专属脚本 (XxxxLocalize / XxxxText 等) 由 ProjectCustomExtractors 通过反射注册, 与本类解耦;
    ///   - 声明为 static, 全局只有一份注册表, 由静态构造函数在首次访问时初始化一次;
    /// </summary>
    internal static class ComponentExtractors
    {
        // ==========================================
        // 注册表条目 (用 struct 避免 GC)
        // ==========================================

        /// <summary>
        /// 单条注册表条目: 把 "组件类型" 与 "针对该类型的提取函数" 绑定在一起
        /// 用 struct 而非 class, 是为了让条目内联存储在 List 中, 避免为每条注册产生一次堆分配 (减少 GC 压力)
        /// </summary>
        private struct ExtractorEntry
        {
            /// <summary>
            /// 目标组件的类型, ExtractAll 会用它调用 Transform.GetComponent(Type) 探测组件是否存在
            /// </summary>
            public Type ComponentType;

            /// <summary>
            /// 提取函数: 入参为探测到的组件实例与当前节点数据, 负责把组件属性写入 node
            /// 统一以基类 Component 为签名, 泛型版本 Register<T> 内部会做一次向下转型再回调
            /// </summary>
            public Action<Component, UINodeData> Extractor;
        }

        // ==========================================
        // 注册表存储
        // ==========================================

        /// <summary>
        /// 全局注册表, 存放所有已登记的 (组件类型, 提取函数) 条目, 由静态构造填充后只读遍历
        /// </summary>
        private static readonly List<ExtractorEntry> _entries = new List<ExtractorEntry>();

        // ==========================================
        // 静态构造: 注册所有提取器
        // ==========================================

        /// <summary>
        /// 静态构造函数, 在本类被首次访问时由 CLR 自动调用一次
        /// 负责填充注册表: 先注册通用 Unity 组件, 再注册项目自定义组件
        /// </summary>
        static ComponentExtractors()
        {
            // 注册通用 Unity 组件 (Canvas / CanvasScaler / Text ...)
            RegisterAllExtractors();
            // 注册项目专属组件 (通过反射按类型名匹配, 目标类型不存在时会被静默跳过)
            ProjectCustomExtractors.RegisterAll();
        }

        // ==========================================
        // 公开 API: 供 BuildNodeTree 调用
        // ==========================================

        /// <summary>
        /// 遍历给定 Transform 上挂载的所有已注册组件, 依次执行对应的提取函数, 把属性写入 node
        /// 由 UI 树构建流程 (BuildNodeTree) 对每个节点调用一次
        /// </summary>
        /// <param name="t">当前正在处理的节点 Transform</param>
        /// <param name="node">与该 Transform 对应的节点数据, 提取结果写入其 ObjectData</param>
        internal static void ExtractAll(Transform t, UINodeData node)
        {
            // 逐条检查注册表: 用 for 而非 foreach, 避免枚举器分配, 同时明确按注册顺序执行
            for (int i = 0; i < _entries.Count; i++)
            {
                // 探测该 Transform 上是否挂有此类型的组件
                Component comp = t.GetComponent(_entries[i].ComponentType);

                // 没有该组件则跳过, 交给下一条注册项
                if (comp == null) continue;

                try
                {
                    // 执行提取函数, 把组件属性写入 node.ObjectData
                    _entries[i].Extractor(comp, node);
                }
                catch (MissingReferenceException)
                {
                    // 组件/其引用的对象在遍历途中被销毁 (常见于运行时动态 UI), 属预期情况, 静默忽略
                }
                catch (System.Exception e)
                {
                    // 其他异常: 单个提取器失败不应中断整棵树的导出, 记一条警告后继续处理其余组件
                    Debug.LogWarning($"[LQATool][ComponentExtractors] {t.gameObject.name} 上的提取器 {_entries[i].ComponentType.Name} 失败: {e.Message}");
                }
            }
        }

        // ==========================================
        // 注册辅助方法
        // ==========================================

        /// <summary>
        /// 泛型注册: 用于编译期已知类型的标准 Unity 组件
        /// 调用方直接以强类型 T 编写提取逻辑, 内部包一层把 Component 向下转型为 T 再回调
        /// </summary>
        /// <typeparam name="T">目标组件类型, 必须派生自 Component</typeparam>
        /// <param name="extractor">针对 T 的提取函数</param>
        internal static void Register<T>(Action<T, UINodeData> extractor) where T : Component
        {
            _entries.Add(new ExtractorEntry
            {
                ComponentType = typeof(T),
                // 适配层: 注册表统一存 Action<Component, ...>, 这里把入参强转成 T 再转发给业务提取器
                Extractor = (comp, node) => extractor((T)comp, node)
            });
        }

        /// <summary>
        /// 按类型名注册: 用于类型不在本插件引用范围内的项目专属组件 (如 XxxxLocalize / Xxxx.XxxxText)
        /// 通过反射遍历当前已加载的所有程序集, 查找名称匹配且派生自 Component 的类型
        /// 目标类型在当前工程中不存在时, 仅打印一条日志并放弃注册, 不影响其他提取器
        /// </summary>
        /// <param name="typeName">组件的短名 (Type.Name) 或全名 (Type.FullName)</param>
        /// <param name="extractor">针对该组件的提取函数 (以基类 Component 为入参, 内部自行反射读字段)</param>
        internal static void RegisterByTypeName(string typeName, Action<Component, UINodeData> extractor)
        {
            // 入参保护: 类型名为空或未提供提取函数时直接返回
            if (string.IsNullOrEmpty(typeName) || extractor == null) return;

            // 反射解析: 在所有已加载程序集中查找匹配的组件类型
            Type resolvedType = null;
            foreach (var asm in System.AppDomain.CurrentDomain.GetAssemblies())
            {
                try
                {
                    foreach (var t in asm.GetTypes())
                    {
                        if (t == null) continue;
                        // 只接受 Component 的子类, 因为后续要靠 GetComponent 按类型探测
                        if (!typeof(Component).IsAssignableFrom(t)) continue;
                        // 短名或全名任一匹配即认定命中
                        if (t.Name == typeName || t.FullName == typeName)
                        {
                            resolvedType = t;
                            break;
                        }
                    }
                }
                catch (System.Reflection.ReflectionTypeLoadException)
                {
                    // 个别程序集类型加载失败 (依赖缺失等) 属正常现象, 跳过该程序集继续查找
                }
                // 已找到目标类型, 无需再遍历其余程序集
                if (resolvedType != null) break;
            }

            // 当前工程未包含该类型: 记日志并放弃注册 (松耦合设计, 缺少项目脚本时插件仍可正常工作)
            if (resolvedType == null)
            {
                Debug.Log($"[LQATool][ComponentExtractors] 自定义组件类型 \"{typeName}\" 未在当前工程中找到, 该提取器将被忽略");
                return;
            }

            // 反射解析成功: 直接存入解析到的类型与提取函数 (提取函数已是 Component 签名, 无需再包适配层)
            _entries.Add(new ExtractorEntry
            {
                ComponentType = resolvedType,
                Extractor = extractor
            });
        }

        /// <summary>
        /// 把文本可见性判定的调试快照 (VisibilityDebug) 手动拼接成 JSON 对象片段
        /// 仅在 LQAUILayerConfig.EmitVisibilityDebug 开启时用于把判定中间量一并写入导出结果, 便于问题定位
        /// </summary>
        /// <param name="d">可见性判定过程中记录的调试数据</param>
        /// <returns>形如 {"verdict": true, "reason": "...", ...} 的 JSON 片段字符串</returns>
        private static string FormatVisibilityDebug(PixelVisibilityChecker.VisibilityDebug d)
        {
            // 统一使用不变文化格式化浮点, 避免非英语系系统把小数点渲染成 "," 破坏 JSON
            var ci = CultureInfo.InvariantCulture;
            return "{"
                + $"\"verdict\": {d.verdict.ToString().ToLower()}, "  // 最终判定: 是否可见 (bool 转小写以符合 JSON 规范)
                + $"\"reason\": \"{d.reason}\", "  // 判定原因的文字说明
                + $"\"hasId\": {d.hasId.ToString().ToLower()}, "  // 是否成功取到该文本的 ID
                + $"\"id\": {d.id}, "  // 文本对应的 ID (int)
                + $"\"aabbValid\": {d.aabbValid.ToString().ToLower()}, "  // 包围盒是否有效
                + $"\"aabb\": {{\"x\": {d.aabb.x}, \"y\": {d.aabb.y}, \"width\": {d.aabb.width}, \"height\": {d.aabb.height}}}, "  // 屏幕空间包围盒
                + $"\"maskTotal\": {d.maskTotal}, "  // 掩码内像素总数
                + $"\"diffCount\": {d.diffCount}, "  // 判定为 "露出" 的像素数
                + $"\"weakAlpha\": {d.weakAlpha}, "  // 未达 alpha 门槛的弱足迹像素数 (小字号/抗锯齿边缘)
                + $"\"coveredByOther\": {d.coveredByOther}, "  // 被其它文本覆盖的像素数
                + $"\"ratio\": {d.ratio.ToString("F3", ci)}, "  // diffCount / maskTotal 的可见比例
                + $"\"ratioThreshold\": {d.ratioThreshold.ToString("F3", ci)}, "  // 判定阈值
                + $"\"useMask\": {d.useMask.ToString().ToLower()}"  // 本次是否具备掩码判定条件
                + "}";
        }

        /// <summary>
        /// 反射读取组件的公开实例属性值 (供 TMP 等未直接引用类型使用)
        /// 属性不存在 / 类型不匹配 / getter 抛错时返回 false
        /// </summary>
        private static bool TryGetProp<T>(Component comp, string propName, out T value)
        {
            value = default;
            if (comp == null) return false;
            var p = comp.GetType().GetProperty(propName,
                System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance);
            if (p == null) return false;
            try
            {
                object raw = p.GetValue(comp, null);
                if (raw is T tv) { value = tv; return true; }
                if (raw == null && !typeof(T).IsValueType) return true;
            }
            catch { }
            return false;
        }

        /// <summary>
        /// 通用记录一个图形组件 (Image / RawImage) 的几何与可见性, 写入节点 ObjectData
        /// 只做通用记录: 把 RectTransform 的 4 个世界角点逐点投影到屏幕像素后原样写出,
        /// 顺序即 GetWorldCorners 原生顺序 ([0]左下 [1]左上 [2]右上 [3]右下)
        /// </summary>
        /// <param name="g">图形组件 (Image 或 RawImage, 均派生自 Graphic)</param>
        /// <param name="node">当前节点数据</param>
        /// <param name="componentKey">写入的组件键名 ("Image" 或 "RawImage")</param>
        private static void ExtractGraphicImage(Graphic g, UINodeData node, string componentKey)
        {
            // 非 RectTransform (理论上 UGUI 图形不会出现) 则无从取角点, 跳过
            var rt = g.transform as RectTransform;
            if (rt == null) return;

            // 标记本节点含图片, 使其进入 ui_data_text.json 的剪枝树
            node.hasImage = true;

            // 世界->屏幕: Overlay 画布不依赖相机 (传 null), 其它模式用画布相机
            Canvas c = g.canvas;
            Camera cam = (c != null && c.renderMode != RenderMode.ScreenSpaceOverlay) ? c.worldCamera : null;

            // 4 个世界角点原样投影到屏幕像素并记录 (顺序: 左下→左上→右上→右下)
            Vector3[] world = new Vector3[4];
            rt.GetWorldCorners(world);
            Vector2 p0 = RectTransformUtility.WorldToScreenPoint(cam, world[0]);
            Vector2 p1 = RectTransformUtility.WorldToScreenPoint(cam, world[1]);
            Vector2 p2 = RectTransformUtility.WorldToScreenPoint(cam, world[2]);
            Vector2 p3 = RectTransformUtility.WorldToScreenPoint(cam, world[3]);
            string corners = "[" + FormatScreenPoint(p0.x, p0.y) + ", " + FormatScreenPoint(p1.x, p1.y)
                           + ", " + FormatScreenPoint(p2.x, p2.y) + ", " + FormatScreenPoint(p3.x, p3.y) + "]";
            node.AddComponentProperty(componentKey, "corners", corners);

            // 通用可见性: 组件启用 + 节点在层级中激活 + 非全透明 (图片无 Full/NoText 像素差分)
            bool visible = g.enabled && g.gameObject.activeInHierarchy && g.color.a > 0.04f;
            node.AddComponentProperty(componentKey, "isVisuallyVisible", visible.ToString().ToLower());
        }

        /// <summary>
        /// 屏幕点格式化为 JSON 片段 {"x":.., "y":..} (取整为像素)
        /// </summary>
        private static string FormatScreenPoint(float x, float y)
            => "{\"x\": " + Mathf.RoundToInt(x) + ", \"y\": " + Mathf.RoundToInt(y) + "}";

        // ==========================================
        // 所有组件提取器在此注册
        // ==========================================

        /// <summary>
        /// 集中注册所有通用 Unity 组件的提取器
        /// 每个 Register 调用对应一种组件类型, lambda 内部把该组件关心的属性写入 node.ObjectData
        /// </summary>
        private static void RegisterAllExtractors()
        {
            // ==========================================
            // Canvas 组件: UI 渲染的根组件, 导出其排序与像素对齐相关属性
            // ==========================================

            Register<Canvas>((canvasComp, node) =>
            {
                // 是否开启像素对齐 (影响 UI 清晰度)
                node.AddComponentProperty("Canvas", "pixelPerfect", canvasComp.pixelPerfect.ToString().ToLower());
                // 渲染排序值, 数值越大越靠前显示
                node.AddComponentProperty("Canvas", "sortingOrder", canvasComp.sortingOrder.ToString());
                // 是否为根 Canvas (嵌套 Canvas 时区分层级)
                node.AddComponentProperty("Canvas", "isRootCanvas", canvasComp.isRootCanvas.ToString().ToLower());
                // 是否覆盖父级排序 (子 Canvas 独立排序时为 true)
                node.AddComponentProperty("Canvas", "overrideSorting", canvasComp.overrideSorting.ToString().ToLower());
                // 排序层名称 (字符串, 需转义并加引号以构成合法 JSON 值)
                node.AddComponentProperty("Canvas", "sortingLayerName", $"\"{JsonBuilder.EscapeJson(canvasComp.sortingLayerName)}\"");
            });

            // ==========================================
            // CanvasScaler 组件: 控制 UI 随分辨率缩放的策略, 导出其缩放模式与参考分辨率
            // ==========================================

            Register<CanvasScaler>((scalerComp, node) =>
            {
                // UI 缩放模式 (枚举: ConstantPixelSize / ScaleWithScreenSize / ConstantPhysicalSize)
                node.AddComponentProperty("CanvasScaler", "uiScaleMode", $"\"{scalerComp.uiScaleMode}\"");
                // 参考每单位像素数 (浮点, 用不变文化格式化)
                node.AddComponentProperty("CanvasScaler", "referencePixelsPerUnit", scalerComp.referencePixelsPerUnit.ToString("F3", CultureInfo.InvariantCulture));
                // 参考分辨率 (设计分辨率, Vector2)
                node.AddComponentProperty("CanvasScaler", "referenceResolution", JsonBuilder.FormatVector2(scalerComp.referenceResolution));
                // 屏幕匹配模式 (决定按宽/高/折中缩放)
                node.AddComponentProperty("CanvasScaler", "screenMatchMode", $"\"{scalerComp.screenMatchMode}\"");
                // 宽高匹配权重: 0 完全匹配宽, 1 完全匹配高
                node.AddComponentProperty("CanvasScaler", "matchWidthOrHeight", scalerComp.matchWidthOrHeight.ToString("F3", CultureInfo.InvariantCulture));
            });

            // ==========================================
            // Text 组件: 旧版 UGUI 文本组件, 是 LQA 关注的核心, 导出文本内容 + 字体 + 段落 + 颜色等完整视觉参数
            // ==========================================

            Register<Text>((textComp, node) =>
            {
                // 标记本节点含文本, 使其进入 ui_data_text.json 的剪枝树
                node.hasText = true;

                // 从可见性缓存读取该文本是否在屏幕上真正可见 (被遮挡/裁剪则为 false)
                // 缓存中无记录时保守按不可见处理
                bool isVisuallyVisible;
                if (!PixelVisibilityChecker.TryGetCached(textComp.transform, out isVisuallyVisible))
                {
                    isVisuallyVisible = false;
                }
                node.AddComponentProperty("Text", "isVisuallyVisible", isVisuallyVisible.ToString().ToLower());

                // 调试开关开启时, 额外导出可见性判定的中间量快照, 便于定位误判
                if (LQAUILayerConfig.EmitVisibilityDebug)
                {
                    PixelVisibilityChecker.VisibilityDebug vdbg;
                    if (PixelVisibilityChecker.TryGetDebug(textComp.transform, out vdbg))
                    {
                        node.AddComponentProperty("Text", "visibilityDebug", FormatVisibilityDebug(vdbg));
                    }
                }

                // 文本实际内容: 复用 JsonBuilder.EscapeJson 做完整转义, 保证 JSON 合法
                node.AddComponentProperty("Text", "textContent", $"\"{JsonBuilder.EscapeJson(textComp.text)}\"");

                // ==========================================
                // Character 分组的属性
                // ==========================================

                // 字体资源引用 (输出 name/assetPath/guid 等资源引用 JSON)
                node.AddComponentProperty("Text", "font", AssetRefHelper.FormatAssetRef(textComp.font));
                // 字体样式 (枚举: Normal / Bold / Italic / BoldAndItalic)
                node.AddComponentProperty("Text", "fontStyle", $"\"{textComp.fontStyle}\"");
                // 字号
                node.AddComponentProperty("Text", "fontSize", textComp.fontSize.ToString());
                // 行间距 (浮点, 用不变文化格式化)
                node.AddComponentProperty("Text", "lineSpacing", textComp.lineSpacing.ToString("F2", System.Globalization.CultureInfo.InvariantCulture));
                // 是否支持富文本标签解析
                node.AddComponentProperty("Text", "richText", textComp.supportRichText.ToString().ToLower());

                // ==========================================
                // Paragraph 分组的属性
                // ==========================================

                // 对齐方式 (枚举: 左/中/右 + 上/中/下 组合)
                node.AddComponentProperty("Text", "alignment", $"\"{textComp.alignment}\"");
                // 水平溢出处理 (Wrap 换行 / Overflow 溢出)
                node.AddComponentProperty("Text", "horizontalOverflow", $"\"{textComp.horizontalOverflow}\"");
                // 垂直溢出处理 (Truncate 截断 / Overflow 溢出)
                node.AddComponentProperty("Text", "verticalOverflow", $"\"{textComp.verticalOverflow}\"");
                // 是否自动缩放字号以适应文本框
                node.AddComponentProperty("Text", "bestFit", textComp.resizeTextForBestFit.ToString().ToLower());
                // bestFit 开启时的最小/最大字号
                node.AddComponentProperty("Text", "minSize", textComp.resizeTextMinSize.ToString());
                node.AddComponentProperty("Text", "maxSize", textComp.resizeTextMaxSize.ToString());

                // ==========================================
                // Graphic 基类的属性
                // ==========================================

                // 文本颜色 (RGBA, 输出 {"r":..,"g":..,"b":..,"a":..})
                node.AddComponentProperty("Text", "color", JsonBuilder.FormatColor(textComp.color));
                // 是否作为射线检测目标 (影响点击/触摸事件)
                node.AddComponentProperty("Text", "raycastTarget", textComp.raycastTarget.ToString().ToLower());
            });

            // ==========================================
            // TMP 组件: TextMeshProUGUI (可选依赖), 用独立 "TMP" 键忠实导出其视觉参数
            // 不直接引用 TMPro 程序集, 通过类型名 + 反射注册, 未安装 TMP 的工程会被静默跳过
            // ==========================================

            RegisterByTypeName("TMPro.TextMeshProUGUI", (comp, node) =>
            {
                const string K = "TMP";

                // 标记本节点含文本, 使其进入 ui_data_text.json 的剪枝树
                node.hasText = true;

                // 可见性: 与 Text 一致, 走同一套像素判定缓存 (缓存未命中保守判为不可见)
                bool vis;
                if (!PixelVisibilityChecker.TryGetCached(comp.transform, out vis)) vis = false;
                node.AddComponentProperty(K, "isVisuallyVisible", vis.ToString().ToLower());

                if (LQAUILayerConfig.EmitVisibilityDebug &&
                    PixelVisibilityChecker.TryGetDebug(comp.transform, out var vdbg))
                {
                    node.AddComponentProperty(K, "visibilityDebug", FormatVisibilityDebug(vdbg));
                }

                var ci = CultureInfo.InvariantCulture;

                // 文本内容
                if (TryGetProp<string>(comp, "text", out var s))
                    node.AddComponentProperty(K, "textContent", $"\"{JsonBuilder.EscapeJson(s ?? string.Empty)}\"");

                // 字号 (TMP 为 float)
                if (TryGetProp<float>(comp, "fontSize", out var fsz))
                    node.AddComponentProperty(K, "fontSize", fsz.ToString("F2", ci));

                // 颜色
                if (TryGetProp<Color>(comp, "color", out var col))
                    node.AddComponentProperty(K, "color", JsonBuilder.FormatColor(col));

                // 对齐 / 字体样式 / 溢出 (均为 TMP 专有枚举, 用基类 Enum 接住按名导出)
                if (TryGetProp<Enum>(comp, "alignment", out var align))
                    node.AddComponentProperty(K, "alignment", $"\"{align}\"");
                if (TryGetProp<Enum>(comp, "fontStyle", out var fstyle))
                    node.AddComponentProperty(K, "fontStyle", $"\"{fstyle}\"");
                if (TryGetProp<Enum>(comp, "overflowMode", out var of))
                    node.AddComponentProperty(K, "overflowMode", $"\"{of}\"");

                // 富文本
                if (TryGetProp<bool>(comp, "richText", out var rich))
                    node.AddComponentProperty(K, "richText", rich.ToString().ToLower());

                // 自动缩放
                if (TryGetProp<bool>(comp, "enableAutoSizing", out var auto))
                    node.AddComponentProperty(K, "enableAutoSizing", auto.ToString().ToLower());
                if (TryGetProp<float>(comp, "fontSizeMin", out var fmin))
                    node.AddComponentProperty(K, "fontSizeMin", fmin.ToString("F2", ci));
                if (TryGetProp<float>(comp, "fontSizeMax", out var fmax))
                    node.AddComponentProperty(K, "fontSizeMax", fmax.ToString("F2", ci));

                // 字距 / 词距 / 行距 / 段距
                if (TryGetProp<float>(comp, "characterSpacing", out var cspace))
                    node.AddComponentProperty(K, "characterSpacing", cspace.ToString("F2", ci));
                if (TryGetProp<float>(comp, "wordSpacing", out var wspace))
                    node.AddComponentProperty(K, "wordSpacing", wspace.ToString("F2", ci));
                if (TryGetProp<float>(comp, "lineSpacing", out var lspace))
                    node.AddComponentProperty(K, "lineSpacing", lspace.ToString("F2", ci));
                if (TryGetProp<float>(comp, "paragraphSpacing", out var pspace))
                    node.AddComponentProperty(K, "paragraphSpacing", pspace.ToString("F2", ci));

                // raycastTarget (Graphic 基类, TMP 也有)
                if (TryGetProp<bool>(comp, "raycastTarget", out var ray))
                    node.AddComponentProperty(K, "raycastTarget", ray.ToString().ToLower());

                // 字体资源 (TMP_FontAsset), 仅记录引用信息 (name/assetPath/guid)
                if (TryGetProp<UnityEngine.Object>(comp, "font", out var fontAsset))
                    node.AddComponentProperty(K, "font", AssetRefHelper.FormatAssetRef(fontAsset));
            });

            // ==========================================
            // Image 组件: UGUI 图片, 记录屏幕角点 corners 与可见性 isVisuallyVisible
            // 写入全量树, 并因标记 hasImage 一并保留进文本/图片剪枝树 (ui_data_text.json)
            // 还原侧从加载的节点树读取这些框, 导出到 rect_locations 的 image 组
            // ==========================================
            Register<Image>((imgComp, node) => ExtractGraphicImage(imgComp, node, "Image"));

            // ==========================================
            // RawImage 组件: 与 Image 同处理, 用独立 "RawImage" 键
            // ==========================================
            Register<RawImage>((rawComp, node) => ExtractGraphicImage(rawComp, node, "RawImage"));
        }
    }
}