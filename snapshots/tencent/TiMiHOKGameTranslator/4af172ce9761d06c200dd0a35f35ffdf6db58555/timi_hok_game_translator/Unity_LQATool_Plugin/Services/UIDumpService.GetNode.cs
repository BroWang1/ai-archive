// ==========================================
// 文件: LQATool\Services\UIDumpService.GetNode.cs
// 模块: Services (业务)
// ==========================================

using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;
using LQATool.Models;
using LQATool.Utils;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// 使用 partial (分部类), 本文件仅承载 "查找最近文本节点" 相关成员
    /// UIDumpService 的其余功能拆分在其他文件中, 便于按职责组织代码
    /// </summary>
    public partial class UIDumpService
    {
        /// <summary>
        /// 在场景中查找距离指定屏幕坐标最近的文本节点
        /// </summary>
        /// <param name="screenPosition">目标屏幕坐标 (通常为鼠标/点击位置, 单位: 像素)</param>
        /// <param name="toolCanvas">工具自身的 Canvas, 需要排除, 避免把工具 UI 也纳入检测</param>
        /// <returns>
        /// 最近文本节点的数据 UINodeData
        /// 若场景中没有可用文本节点则返回 null
        /// </returns>
        public UINodeData FindNearestTextNode(Vector2 screenPosition, Canvas toolCanvas)
        {
            // 收集所有符合条件 (可见、含文本、在屏幕范围内) 的候选文本节点
            List<TextNodeCandidate> candidates = new List<TextNodeCandidate>();

            // 遍历场景中所有的 Canvas, 逐个 Canvas 递归收集其下的文本节点
            foreach (var canvas in UnityEngine.Object.FindObjectsOfType<Canvas>())
            {
                // 跳过工具自身的 Canvas, 避免检测到工具界面的文本
                if (canvas == toolCanvas) continue;

                // 跳过被禁用的 Canvas (不可见的界面无需检测)
                if (!canvas.enabled) continue;

                // 从该 Canvas 的根 Transform 开始递归收集文本节点
                CollectTextNodes(canvas.transform, canvas, candidates);
            }

            // 没有任何候选文本节点, 直接返回 null
            if (candidates.Count == 0) return null;

            // 记录当前找到的最小距离, 初始化为最大值以便后续比较
            float minDistance = float.MaxValue;
            // 记录当前距离最近的候选节点
            TextNodeCandidate nearest = null;

            // 遍历所有候选, 计算其屏幕中心点到目标坐标的距离, 取最近者
            foreach (var candidate in candidates)
            {
                float distance = Vector2.Distance(screenPosition, candidate.screenCenter);

                if (distance < minDistance)
                {
                    minDistance = distance;
                    nearest = candidate;
                }
            }

            // 返回最近候选的节点数据, 使用空条件运算符防止 nearest 为空时报错
            return nearest?.nodeData;
        }

        /// <summary>
        /// 文本节点候选项: 封装节点数据及其在屏幕上的中心坐标, 用于距离比较
        /// </summary>
        private class TextNodeCandidate
        {
            // 该文本节点收集到的属性数据
            public UINodeData nodeData;
            // 该文本节点在屏幕上的中心点坐标 (像素), 用于与点击位置计算距离
            public Vector2 screenCenter;
        }

        /// <summary>
        /// 递归遍历 Transform 层级, 收集满足条件的文本节点作为候选
        /// </summary>
        /// <param name="current">当前正在处理的 Transform 节点</param>
        /// <param name="rootCanvas">当前节点所属的根 Canvas (用于确定渲染相机)</param>
        /// <param name="candidates">候选列表, 收集结果写入其中</param>
        private void CollectTextNodes(Transform current, Canvas rootCanvas, List<TextNodeCandidate> candidates)
        {
            // 节点及其父级若在层级中处于非激活状态则跳过 (不可见节点不参与检测)
            if (!current.gameObject.activeInHierarchy) return;

            // 尝试把当前节点识别为文本组件 (旧版 Text 或 TMP)
            Graphic graphicComp = current.GetComponent<Graphic>();
            TextLike textLike = null;

            // 仅处理是文本 (Text/TMP) 且内容非空的节点
            if (graphicComp != null && TextLike.TryWrap(graphicComp, out textLike)
                && !string.IsNullOrEmpty(textLike.text))
            {
                // 获取 RectTransform, UI 元素依赖它来计算屏幕位置
                RectTransform rt = current.GetComponent<RectTransform>();
                if (rt != null)
                {
                    // 计算矩形中心的世界坐标
                    Vector3 worldCenter = rt.TransformPoint(rt.rect.center);

                    // 根据 Canvas 的渲染模式决定用于坐标转换的相机:
                    // ScreenSpaceOverlay 模式不需要相机, 其余模式使用 Canvas 指定的 worldCamera
                    Camera cam = null;
                    if (rootCanvas.renderMode != RenderMode.ScreenSpaceOverlay)
                    {
                        cam = rootCanvas.worldCamera;
                    }

                    // 将世界坐标转换为屏幕坐标
                    Vector2 screenPos = RectTransformUtility.WorldToScreenPoint(cam, worldCenter);

                    // 仅保留中心点落在屏幕可见范围内的文本节点
                    if (screenPos.x >= 0 && screenPos.x <= Screen.width &&
                        screenPos.y >= 0 && screenPos.y <= Screen.height)
                    {
                        // 构建节点数据: 名称、层级路径、主组件类型, 并标记含有文本
                        UINodeData nodeData = new UINodeData
                        {
                            name = current.gameObject.name,
                            path = UIHelper.GetGameObjectPath(current.gameObject),
                            objectType = UIHelper.GetPrimaryComponentType(current.gameObject),
                            hasText = true
                        };

                        // 两类文本统一写 "Text"/"textContent", 复用运行时面板 (Display) 现有读取逻辑, 免改下游
                        nodeData.AddComponentProperty("Text", "textContent", $"\"{JsonBuilder.EscapeJson(textLike.text)}\"");

                        // ==========================================
                        // 项目专属逻辑 (Project-Specific): 本地化组件的译文 Key 反射读取
                        // ==========================================

                        // 通过反射尝试读取项目自定义的本地化组件 XxxxLocalize 的 keyHash 字段
                        // 使用反射是为了在不直接引用该类型的情况下兼容不同项目/程序集
                        try
                        {
                            var projectLocalize = current.GetComponent("XxxxLocalize");
                            if (projectLocalize != null)
                            {
                                // 查找 keyHash 字段, 涵盖 public / 非 public 的实例字段
                                var field = projectLocalize.GetType().GetField("keyHash",
                                                                            System.Reflection.BindingFlags.Public |
                                                                            System.Reflection.BindingFlags.NonPublic |
                                                                            System.Reflection.BindingFlags.Instance);
                                if (field != null)
                                {
                                    var val = field.GetValue(projectLocalize);
                                    // 仅当取到非空值时记录本地化 Key, 便于 LQA 定位翻译条目
                                    if (val != null && !string.IsNullOrEmpty(val.ToString()))
                                    {
                                        nodeData.AddComponentProperty("XxxxLocalize", "keyHash", $"\"{val}\"");
                                    }
                                }
                            }
                        }
                        catch (System.Exception)
                        {
                            // 反射失败 (如无该组件/字段或跨程序集异常) 时静默忽略, 不影响主流程
                        }

                        // ==========================================
                        // 项目专属逻辑 (Project-Specific): 结束
                        // ==========================================

                        // 记录 RectTransform 的锚定位置与尺寸偏移, 便于还原布局信息
                        if (rt != null)
                        {
                            nodeData.AddComponentProperty("RectTransform", "anchoredPosition", JsonBuilder.FormatVector2(rt.anchoredPosition));
                            nodeData.AddComponentProperty("RectTransform", "sizeDelta", JsonBuilder.FormatVector2(rt.sizeDelta));
                        }

                        // 以下为旧版 Text 专有字段 (TMP 无同名枚举), 仅旧版文本时写入
                        if (!textLike.isTmp && graphicComp is Text uguiText)
                        {
                            // 记录文本的字体样式 (粗体/斜体等)
                            nodeData.AddComponentProperty("Text", "fontStyle", $"\"{uguiText.fontStyle}\"");
                            // 记录字号
                            nodeData.AddComponentProperty("Text", "fontSize", uguiText.fontSize.ToString());
                            // 记录文本对齐方式
                            nodeData.AddComponentProperty("Text", "alignment", $"\"{uguiText.alignment}\"");
                            // 记录水平溢出处理方式 (Wrap / Overflow)
                            nodeData.AddComponentProperty("Text", "horizontalOverflow", $"\"{uguiText.horizontalOverflow}\"");
                            // 记录垂直溢出处理方式 (Truncate / Overflow)
                            nodeData.AddComponentProperty("Text", "verticalOverflow", $"\"{uguiText.verticalOverflow}\"");
                        }

                        // 将该文本节点封装为候选项加入列表
                        candidates.Add(new TextNodeCandidate
                        {
                            nodeData = nodeData,
                            screenCenter = screenPos
                        });
                    }
                }
            }

            // 递归处理所有子节点, 确保整棵层级树都被遍历到
            foreach (Transform child in current)
            {
                CollectTextNodes(child, rootCanvas, candidates);
            }
        }
    }
}