// ==========================================
// 文件: LQATool\Services\UIDumpService.NodeTree.cs
// 模块: Services (业务)
// ==========================================

using System.Collections.Generic;
using System.IO;
using UnityEngine;
using LQATool.Models;
using LQATool.Utils;
using LQATool.Config;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// UIDumpService 的分部实现 (主定义见 UIDumpService.cs)
    /// 本分部聚焦 "UI 节点树采集": 遍历场景 Canvas 生成 UINodeData 树, 并落地为
    /// ui_data_all.json (全量) 与 ui_data_text.json (文本/图片剪枝树),
    /// 两者是否写盘分别受 EmitFullUIDataJson / EmitTextUIDataJson 开关控制
    /// </summary>
    public partial class UIDumpService
    {
        /// <summary>
        /// 采集环境元数据 + 遍历场景所有根 Canvas, 生成 UI 节点树 JSON 并写入磁盘
        /// 由 ExecuteDump 在截图流程末尾调用 (此时游戏时间已被冻结 timeScale=0,
        /// 保证这里读到的节点状态与前面截的图基于同一帧, 不会因动画/异步加载而漂移)
        /// </summary>
        /// <param name="toolCanvas">工具自身的 Canvas, 遍历时必须跳过, 否则会把工具面板也导出</param>
        /// <param name="dirPath">本次 Dump 的输出目录 (带时间戳), JSON 文件将写入此处</param>
        private void GenerateJsonData(Canvas toolCanvas, string dirPath)
        {
            // ==========================================
            // 采集 Dump 瞬间的环境元数据 (先取快照, 避免多次读取运行时属性)
            // 这些数据供还原工程复刻同样的屏幕/画质/语言环境, 是像素级对齐的前提
            // ==========================================

            // 屏幕分辨率快照 (像素)
            int capturedWidth = Screen.width;
            int capturedHeight = Screen.height;

            // 系统语言 (枚举转字符串, 如 "ChineseSimplified" / "English")
            string systemLanguageName = Application.systemLanguage.ToString();

            // 图层配置快照: 记录本次 Dump 时 "哪些 Layer 被单独截图" 的权威清单
            // 用 ToArray 拷贝一份, 防止后续配置变更污染这份快照, 配置为 null 时兜底为空数组
            string[] layerNamesSnapshot = LQAUILayerConfig.UILayerNames != null ? LQAUILayerConfig.UILayerNames.ToArray() : new string[0];

            // 屏幕方向 (Portrait / LandscapeLeft 等), 还原端需切到同方向, 否则 RectTransform 全部错位
            string orientationName = Screen.orientation.ToString();

            // 安全区域 (刘海屏/灵动岛下会小于屏幕尺寸)
            Rect capturedSafeArea = Screen.safeArea;

            // 画质等级: 先取当前索引, 再据索引从名称数组中取名 (做越界保护, 越界时给空串)
            int capturedQualityLevel = QualitySettings.GetQualityLevel();
            string[] qualityNames = QualitySettings.names;
            string capturedQualityName = (qualityNames != null && capturedQualityLevel >= 0 && capturedQualityLevel < qualityNames.Length) ? qualityNames[capturedQualityLevel] : string.Empty;

            // 颜色空间 (Linear / Gamma), 两端不一致时纯色块会明显偏亮或偏暗
            string capturedColorSpace = QualitySettings.activeColorSpace.ToString();

            // 目标帧率 (-1 表示未限制)
            int capturedTargetFrameRate = Application.targetFrameRate;

            // ==========================================
            // 构建 "全量版" 结果对象 resultAll, 填充上面采集的所有元数据
            // ==========================================
            UIDumpResult resultAll = new UIDumpResult
            {
                // 当前激活场景名
                sceneName = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name,
                // 游戏客户端版本号 (Player Settings → Version)
                appVersion = Application.version,
                // Unity 引擎版本号
                unityVersion = Application.unityVersion,
                // 屏幕分辨率 (像素)
                screenWidth = capturedWidth,
                screenHeight = capturedHeight,
                // 屏幕 DPI (设备物理像素密度)
                screenDpi = Screen.dpi,
                // 系统语言
                systemLanguage = systemLanguageName,
                // 当前激活的 Layer 名称
                activeLayerNames = layerNamesSnapshot,
                // 屏幕方向
                orientation = orientationName,
                // 安全区域
                safeArea = capturedSafeArea,
                // 画质等级
                qualityLevel = capturedQualityLevel,
                // 画质等级名称
                qualityLevelName = capturedQualityName,
                // 颜色空间
                colorSpace = capturedColorSpace,
                // 目标帧率
                targetFrameRate = capturedTargetFrameRate,
            };

            // ==========================================
            // 构建 "文本/图片版" 结果对象 resultText, 元数据与全量版完全一致 (直接引用 resultAll 的字段)
            // 二者的区别仅在于 nodes: resultText 只保留含文本或图片的节点树 (下面循环里剪枝得到)
            // ==========================================
            UIDumpResult resultText = new UIDumpResult
            {
                sceneName = resultAll.sceneName,
                appVersion = resultAll.appVersion,
                unityVersion = resultAll.unityVersion,
                screenWidth = resultAll.screenWidth,
                screenHeight = resultAll.screenHeight,
                screenDpi = resultAll.screenDpi,
                systemLanguage = resultAll.systemLanguage,
                activeLayerNames = resultAll.activeLayerNames,
                orientation = resultAll.orientation,
                safeArea = resultAll.safeArea,
                qualityLevel = resultAll.qualityLevel,
                qualityLevelName = resultAll.qualityLevelName,
                colorSpace = resultAll.colorSpace,
                targetFrameRate = resultAll.targetFrameRate,
            };

            // ==========================================
            // 遍历场景中所有 Canvas, 逐个构建节点树
            // ==========================================
            foreach (var canvas in UnityEngine.Object.FindObjectsOfType<Canvas>())
            {
                // 跳过工具自身的 Canvas, 避免把 LQA 工具面板导出到结果里
                if (canvas == toolCanvas) continue;

                // 只处理根 Canvas: 子 Canvas (嵌套 Canvas) 会在递归遍历父树时被自然覆盖,
                // 若这里不过滤, 子 Canvas 会被重复当成顶层节点导出
                if (!canvas.isRootCanvas) continue;

                // 从该 Canvas 的 Transform 出发, 递归构建完整节点树
                UINodeData canvasNode = BuildNodeTree(canvas.transform);

                // 全量树: 无条件收录
                resultAll.nodes.Add(canvasNode);

                // 文本/图片树: 对全量子树做剪枝, 只保留含文本或图片节点及其祖先, 整棵都没有则返回 null, 直接丢弃
                UINodeData textCanvasNode = FilterTextNodeTree(canvasNode);
                if (textCanvasNode != null) resultText.nodes.Add(textCanvasNode);
            }

            // ==========================================
            // 序列化并落盘
            // ==========================================

            // 全量 JSON: 受配置开关控制
            if (LQAUILayerConfig.EmitFullUIDataJson)
            {
                File.WriteAllText(Path.Combine(dirPath, "ui_data_all.json"), JsonBuilder.Serialize(resultAll));
            }

            // 文本/图片 JSON: 受配置开关控制
            if (LQAUILayerConfig.EmitTextUIDataJson)
            {
                File.WriteAllText(Path.Combine(dirPath, "ui_data_text.json"), JsonBuilder.Serialize(resultText));
            }
        }

        /// <summary>
        /// 递归遍历一个 Transform 及其所有子孙, 构建成 UINodeData 树
        /// 每个节点会附带 GameObject / Transform / RectTransform 的基础属性, 以及由
        /// ComponentExtractors 提取的各类 UI 组件属性 (Text / Image / Canvas 等)
        /// </summary>
        /// <param name="t">当前要处理的 Transform</param>
        /// <returns>构建完成的节点 (含其所有子孙节点)</returns>
        private UINodeData BuildNodeTree(Transform t)
        {
            // 创建节点并填充 3 项标识信息
            UINodeData node = new UINodeData
            {
                // GameObject 名称
                name = t.gameObject.name,
                // 在 Hierarchy 中的完整路径 (如 "Canvas/Panel/Button"), 便于人工定位
                path = UIHelper.GetGameObjectPath(t.gameObject),
                // 主要组件类型 (让外部解析工具知道这是什么控件, 如 Text/Image/Button)
                objectType = UIHelper.GetPrimaryComponentType(t.gameObject)
            };

            // ==========================================
            // GameObject 层级属性 (bool 统一转小写字符串 "true"/"false", 契合 JSON 布尔写法)
            // ==========================================

            // 自身激活状态 (Inspector 顶部勾选框)
            node.AddComponentProperty("GameObject", "activeSelf", t.gameObject.activeSelf.ToString().ToLower());

            // ==========================================
            // Transform 层级属性 (局部坐标系, 均格式化为 {x,y,z} 的 JSON 对象)
            // ==========================================

            // 局部欧拉角 (旋转)
            node.AddComponentProperty("Transform", "localEulerAngles", JsonBuilder.FormatVector3(t.localEulerAngles));
            // 局部缩放
            node.AddComponentProperty("Transform", "localScale", JsonBuilder.FormatVector3(t.localScale));

            // ==========================================
            // RectTransform 属性: 仅当该 Transform 实际是 RectTransform (即 UI 元素) 时才采集
            // 用模式匹配 (t is RectTransform rt) 一次完成类型判断 + 转换
            // ==========================================

            if (t is RectTransform rt)
            {
                // 锚点坐标 (2D)
                node.AddComponentProperty("RectTransform", "anchoredPosition", JsonBuilder.FormatVector2(rt.anchoredPosition));
                // 相对锚点的尺寸增量
                node.AddComponentProperty("RectTransform", "sizeDelta", JsonBuilder.FormatVector2(rt.sizeDelta));
                // 锚点最小/最大 (0~1 归一化, 描述拉伸模式)
                node.AddComponentProperty("RectTransform", "anchorMin", JsonBuilder.FormatVector2(rt.anchorMin));
                node.AddComponentProperty("RectTransform", "anchorMax", JsonBuilder.FormatVector2(rt.anchorMax));
                // 轴心 (0~1, 决定旋转/缩放的中心点)
                node.AddComponentProperty("RectTransform", "pivot", JsonBuilder.FormatVector2(rt.pivot));
                // 计算后的实际矩形宽高 (只取 width/height, 复用 Vector2 格式化), 还原时不读, 但是保留以供人工排查溢出/截断
                node.AddComponentProperty("RectTransform", "rect", JsonBuilder.FormatVector2(new Vector2(rt.rect.width, rt.rect.height)));
            }

            // 交给组件提取器统一提取所有已注册的 UI 组件属性 (Text / Image / Canvas / 项目自定义组件等)
            // 提取结果同样写入 node.ObjectData
            ComponentExtractors.ExtractAll(t, node);

            // ==========================================
            // 递归处理子节点: 先缓存 childCount, 循环中把每个子节点的序号 i 与总数一并传入
            // ==========================================
            int childCount = t.childCount;
            for (int i = 0; i < childCount; i++)
            {
                node.ChildNodes.Add(BuildNodeTree(t.GetChild(i)));
            }

            return node;
        }

        /// <summary>
        /// 对全量节点树做 "树状剪枝", 生成只含文本或图片的精简树
        /// 保留规则: 一个节点会被保留, 当且仅当它自身含文本或图片 (hasText、hasImage), 或它有任意子孙含文本或图片
        ///           (从而保证含文本或图片节点的整条祖先路径都被保留, 树结构不断裂)
        /// 采用后序递归: 先处理子节点, 再据 "自身有文本/图片 or 有保留下来的子节点" 决定当前节点去留
        /// </summary>
        /// <param name="originalNode">全量树中的原始节点</param>
        /// <returns>
        /// 剪枝后的新节点 (深拷贝)
        /// 若该子树完全不含文本或图片则返回 null
        /// </returns>
        private UINodeData FilterTextNodeTree(UINodeData originalNode)
        {
            // 先递归剪枝所有子节点, 收集其中真正保留下来的 (非 null) 子节点
            List<UINodeData> filteredChildren = new List<UINodeData>();
            foreach (var child in originalNode.ChildNodes)
            {
                var fc = FilterTextNodeTree(child);

                // 子节点自身及其子孙都没文本/图片时返回 null, 直接丢弃
                if (fc != null) filteredChildren.Add(fc);
            }

            // 当前节点自身有文本/图片, 或有保留下来的子节点 → 需要保留当前节点
            if (originalNode.hasText || originalNode.hasImage || filteredChildren.Count > 0)
            {
                // 深拷贝一份新节点 (不复用原对象, 避免与全量树共享引用)
                UINodeData newNode = new UINodeData
                {
                    name = originalNode.name,
                    path = originalNode.path,
                    objectType = originalNode.objectType,
                    hasText = originalNode.hasText,
                    hasImage = originalNode.hasImage,

                    // 挂上已剪枝的子节点列表
                    ChildNodes = filteredChildren
                };

                // 逐层深拷贝 ObjectData (两层字典), 保证新树与原树在属性数据上完全独立
                foreach (var compKvp in originalNode.ObjectData)
                {
                    var innerCopy = new Dictionary<string, string>();

                    foreach (var propKvp in compKvp.Value)
                    {
                        innerCopy[propKvp.Key] = propKvp.Value;
                    }

                    newNode.ObjectData[compKvp.Key] = innerCopy;
                }

                return newNode;
            }

            // 整棵子树都不含文本/图片 → 剪掉
            return null;
        }
    }
}