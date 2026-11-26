// ==========================================
// 文件: LQARestore\Core\Runtime\RestoreEngine.cs
// 模块: Core (核心层)
// ==========================================

using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 还原引擎 (核心层): 把采集工具 (LQATool) 产出的 dump 数据 "反向重建" 成 Unity 场景中的可视画面
    /// 职责: 读取一份 dump 的 JSON 描述文件, 依次完成:
    ///   1. 解析 JSON 根对象, 取出原始屏幕分辨率等元信息
    ///   2. 新建一个干净的还原场景, 并把 GameView 分辨率对齐到原始画面
    ///   3. 铺上 "无文本截图" 作为背景画布 (ScreenShot_NoText.png)
    ///   4. 委托 TextNodeBuilder 递归重建 dump 里记录的文本节点树
    ///   5. 处理延迟失活 (activeSelf=false) 的节点, 标记场景为脏, 最终截图输出 Restore.png
    /// 设计要点: 引擎本身不直接依赖 Unity 编辑器/平台 API, 而是通过 IFontResolver (字体解析)
    ///           与 ISceneHost (场景/截图宿主) 两个接口与外界交互, 从而与运行环境解耦,
    ///           便于在 Editor / 未来 Runtime 等不同环境下替换实现
    /// </summary>
    public class RestoreEngine
    {
        // ==========================================
        // 依赖注入 (私有只读字段) —— 由构造函数传入, 供还原流程调用
        // ==========================================

        /// <summary>
        /// 字体解析器: 把 dump 里的字体引用信息 (name/assetPath/guid) 解析为可渲染的 Font
        /// 具体查找方式由实现决定 (Editor 走 AssetDatabase, 真机可另写实现)
        /// </summary>
        private readonly IFontResolver _fontResolver;

        /// <summary>
        /// 场景宿主: 封装新建场景 / 设置分辨率 / 截图 / 标记脏 等与 Unity 场景强相关的底层能力
        /// </summary>
        private readonly ISceneHost _sceneHost;

        /// <summary>
        /// 延迟失活队列: 收集 "需要 SetActive(false)" 的节点操作
        /// 为什么要延迟: 若在重建过程中立即失活某节点, 其未创建完成的子节点会受影响,
        ///   因此先原样激活地建完整棵树, 待全部子节点就位后再统一失活, 保证层级结构完整
        /// 由本引擎创建并传给 TextNodeBuilder, 双方共享同一份队列
        /// </summary>
        private readonly List<Action> _pendingDeactivations = new List<Action>();

        /// <summary>
        /// 构造还原引擎, 注入字体解析与场景宿主两个外部依赖
        /// </summary>
        /// <param name="fontResolver">字体解析器实现 (如 EditorFontResolver)</param>
        /// <param name="sceneHost">场景宿主实现 (如 EditorSceneHost)</param>
        public RestoreEngine(IFontResolver fontResolver, ISceneHost sceneHost)
        {
            _fontResolver = fontResolver;
            _sceneHost = sceneHost;
        }

        /// <summary>
        /// 还原主流程: 对应原 RestoreFromDumpFile 的还原主体 (去掉了 OpenFilePanel 选文件的交互部分)
        /// 从给定的 JSON 路径读取一份 dump, 重建文本画面并截图输出到同目录的 Restore.png
        /// 整个过程包裹在 try/catch 中: 任一步骤异常都不应让编辑器崩溃, 仅记录错误并安全退出
        /// </summary>
        /// <param name="jsonPath">
        /// dump 的 JSON 文件完整路径
        /// 其所在目录 (dumpDir) 同时也是背景图 ScreenShot_NoText.png 与输出图 Restore.png 的目录
        /// </param>
        /// <param name="translationPath">可选 i18n_translation_xx.json (示例) 路径; 为空则用 dump 原文还原</param>
        /// <param name="fontVariantTemplate">可选字体变体模板 (含 {name}), 如 "{name}@th"; 为空则字体按 dump 原样还原</param>
        public void RestoreFromDump(string jsonPath, string translationPath = null, string fontVariantTemplate = null)
        {
            // 入参校验: 路径为空或文件不存在, 直接静默返回 (不视为错误)
            if (string.IsNullOrEmpty(jsonPath) || !File.Exists(jsonPath)) return;

            // dump 目录: 背景图读取、结果图输出都以此为基准目录
            string dumpDir = Path.GetDirectoryName(jsonPath);

            // 清空延迟失活队列, 避免上一次还原的残留操作影响本次
            _pendingDeactivations.Clear();

            try
            {
                // 1. 读取并解析 JSON, 根节点必须是一个对象 (字典), 否则视为格式错误
                string jsonText = File.ReadAllText(jsonPath);
                var root = MiniJson.Parse(jsonText) as Dictionary<string, object>;
                if (root == null) throw new Exception("JSON 根不是对象");

                // 2. 校验 Color Space: dump 记录的颜色空间与当前项目设置不一致时,
                //    纯色块/渐变会明显偏亮或偏暗, 还原画面与原图对比会失真, 故给出告警提醒 (不中断还原)
                string dumpColorSpace = root.Get<string>("colorSpace");
                if (!string.IsNullOrEmpty(dumpColorSpace))
                {
                    string projectColorSpace = QualitySettings.activeColorSpace.ToString();
                    if (!string.Equals(dumpColorSpace, projectColorSpace, StringComparison.OrdinalIgnoreCase))
                    {
                        Debug.LogWarning(
                            $"[LQARestore][RestoreEngine] Color Space 不一致: Dump={dumpColorSpace}, " +
                            $"当前项目={projectColorSpace}; 还原画面的明暗/颜色可能与原始不符, " +
                            $"建议在 Edit > Project Settings > Player > Other Settings > Color Space 切换为 {dumpColorSpace} 后重新还原");
                    }
                }

                // 3. 新建一个干净的还原场景, 作为后续所有还原对象的承载容器
                _sceneHost.NewRestoreScene("LQA_Restore_Scene");

                // 4. 取出 dump 记录的原始屏幕分辨率 (缺省回退到 1920x1080),
                //    并把 GameView 尺寸对齐到该分辨率, 使还原预览/截图与原始画面一致
                int dumpW = Convert.ToInt32(root.Get<object>("screenWidth")  ?? 1920);
                int dumpH = Convert.ToInt32(root.Get<object>("screenHeight") ?? 1080);
                _sceneHost.SetResolution(dumpW, dumpH, "LQA_Restore");

                // 4. 铺背景: 以 "无文本截图" 作为底图画布, 文本节点稍后叠加在其之上
                CreateBackgroundCanvas(dumpDir, root);

                // 5. 递归重建文本节点树
                //    TextNodeBuilder 与本引擎共享 _pendingDeactivations 队列: 建树时先全部激活地创建,
                //    需要失活的节点被登记进队列, 待整棵树建完后再统一处理 (见下方)
                //    同时传入 onTextBuilt 回调, 旁挂收集所有还原出的可见文本节点, 供导出屏幕文本框 (rect_locations)
                // 可选: 用户在菜单选择了 i18n_translation_xx.json (示例) 时加载翻译表; 加载失败/未选 → null (原文还原)
                TranslationTable translationTable = null;
                if (!string.IsNullOrEmpty(translationPath))
                    translationTable = TranslationTable.Load(translationPath);

                // 字体解析器: 配了变体模板则用 FontVariantResolver 包一层 (按模板改写字体名, 找不到回退原字体);
                // 未配置模板则直接用原始解析器 (等于当前逻辑)
                IFontResolver fontResolver = string.IsNullOrEmpty(fontVariantTemplate)
                    ? _fontResolver
                    : new FontVariantResolver(_fontResolver, fontVariantTemplate);

                var textNodes = new List<TextRectItem>();
                var builder = new TextNodeBuilder(fontResolver, _pendingDeactivations,
                    (go, finalText) =>
                    {
                        if (go != null && go.TryGetComponent<RectTransform>(out var trt))
                            textNodes.Add(new TextRectItem
                            {
                                Rt = trt,
                                Text = finalText ?? ""
                            });
                    },
                    translationTable != null ? (Func<string, string, string>)translationTable.Resolve : null);
                var nodes = root.Get<List<object>>("nodes");
                if (nodes != null)
                {
                    // 遍历顶层节点, 逐个作为根 (parent 为 null) 递归重建
                    foreach (var n in nodes)
                        if (n is Dictionary<string, object> nodeDict)
                            builder.BuildTextNode(nodeDict, null);
                }

                // 6. 收集图片框: 对原始节点树做一次纯数据遍历, 把可见的 Image/RawImage
                //    采集角点 (corners) 原样透传, 供导出 rect_locations 的 image 组
                //    图片位置不随翻译变化, 采集侧已记录屏幕像素角点 (与文本框同坐标系: y 左下原点),
                //    故无需在还原场景重建 Image 对象, 直接透传即可
                var imageBoxes = new List<object>();
                CollectImageBoxes(nodes, imageBoxes);

                // 7. 整棵树建完后, 统一执行延迟失活操作 (还原 activeSelf=false 的节点)
                //    单个失活失败只告警不中断, 保证其余节点仍能正确处理
                foreach (var deactivate in _pendingDeactivations)
                {
                    try {
                        deactivate();
                    }
                    catch (Exception ex) {
                        Debug.LogWarning($"[LQARestore][RestoreEngine] SetActive 失败: {ex.Message}");
                    }
                }
                _pendingDeactivations.Clear();

                // 8. 标记场景为脏 (使编辑器识别到内容变化), 并打印完成日志
                _sceneHost.MarkDirty();
                Debug.Log($"[LQARestore][RestoreEngine] 文本还原完成，来源: {dumpDir}");

                // 9. 截图输出: 把还原后的画面渲染保存为 Restore.png, 便于与原始 dump 画面对比
                string outPath = Path.Combine(dumpDir, "Restore.png");
                _sceneHost.CaptureToPng(outPath, dumpW, dumpH);

                // 10. 导出检测框: 把还原出的每个可见文本节点的屏幕矩形 + 采集透传的图片框写成平台
                //    rect_locations 格式, 落到 dump 同目录的 rect_locations.json, 供 "提交还原结果" 时上传
                //    (Overlay 画布下 UI 的 world 坐标即屏幕像素坐标, 故 GetWorldCorners 得到的就是屏幕角点)
                WriteRectLocations(dumpDir, textNodes, imageBoxes, dumpH);
            }
            catch (Exception e)
            {
                // 任一环节异常: 记录完整错误与堆栈, 并清空延迟队列, 保证下一次还原从干净状态开始
                Debug.LogError($"[LQARestore][RestoreEngine] 还原失败: {e.Message}\n{e.StackTrace}");
                _pendingDeactivations.Clear();
            }
        }

        /// <summary>
        /// 创建背景画布: 把 dump 目录下的 "无文本截图" (ScreenShot_NoText.png) 作为底图铺满全屏
        /// 该底图承担 "原始画面但抠掉文本" 的角色, 还原出的文本节点会叠加在它之上, 从而复现完整画面
        /// 若文件不存在则跳过 (仅告警), 还原流程仍可继续 (只是没有背景)
        /// </summary>
        /// <param name="dumpDir">dump 所在目录, 背景图从此目录读取</param>
        /// <param name="root">dump 的 JSON 根对象, 用于读取原始分辨率作为画布参考分辨率</param>
        private void CreateBackgroundCanvas(string dumpDir, Dictionary<string, object> root)
        {
            // 背景图缺失时不作为错误处理: 打印告警并跳过, 让文本仍能还原到透明/默认背景上
            string bgPath = Path.Combine(dumpDir, "ScreenShot_NoText.png");
            if (!File.Exists(bgPath))
            {
                Debug.LogWarning("[LQARestore][RestoreEngine] 未找到 ScreenShot_NoText.png, 跳过背景");
                return;
            }

            // 从磁盘字节流加载纹理 (初始尺寸随意, LoadImage 会按图片实际尺寸自动重建)
            var tex = new Texture2D(2, 2, TextureFormat.RGBA32, false);
            tex.LoadImage(File.ReadAllBytes(bgPath));
            tex.name = "ScreenShot_NoText";

            // 背景画布: Overlay 模式直接贴屏, sortingOrder = -1 保证它位于所有文本节点之下
            var canvasGo = new GameObject("LQA_Background_Canvas");
            var canvas = canvasGo.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = -1;

            // 缩放器按原始分辨率做参考, 使背景图随 GameView 尺寸等比适配
            var scaler = canvasGo.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(
                Convert.ToInt32(root.Get<object>("screenWidth") ?? 1920),
                Convert.ToInt32(root.Get<object>("screenHeight") ?? 1080)
            );

            // 补齐 GraphicRaycaster (标准 UI 画布组成部分, 保持结构完整)
            canvasGo.AddComponent<GraphicRaycaster>();

            // 背景图节点: 用 RawImage 直接显示这张 Texture2D (无需 Sprite 转换)
            var bgGo = new GameObject("BG", typeof(RectTransform));
            bgGo.transform.SetParent(canvasGo.transform, false);
            bgGo.AddComponent<CanvasRenderer>();

            var bg = bgGo.AddComponent<RawImage>();
            bg.texture = tex;

            // 让背景图铺满整个画布: 锚点拉伸到四角 (0,0)~(1,1), 四边偏移清零
            var rt = bg.rectTransform;
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
        }

        /// <summary>
        /// 还原过程中收集的一个文本节点: 其 RectTransform 与文本内容
        /// </summary>
        private struct TextRectItem
        {
            public RectTransform Rt;
            public string Text;
        }

        /// <summary>
        /// 把收集到的文本节点屏幕矩形导出为平台 rect_locations 格式, 写到 dumpDir/rect_locations.json
        ///
        /// 平台 (image/service.py auto_review) 约定: rect_locations 是 { 组key: [ { "corners":[4个{x,y}点] }, ... ] };
        ///   corners 需按 1左下 → 2左上 → 3右上 → 4右下 逆时针顺序给出全部四点, 且 y 为 "左下原点"
        /// Unity 的 RectTransform.GetWorldCorners 在 Overlay 画布下返回屏幕像素坐标(y 向上为正, 即左下原点),
        ///   顺序为 [0]左下 [1]左上 [2]右上 [3]右下, 这里按平台约定重排为左下起逆时针
        /// </summary>
        private void WriteRectLocations(string dumpDir, List<TextRectItem> items, List<object> imageBoxes, int dumpH)
        {
            try
            {
                // 生成前强制刷新一次布局, 保证 RectTransform 的世界角点已是最终值
                Canvas.ForceUpdateCanvases();

                var boxes = new List<object>();
                var wc = new Vector3[4];
                foreach (var it in items)
                {
                    if (it.Rt == null) continue;
                    it.Rt.GetWorldCorners(wc);  // [0]左下 [1]左上 [2]右上 [3]右下 (屏幕像素, y 左下原点)
                    float xMin = Mathf.Min(wc[0].x, wc[2].x);
                    float xMax = Mathf.Max(wc[0].x, wc[2].x);
                    float yMin = Mathf.Min(wc[0].y, wc[2].y);
                    float yMax = Mathf.Max(wc[0].y, wc[2].y);

                    // 过滤零面积/异常框
                    if (xMax - xMin < 1f || yMax - yMin < 1f) continue;

                    // 平台约定: 从左下起逆时针采集全部四点, 依次 1左下 → 2左上 → 3右上 → 4右下 (左下原点)
                    var corners = new List<object>
                    {
                        MakePoint(xMin, yMin),  // 1 左下
                        MakePoint(xMin, yMax),  // 2 左上
                        MakePoint(xMax, yMax),  // 3 右上
                        MakePoint(xMax, yMin),  // 4 右下
                    };
                    boxes.Add(new Dictionary<string, object>
                    {
                        { "corners", corners },
                        { "textStr", it.Text ?? "" },
                    });
                }

                // 顶层两个分组: "text" (还原重算的文本框) 与 "image" (采集透传的图片框)
                // 平台按 dict 的 key 分组, 键名本身不参与几何计算
                // 排版: 根对象与数组多行展开, 每个框对象单行内联 (与 ui_data_all.json 风格一致)
                var sb = new System.Text.StringBuilder();
                sb.Append('{');
                AppendGroup(sb, "text", boxes, isFirst: true);
                AppendGroup(sb, "image", imageBoxes, isFirst: false);
                sb.Append("\n}");

                string outPath = Path.Combine(dumpDir, "rect_locations.json");
                File.WriteAllText(outPath, sb.ToString());
                Debug.Log($"[LQARestore][RestoreEngine] 已导出检测框: {outPath} (文本 {boxes.Count} 个, 图片 {imageBoxes.Count} 个)");
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[LQARestore][RestoreEngine] 导出 rect_locations 失败: {e.Message}");
            }
        }

        /// <summary>
        /// 构造平台角点对象 {"x":.., "y":..} (取整为像素)
        /// </summary>
        private static Dictionary<string, object> MakePoint(float x, float y)
        {
            return new Dictionary<string, object>
            {
                { "x", (double)Mathf.RoundToInt(x) },
                { "y", (double)Mathf.RoundToInt(y) },
            };
        }

        /// <summary>
        /// 递归遍历原始节点树, 收集所有 "可见" 图片 (Image / RawImage) 的采集角点
        /// 与文本重建解耦: 直接读采集写入的屏幕像素角点, 不重建 Image 对象
        /// </summary>
        private void CollectImageBoxes(List<object> nodes, List<object> outBoxes)
        {
            if (nodes == null) return;
            foreach (var n in nodes)
            {
                if (!(n is Dictionary<string, object> nodeDict)) continue;

                var objectData = nodeDict.Get<Dictionary<string, object>>("ObjectData");
                if (objectData != null)
                {
                    TryAddImageBox(objectData.Get<Dictionary<string, object>>("Image"), outBoxes);
                    TryAddImageBox(objectData.Get<Dictionary<string, object>>("RawImage"), outBoxes);
                }

                CollectImageBoxes(nodeDict.Get<List<object>>("ChildNodes"), outBoxes);
            }
        }

        /// <summary>
        /// 若图片属性存在、可见且含有效角点, 则以 { "corners": [...] } 形式加入结果
        /// corners 原样透传采集值 (采集侧已按 1左下→2左上→3右上→4右下 记录屏幕像素角点)
        /// </summary>
        private static void TryAddImageBox(Dictionary<string, object> imgProps, List<object> outBoxes)
        {
            if (imgProps == null) return;
            // 只导出可见图片 (采集侧固定写入 isVisuallyVisible, 缺省保守判为可见)
            if (!imgProps.GetInnerBool("isVisuallyVisible", true)) return;

            var corners = imgProps.Get<List<object>>("corners");
            if (corners == null || corners.Count == 0) return;

            outBoxes.Add(new Dictionary<string, object> { { "corners", corners } });
        }

        /// <summary>
        /// 把一组框以 "key": [ 单行内联对象, ... ] 形式追加到 sb
        /// isFirst=false 时先补一个逗号分隔上一组, 空组输出 "key": []
        /// </summary>
        private static void AppendGroup(System.Text.StringBuilder sb, string key, List<object> boxes, bool isFirst)
        {
            if (!isFirst) sb.Append(',');
            sb.Append("\n  \"").Append(key).Append("\": [");
            for (int i = 0; i < boxes.Count; i++)
            {
                sb.Append("\n    ").Append(JsonWriter.SerializeInline(boxes[i]));
                if (i < boxes.Count - 1) sb.Append(',');
            }
            if (boxes.Count > 0) sb.Append("\n  ");
            sb.Append(']');
        }
    }
}