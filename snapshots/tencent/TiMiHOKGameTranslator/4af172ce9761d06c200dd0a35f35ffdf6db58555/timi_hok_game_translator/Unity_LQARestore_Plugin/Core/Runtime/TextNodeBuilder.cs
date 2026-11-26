// ==========================================
// 文件: LQARestore\Core\Runtime\TextNodeBuilder.cs
// 模块: Core (核心层)
// ==========================================

using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using UnityEngine.UI;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 文本节点构建器: 把 Dump 导出的 UI 节点字典 (Dictionary) 还原为运行时的 GameObject 树
    /// 职责:
    ///   - 递归遍历 Dump JSON 反序列化后的节点字典, 为每个节点重建 GameObject 及其组件;
    ///   - 只关心通用文本还原链路 (Canvas / CanvasScaler / RectTransform / Text);
    ///   - 项目专属组件 (如 XxxxText 特效) 的附加还原委托给 NodePostProcessors 注册表, 本类不感知;
    ///     唯一例外: 本地化 keyHash 因需参与 "最终文本" 的译文解析, 内联读取于 BuildTextNode
    ///     (见该处 "[项目专属]" 注释); 迁移到其它项目时只改那一处的键名即可;
    ///   - 依据 "有效可见性" 剪枝, 不可见的文本节点连同整棵子树一起跳过重建;
    /// 设计要点:
    ///   - 还原是 "把 UI 平铺到截图之上" 的 2D 合成场景, 没有原始 UI 相机, 故 Canvas 统一退化为 Overlay;
    ///   - 字体加载委托给 IFontResolver, 兼容真机 (Android) 采集时缺少 AssetDatabase 的场景;
    ///   - 有效可见性判定: 节点根层若有人工显示标记 manualShow (由 LQATextShowWindow 写入) 则以其为准,
    ///     否则回退采集侧的像素可见性 isVisuallyVisible; 判为不可见即跳过重建 (不生成该节点及其子树);
    ///   - activeSelf=false 的节点先建后禁用: 关闭动作延迟到整棵树构建完成后统一执行,
    ///     避免在父节点尚未激活时子节点无法继续挂载
    /// </summary>
    public class TextNodeBuilder
    {
        /// <summary>
        /// 字体解析器: 按 Dump 中记录的字体引用 (assetPath / guid / name) 在工程内定位 Font 资源
        /// </summary>
        private readonly IFontResolver _fontResolver;

        /// <summary>
        /// 延迟禁用动作队列: 收集所有 activeSelf=false 节点的 SetActive(false) 调用,
        /// 待整棵树构建完毕后由调用方统一回放, 保证禁用不影响子节点的挂载过程
        /// </summary>
        private readonly List<Action> _pendingDeactivations;

        /// <summary>
        /// 可选回调: 每还原出一个 "含 Text 组件" 的节点时被调用一次, 传入该节点 GameObject 与其最终文本
        /// 供外部 (如导出文本框 rect_locations)旁挂收集, 不影响还原本身; 为 null 时不触发
        /// </summary>
        private readonly Action<GameObject, string> _onTextBuilt;

        /// <summary>
        /// 可选翻译解析委托: 入参 (keyHash, textContent), 返回最终文本; 为 null 时表示不翻译, 直接用 textContent
        /// </summary>
        private readonly Func<string, string, string> _translationResolver;

        /// <summary>
        /// 构造函数
        /// </summary>
        /// <param name="fontResolver">字体解析器, 可为 null (为 null 时一律回退到内置字体)</param>
        /// <param name="pendingDeactivations">外部持有的延迟禁用队列, 本类只往里追加, 由调用方负责回放</param>
        /// <param name="onTextBuilt">可选: 每建出一个含 Text 的节点时回调(GameObject, 最终文本), 用于旁挂收集</param>
        /// <param name="translationResolver">可选: 翻译解析委托 (keyHash, textContent) → 最终文本; 为 null 时用原文</param>
        public TextNodeBuilder(IFontResolver fontResolver, List<Action> pendingDeactivations,
                               Action<GameObject, string> onTextBuilt = null,
                               Func<string, string, string> translationResolver = null)
        {
            _fontResolver = fontResolver;
            _pendingDeactivations = pendingDeactivations;
            _onTextBuilt = onTextBuilt;
            _translationResolver = translationResolver;
        }

        /// <summary>
        /// 递归构建单个文本节点: 依据节点字典重建 GameObject, 挂载并还原相关组件, 再向下处理子节点
        /// </summary>
        /// <param name="nodeDict">当前节点的字典数据 (含 name / ObjectData / ChildNodes)</param>
        /// <param name="parent">父节点 Transform, 根节点传入时可为 null</param>
        public void BuildTextNode(Dictionary<string, object> nodeDict, Transform parent)
        {
            string name       = nodeDict.Get<string>("name") ?? "Unnamed";
            var    objectData = nodeDict.Get<Dictionary<string, object>>("ObjectData") ?? new Dictionary<string, object>();

            // 可见性过滤 (有效可见性判定):
            //   - 节点根层若存在 manualShow (人工显示标记, 由 LQATextShowWindow 写入), 以它为准;
            //   - 否则回退到采集侧的 isVisuallyVisible (像素差分判定, 缺省保守判为可见);
            //   不可见时连同整个子树一起跳过重建, 避免被隐藏/被遮挡的文本叠加到画面上
            // 文本属性块: 旧版 Text 走 "Text" 键, TMP 走 "TMP" 键
            var textProps = objectData.Get<Dictionary<string, object>>("Text");
            var tmpProps  = objectData.Get<Dictionary<string, object>>("TMP");
            var anyTextProps = textProps ?? tmpProps;
            if (anyTextProps != null)
            {
                bool effectiveVisible = nodeDict.ContainsKey("manualShow")
                    ? nodeDict.GetInnerBool("manualShow", true)
                    : anyTextProps.GetInnerBool("isVisuallyVisible", true);
                if (!effectiveVisible) return;
            }

            GameObject go;
            // 该节点是否为一个 Canvas 节点, 决定挂载的组件集合
            bool hasCanvas = objectData.ContainsKey("Canvas");

            // 统一带 RectTransform 创建 (UI 节点默认使用 RectTransform 而非普通 Transform)
            go = new GameObject(name, typeof(RectTransform));
            if (parent != null) go.transform.SetParent(parent, false);

            if (hasCanvas)
            {
                // Canvas 节点: 补齐 Canvas / CanvasScaler / GraphicRaycaster 三件套后还原属性
                var canvas = go.AddComponent<Canvas>();
                var scaler = go.AddComponent<CanvasScaler>();
                go.AddComponent<GraphicRaycaster>();
                ApplyCanvas(canvas, scaler, objectData);
            }
            else
            {
                // 只有文本节点 (Text / TMP) 需要 CanvasRenderer
                if (objectData.ContainsKey("Text") || objectData.ContainsKey("TMP"))
                    go.AddComponent<CanvasRenderer>();
            }

            // 还原 RectTransform 定位
            if (go.TryGetComponent<RectTransform>(out var rt))
                ApplyRect(rt, objectData);

            // ==========================================
            // [项目专属] 本地化组件 keyHash 提取 —— 迁移到其它项目时改这一处
            // ==========================================
            // 键名 "XxxxLocalize" / "keyHash" 是当前项目 (Xxxx 系列) 本地化组件的专属约定,
            //   由采集侧 ProjectCustomExtractors 写入 JSON, 语义为该文本对应的本地化 key 哈希
            // 为何破例内联在核心层 (本类其余项目专属还原均已解耦到 NodePostProcessors / ProjectCustomRestorers):
            //   keyHash 需参与 "最终显示文本" 的译文解析 (见下方 _translationResolver 调用), 而文本内容必须在
            //   通用 Text/TMP 还原的当下就确定; 后处理器在文本还原之后才执行, 无法回改已写入的文本,
            //   因此这处 keyHash 读取只能就地内联, 这是本类唯一感知项目专属键名的地方
            // 迁移指引: 换到其它项目时, 若本地化组件的键名/字段不同 —— 只需改下面这一行的
            //   "XxxxLocalize" / "keyHash"; 若目标项目没有本地化组件 —— 让 keyHash 取到空串即可
            //   (translationResolver 会自动退化为仅按 original 匹配)
            //   翻译匹配规则本身 (keyHash 优先, 回退 original) 封装在 TranslationTable, 与本处无关
            string keyHash = objectData.Get<Dictionary<string, object>>("XxxxLocalize").GetInnerString("keyHash");

            // 通用 Text 还原
            if (objectData.TryGetValue("Text", out var txtObj) && txtObj is Dictionary<string, object> txtProps)
            {
                // 无翻译表时 finalText 即原始 textContent (行为与原来一致); 有则按 keyHash/original 规则解析
                string original = txtProps.Get<string>("textContent") ?? "";
                string finalText = _translationResolver != null ? _translationResolver(keyHash, original) : original;
                ApplyText(go, txtProps, finalText);
                // 旁挂回调: 通知外部 "这里还原出了一个可见文本节点" (供收集屏幕框导出 rect_locations)
                if (_onTextBuilt != null) _onTextBuilt(go, finalText);
            }
            else if (objectData.TryGetValue("TMP", out var tmpObj) && tmpObj is Dictionary<string, object> tmpTextProps)
            {
                string original = tmpTextProps.Get<string>("textContent") ?? "";
                string finalText = _translationResolver != null ? _translationResolver(keyHash, original) : original;
                ApplyTmp(go, tmpTextProps, finalText);
                // TMP 键同样含 textContent, rect_locations 导出可正常收集其文本框
                if (_onTextBuilt != null) _onTextBuilt(go, finalText);
            }

            // 项目专属组件后处理 (如 XxxxText 描边/阴影), 通过注册表注入, 核心不感知具体类型
            NodePostProcessors.ApplyAll(go, objectData);

            // 处理 activeSelf: 需要禁用的节点不立即关闭, 而是登记到延迟队列,
            // 避免父节点提前禁用导致后续子节点无法正常挂载
            var goProps = objectData.Get<Dictionary<string, object>>("GameObject");
            if (goProps != null && !goProps.GetInnerBool("activeSelf", true))
            {
                var capturedGo = go;
                _pendingDeactivations.Add(() =>
                {
                    if (capturedGo != null) capturedGo.SetActive(false);
                });
            }

            // 递归子节点
            var children = nodeDict.Get<List<object>>("ChildNodes");
            if (children != null)
            {
                foreach (var c in children)
                {
                    if (c is Dictionary<string, object> cd)
                        BuildTextNode(cd, go.transform);
                }
            }
        }

        /// <summary>
        /// 还原 Text 组件: 文本内容、字号、颜色、对齐、溢出、富文本、字体
        /// (项目专属特效如 XxxxText 描边/阴影不在此处理, 见 NodePostProcessors)
        /// </summary>
        /// <param name="go">目标 GameObject, Text 组件将挂载在其上</param>
        /// <param name="txtProps">Text 组件的属性字典</param>
        /// <param name="overrideText">最终显示文本 (已按翻译规则解析)</param>
        private void ApplyText(GameObject go, Dictionary<string, object> txtProps, string overrideText)
        {
            var txt = go.AddComponent<Text>();

            txt.text = overrideText ?? "";
            txt.fontSize = txtProps.GetInnerInt("fontSize", 14);

            // Line Spacing: 行间距倍率, 影响多行文本的行高, 不还原时多行文本行距会偏离原始效果
            txt.lineSpacing = txtProps.GetInnerFloat("lineSpacing", 1f);

            var color = txtProps.Get<Dictionary<string, object>>("color");
            if (color != null) txt.color = ReadColor(color);

            // 枚举型属性: 用 Enum.TryParse 从字符串还原, 解析失败则保持组件默认值
            if (Enum.TryParse<TextAnchor>(txtProps.GetInnerString("alignment"), out var al))
                txt.alignment = al;
            if (Enum.TryParse<FontStyle>(txtProps.GetInnerString("fontStyle"), out var fs))
                txt.fontStyle = fs;
            if (Enum.TryParse<HorizontalWrapMode>(txtProps.GetInnerString("horizontalOverflow"), out var hw))
                txt.horizontalOverflow = hw;
            if (Enum.TryParse<VerticalWrapMode>(txtProps.GetInnerString("verticalOverflow"), out var vw))
                txt.verticalOverflow = vw;

            // Best Fit: 自动缩放字号以适配文本框
            // 不还原会被强制按原始 fontSize 渲染, 在竖向偏紧的小框 (如角标数字框 43.5px / 字号 36)
            // 里因 verticalOverflow=Truncate 被整行截掉 → 数字完全不显示
            bool bf = txtProps.GetInnerBool("bestFit");
            txt.resizeTextForBestFit = bf;
            if (bf)
            {
                txt.resizeTextMinSize = txtProps.GetInnerInt("minSize", 10);
                txt.resizeTextMaxSize = txtProps.GetInnerInt("maxSize", txt.fontSize);
            }

            txt.supportRichText = txtProps.GetInnerBool("richText", true);
            txt.raycastTarget = txtProps.GetInnerBool("raycastTarget", true);

            // 字体加载
            // 兼容 Android 采集: 真机运行时无 AssetDatabase, dump 里 font 只有 name,
            // assetPath/guid 均为 null, 故在 assetPath 精确加载失败后按字体名在工程内反查
            var fontRef = txtProps.Get<Dictionary<string, object>>("font");
            Font font = _fontResolver != null ? _fontResolver.Resolve(fontRef) : null;
            // 逐级回退: 解析失败 → 运行时内置字体 → 旧版 Arial 内置字体, 确保文本始终可渲染
            if (font == null) font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (font == null) font = Resources.GetBuiltinResource<Font>("Arial.ttf");
            txt.font = font;
        }

        /// <summary>
        /// 还原 TMP 文本节点
        /// 策略: 还原工程安装了 TextMeshPro → 反射创建 TextMeshProUGUI 精确还原;
        ///       未安装 → 用内置 UnityEngine.UI.Text 近似 (文本/字号/颜色/富文本), 保证截图与文本框仍可产出
        /// </summary>
        private void ApplyTmp(GameObject go, Dictionary<string, object> tmpProps, string overrideText)
        {
            Type tmpType = ResolveTmpType();

            // 分支一: 工程装了 TMP, 反射还原 TextMeshProUGUI
            if (tmpType != null)
            {
                var tmp = go.AddComponent(tmpType);

                SetProp(tmp, "text", overrideText ?? "");
                SetProp(tmp, "fontSize", tmpProps.GetInnerFloat("fontSize", 36f));

                var color = tmpProps.Get<Dictionary<string, object>>("color");
                if (color != null) SetProp(tmp, "color", ReadColor(color));

                SetProp(tmp, "richText", tmpProps.GetInnerBool("richText", true));
                SetProp(tmp, "raycastTarget", tmpProps.GetInnerBool("raycastTarget", true));

                bool autoSize = tmpProps.GetInnerBool("enableAutoSizing");
                SetProp(tmp, "enableAutoSizing", autoSize);
                if (autoSize)
                {
                    SetProp(tmp, "fontSizeMin", tmpProps.GetInnerFloat("fontSizeMin", 10f));
                    SetProp(tmp, "fontSizeMax", tmpProps.GetInnerFloat("fontSizeMax", 72f));
                }

                // 枚举按名称解析后写入 (alignment / fontStyle / overflowMode)
                SetEnumProp(tmp, "alignment", tmpProps.GetInnerString("alignment"));
                SetEnumProp(tmp, "fontStyle", tmpProps.GetInnerString("fontStyle"));
                SetEnumProp(tmp, "overflowMode", tmpProps.GetInnerString("overflowMode"));

                SetProp(tmp, "characterSpacing", tmpProps.GetInnerFloat("characterSpacing", 0f));
                SetProp(tmp, "wordSpacing", tmpProps.GetInnerFloat("wordSpacing", 0f));
                SetProp(tmp, "lineSpacing", tmpProps.GetInnerFloat("lineSpacing", 0f));
                SetProp(tmp, "paragraphSpacing", tmpProps.GetInnerFloat("paragraphSpacing", 0f));

                // 字体资源不强制还原, 交由 TMP 默认字体渲染 (跨工程字体资源难以精确定位)
                return;
            }

            // 分支二: 未装 TMP, 用内置 Text 近似
            var txt = go.AddComponent<Text>();
            txt.text = overrideText ?? "";
            txt.fontSize = Mathf.RoundToInt(tmpProps.GetInnerFloat("fontSize", 36f));

            var col = tmpProps.Get<Dictionary<string, object>>("color");
            if (col != null) txt.color = ReadColor(col);

            txt.supportRichText = tmpProps.GetInnerBool("richText", true);
            txt.raycastTarget = tmpProps.GetInnerBool("raycastTarget", true);
            // TMP 默认不裁剪, 近似时统一放开溢出, 避免文字被 Truncate 掉
            txt.horizontalOverflow = HorizontalWrapMode.Overflow;
            txt.verticalOverflow = VerticalWrapMode.Overflow;

            Font font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            if (font == null) font = Resources.GetBuiltinResource<Font>("Arial.ttf");
            txt.font = font;
        }

        // TMP 类型解析缓存 (未安装 TMP 时恒为 null)
        private static Type _tmpTypeCache;
        private static bool _tmpTypeResolved;

        /// <summary>
        /// 解析 TMPro.TextMeshProUGUI 类型 (遍历已加载程序集), 未安装 TMP 时返回 null
        /// </summary>
        private static Type ResolveTmpType()
        {
            if (_tmpTypeResolved) return _tmpTypeCache;
            _tmpTypeResolved = true;
            foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
            {
                var t = asm.GetType("TMPro.TextMeshProUGUI");
                if (t != null) { _tmpTypeCache = t; break; }
            }
            return _tmpTypeCache;
        }

        /// <summary>
        /// 反射写公开实例属性 (属性不存在/只读/类型不匹配时静默跳过)
        /// </summary>
        private static void SetProp(Component comp, string propName, object value)
        {
            if (comp == null) return;
            var p = comp.GetType().GetProperty(propName, BindingFlags.Public | BindingFlags.Instance);
            if (p == null || !p.CanWrite) return;
            try { p.SetValue(comp, value, null); } catch { }
        }

        /// <summary>
        /// 反射把字符串按属性的枚举类型解析后写入 (解析失败静默跳过)
        /// </summary>
        private static void SetEnumProp(Component comp, string propName, string enumName)
        {
            if (comp == null || string.IsNullOrEmpty(enumName)) return;
            var p = comp.GetType().GetProperty(propName, BindingFlags.Public | BindingFlags.Instance);
            if (p == null || !p.CanWrite || !p.PropertyType.IsEnum) return;
            try { p.SetValue(comp, Enum.Parse(p.PropertyType, enumName), null); } catch { }
        }

        /// <summary>
        /// 还原 Canvas 与 CanvasScaler 属性
        /// 注意: 渲染模式被强制改为 ScreenSpaceOverlay (见方法内注释), 其余排序/缩放属性照常还原
        /// </summary>
        /// <param name="canvas">目标 Canvas 组件</param>
        /// <param name="scaler">目标 CanvasScaler 组件</param>
        /// <param name="data">当前节点的 ObjectData, 从中读取 Canvas / CanvasScaler 子字典</param>
        private void ApplyCanvas(Canvas canvas, CanvasScaler scaler, Dictionary<string, object> data)
        {
            var canvasProps = data.Get<Dictionary<string, object>>("Canvas");
            if (canvasProps != null)
            {
                // 还原是 "把 UI 平铺到截图之上" 的 2D 合成场景, 没有原始 UI 相机,
                // Camera/World 模式都无法正确贴屏渲染, 统一退化为 Overlay
                // sortingOrder / overrideSorting 仍照常还原, 排序行为不受影响
                canvas.renderMode = RenderMode.ScreenSpaceOverlay;

                canvas.sortingOrder = canvasProps.GetInnerInt("sortingOrder", 0);

                canvas.pixelPerfect = canvasProps.GetInnerBool("pixelPerfect");
                canvas.overrideSorting = canvasProps.GetInnerBool("overrideSorting");

                string sln = canvasProps.GetInnerString("sortingLayerName");
                if (!string.IsNullOrEmpty(sln))
                    canvas.sortingLayerName = sln;
            }

            var scalerProps = data.Get<Dictionary<string, object>>("CanvasScaler");
            if (scalerProps != null)
            {
                if (Enum.TryParse<CanvasScaler.ScaleMode>(scalerProps.GetInnerString("uiScaleMode"), out var sm))
                    scaler.uiScaleMode = sm;

                var refRes = scalerProps.Get<Dictionary<string, object>>("referenceResolution");
                if (refRes != null)
                    scaler.referenceResolution = new Vector2(
                        refRes.GetInnerFloat("x", 1920),
                        refRes.GetInnerFloat("y", 1080));

                if (Enum.TryParse<CanvasScaler.ScreenMatchMode>(scalerProps.GetInnerString("screenMatchMode"), out var smm))
                    scaler.screenMatchMode = smm;

                scaler.matchWidthOrHeight = scalerProps.GetInnerFloat("matchWidthOrHeight", 0.5f);
                scaler.referencePixelsPerUnit = scalerProps.GetInnerFloat("referencePixelsPerUnit", 100f);
            }
        }

        /// <summary>
        /// 还原 RectTransform 布局属性 (锚点/轴心/尺寸/位置) 以及 Transform 的缩放与旋转
        /// </summary>
        /// <param name="rt">目标 RectTransform 组件</param>
        /// <param name="data">当前节点的 ObjectData, 从中读取 RectTransform / Transform / Canvas 子字典</param>
        private void ApplyRect(RectTransform rt, Dictionary<string, object> data)
        {
            var rtProps = data.Get<Dictionary<string, object>>("RectTransform");
            if (rtProps != null)
            {
                var aMin = rtProps.Get<Dictionary<string, object>>("anchorMin");
                if (aMin != null) rt.anchorMin = new Vector2(aMin.GetInnerFloat("x"), aMin.GetInnerFloat("y"));

                var aMax = rtProps.Get<Dictionary<string, object>>("anchorMax");
                if (aMax != null) rt.anchorMax = new Vector2(aMax.GetInnerFloat("x"), aMax.GetInnerFloat("y"));

                var pivot = rtProps.Get<Dictionary<string, object>>("pivot");
                if (pivot != null) rt.pivot = new Vector2(pivot.GetInnerFloat("x"), pivot.GetInnerFloat("y"));

                var sizeDelta = rtProps.Get<Dictionary<string, object>>("sizeDelta");
                if (sizeDelta != null)
                    rt.sizeDelta = new Vector2(sizeDelta.GetInnerFloat("x", 100), sizeDelta.GetInnerFloat("y", 100));

                var anchoredPos = rtProps.Get<Dictionary<string, object>>("anchoredPosition");
                if (anchoredPos != null)
                    rt.anchoredPosition = new Vector2(anchoredPos.GetInnerFloat("x", 0), anchoredPos.GetInnerFloat("y", 0));
            }

            var tProps = data.Get<Dictionary<string, object>>("Transform");
            if (tProps != null)
            {
                // 仅跳过 "根 Canvas" 的 localScale (如根画布 0.029, 是配合 UI 相机距离的补偿,
                // Overlay 还原时由 Unity 重新驱动)
                // 嵌套子 Canvas (isRootCanvas=false) 的 localScale 是设计者真实设置的布局缩放,
                // 必须保留, 否则父节点施加的放大 (如 UITRCardItem 的 2.02) 得不到子画布 0.41 的回缩,
                // 整棵子树被放大 ~2.44 倍 (典型现象: 中央卡片 "赵云" 等文本明显过大)
                bool isRootCanvas = false;
                var canvasProps = data.Get<Dictionary<string, object>>("Canvas");
                if (canvasProps != null)
                    isRootCanvas = canvasProps.GetInnerBool("isRootCanvas");

                if (!isRootCanvas)
                {
                    var scale = tProps.Get<Dictionary<string, object>>("localScale");
                    if (scale != null)
                        rt.localScale = new Vector3(scale.GetInnerFloat("x", 1), scale.GetInnerFloat("y", 1), scale.GetInnerFloat("z", 1));
                }

                var euler = tProps.Get<Dictionary<string, object>>("localEulerAngles");
                if (euler != null)
                    rt.localEulerAngles = new Vector3(euler.GetInnerFloat("x"), euler.GetInnerFloat("y"), euler.GetInnerFloat("z"));
            }
        }

        /// <summary>
        /// 从颜色字典读取 Color, 缺省通道按不透明白 (r=g=b=a=1) 填充
        /// </summary>
        /// <param name="d">含 r/g/b/a 分量的字典, 为 null 时返回 Color.white</param>
        /// <returns>还原后的 Color</returns>
        private Color ReadColor(Dictionary<string, object> d)
        {
            if (d == null) return Color.white;
            return new Color(
                d.GetInnerFloat("r", 1), d.GetInnerFloat("g", 1),
                d.GetInnerFloat("b", 1), d.GetInnerFloat("a", 1));
        }
    }
}