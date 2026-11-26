// ==========================================
// 文件: LQATool\UI\LQAToolUIManager.Display.cs
// 模块: UI (用户界面)
// ==========================================

using System.Text;
using UnityEngine;
using LQATool.Models;

/// <summary>
/// LQATool 用户界面层命名空间
/// </summary>
namespace LQATool.UI
{
    /// <summary>
    /// LQAToolUIManager 的分部类: 本片段只聚焦 "信息面板的内容填充与定位" 逻辑
    /// 其余职责 (构建 UI、事件处理等) 分散在同名的其它分部文件中
    /// </summary>
    public partial class LQAToolUIManager
    {
        /// <summary>
        /// 显示指定节点的详细信息面板
        /// 根据 nodeData 拼装富文本内容, 填充到 _infoText, 并把面板移动到点击位置附近后显示
        /// </summary>
        /// <param name="nodeData">要展示的节点数据 (通常是射线检测到的最近文本节点)</param>
        /// <param name="pointerPosition">触发点的屏幕坐标, 用于面板定位</param>
        public void ShowNodeInfo(UINodeData nodeData, Vector2 pointerPosition)
        {
            // 空节点直接返回, 避免后续解引用报空异常
            if (nodeData == null) return;

            // 使用 StringBuilder 累积多行富文本, 避免频繁字符串拼接产生的临时对象
            StringBuilder sb = new StringBuilder();

            // 标题行: 绿色加粗, 标明这是最近的文本节点
            sb.AppendLine("<color=#00FF00><b>[ Nearest Text Node ]</b></color>");
            // 分隔线, 视觉上区隔标题与正文
            sb.AppendLine("-----------------------------");
            // 名称行: 黄色显示 GameObject 名称, 灰色括号内附带主要组件类型
            sb.AppendLine($"<color=#FFFF00>Name:</color> {nodeData.name} <color=#888888>({nodeData.objectType})</color>");
            // 路径行: 青色显示节点在 Hierarchy 中的完整路径, 便于人工定位
            sb.AppendLine($"<color=#00FFFF>Path:</color> {nodeData.path}");

            // 文本内容: 从 Text 组件读取 textContent 属性 (存储为 JSON 片段)
            if (nodeData.TryGetComponentProperty("Text", "textContent", out string rawText))
            {
                // 去除 JSON 字符串两端的引号, 并把转义的内容还原为真实换行与引号, 便于阅读
                rawText = rawText.Trim('"')
                                 .Replace("\\n", "\n")
                                 .Replace("\\r", "\r")
                                 .Replace("\\t", "\t")
                                 .Replace("\\\"", "\"")
                                 .Replace("\\\\", "\\");
                // 橙色显示文本内容
                sb.AppendLine($"<color=#FF8800>Text:</color> {rawText}");
            }

            // ==========================================
            // 项目专属逻辑 (Project-Specific): 本地化组件 KeyHash 显示
            // ==========================================

            // 本地化 KeyHash: 从 XxxxLocalize 组件读取, 用于关联本地化条目
            if (nodeData.TryGetComponentProperty("XxxxLocalize", "keyHash", out string keyHash))
            {
                // 去掉 JSON 引号
                keyHash = keyHash.Trim('"');
                // 紫色显示 KeyHash
                sb.AppendLine($"<color=#DD88FF>KeyHash:</color> {keyHash}");
            }

            // ==========================================
            // 项目专属逻辑 (Project-Specific): 结束
            // ==========================================

            // 分隔线, 下方为布局与字体相关的次要属性 (统一用灰色 #AAAAAA 弱化显示)
            sb.AppendLine("-----------------------------");

            // 锚点坐标: RectTransform.anchoredPosition
            if (nodeData.TryGetComponentProperty("RectTransform", "anchoredPosition", out string anchoredPos))
                sb.AppendLine($"<color=#AAAAAA>AnchoredPosition:</color> {anchoredPos}");

            // 尺寸增量: RectTransform.sizeDelta
            if (nodeData.TryGetComponentProperty("RectTransform", "sizeDelta", out string sizeDelta))
                sb.AppendLine($"<color=#AAAAAA>SizeDelta:</color> {sizeDelta}");

            // 字体样式 (Normal / Bold / Italic 等), 去掉 JSON 引号
            if (nodeData.TryGetComponentProperty("Text", "fontStyle", out string fontStyle))
                sb.AppendLine($"<color=#AAAAAA>FontStyle:</color> {fontStyle.Trim('"')}");

            // 字号
            if (nodeData.TryGetComponentProperty("Text", "fontSize", out string fontSize))
                sb.AppendLine($"<color=#AAAAAA>FontSize:</color> {fontSize}");

            // 对齐方式, 去掉 JSON 引号
            if (nodeData.TryGetComponentProperty("Text", "alignment", out string alignment))
                sb.AppendLine($"<color=#AAAAAA>Alignment:</color> {alignment.Trim('"')}");

            // 水平溢出模式 (Wrap / Overflow), 去掉 JSON 引号
            if (nodeData.TryGetComponentProperty("Text", "horizontalOverflow", out string hOverflow))
                sb.AppendLine($"<color=#AAAAAA>HorizontalOverflow:</color> {hOverflow.Trim('"')}");

            // 垂直溢出模式 (Truncate / Overflow), 去掉 JSON 引号
            if (nodeData.TryGetComponentProperty("Text", "verticalOverflow", out string vOverflow))
                sb.AppendLine($"<color=#AAAAAA>VerticalOverflow:</color> {vOverflow.Trim('"')}");

            // 将拼装好的富文本一次性写入面板文本组件
            _infoText.text = sb.ToString();
            // 根据点击位置调整面板的锚点位置
            UpdatePanelPosition(pointerPosition);
            // 把面板置于同级节点的最后, 保证它渲染在最上层不被其它 UI 遮挡
            _infoPanel.transform.SetAsLastSibling();
            // 激活并显示面板
            _infoPanel.SetActive(true);
        }

        /// <summary>
        /// 根据点击的屏幕坐标, 把信息面板定位到点击位置附近
        /// 会依据点击点所在的屏幕象限动态调整面板 pivot, 使面板始终朝屏幕内侧展开, 避免超出边界
        /// </summary>
        /// <param name="pointerPosition">触发点的屏幕坐标</param>
        private void UpdatePanelPosition(Vector2 pointerPosition)
        {
            // 取得 Canvas 的 RectTransform, 作为屏幕坐标转本地坐标的参照矩形
            RectTransform canvasRect = _canvas.GetComponent<RectTransform>();

            // 将屏幕坐标转换为 Canvas 内的本地坐标
            // ScreenSpaceOverlay 模式下第 3 个参数传 null, 其它模式需传入 Canvas 的渲染相机
            RectTransformUtility.ScreenPointToLocalPointInRectangle(
                canvasRect,
                pointerPosition,
                _canvas.renderMode == RenderMode.ScreenSpaceOverlay ? null : _canvas.worldCamera,
                out Vector2 localPos
            );

            // 取得面板自身的 RectTransform, 用于设置 pivot 与位置
            RectTransform panelRect = _infoPanel.GetComponent<RectTransform>();
            // 依据点击点在屏幕左右半区决定水平 pivot:
            // 左半屏 pivot.x=0 (面板向右展开), 右半屏 pivot.x=1 (面板向左展开)
            float pivotX = pointerPosition.x < Screen.width / 2f ? 0f : 1f;
            // 依据点击点在屏幕上下半区决定垂直 pivot:
            // 下半屏 pivot.y=0 (面板向上展开), 上半屏 pivot.y=1 (面板向下展开)
            float pivotY = pointerPosition.y < Screen.height / 2f ? 0f : 1f;
            // 应用动态 pivot, 使面板始终朝屏幕内侧展开, 避免溢出屏幕边缘
            panelRect.pivot = new Vector2(pivotX, pivotY);
            // 把面板放到转换后的本地坐标处 (localPos 来自上面的 out 出参)
            panelRect.anchoredPosition = localPos;
        }
    }
}