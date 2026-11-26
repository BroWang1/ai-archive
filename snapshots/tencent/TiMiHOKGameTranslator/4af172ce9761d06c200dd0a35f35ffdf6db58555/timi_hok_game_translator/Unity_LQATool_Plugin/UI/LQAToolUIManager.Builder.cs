// ==========================================
// 文件: LQATool\UI\LQAToolUIManager.Builder.cs
// 模块: UI (用户界面)
// ==========================================

using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// LQATool 用户界面层命名空间
/// </summary>
namespace LQATool.UI
{
    /// <summary>
    /// 分部类: 与 LQAToolUIManager.cs / .Display.cs / .EventSystem.cs 共同组成同一个类
    /// 本分部专注于 "如何把 UI 画出来", 字段 (_canvas / _infoPanel 等) 在主文件中声明
    /// </summary>
    public partial class LQAToolUIManager
    {
        /// <summary>
        /// 动态构建工具所需的全部 UI 元素 (整棵 UI 树的入口)
        /// 调用时机: 由 Initialize() 调用
        /// 构建内容: 主画布 Canvas → Dump 按钮 → GetNode 按钮 → 信息面板
        /// </summary>
        private void CreateToolUI()
        {
            // 1. 创建承载所有 UI 的根节点游戏对象
            GameObject canvasObj = new GameObject("LQATool_Canvas");
            // 挂到 UIManager 所在的对象下, 保持层级整洁, 便于随管理器一起被销毁
            canvasObj.transform.SetParent(this.transform);

            // 2. 添加 Canvas 组件并缓存引用 (供 Dump 时临时隐藏工具 UI)
            _canvas = canvasObj.AddComponent<Canvas>();
            // 屏幕空间-覆盖模式: 直接叠加在屏幕最外层, 不依赖任何摄像机
            _canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            // 排序层级拉到最高 (short.MaxValue), 确保工具 UI 永远压在游戏 UI 之上
            _canvas.sortingOrder = 32767;

            // 3. 添加画布缩放器, 让 UI 在不同分辨率设备上表现一致
            CanvasScaler scaler = canvasObj.AddComponent<CanvasScaler>();
            // 按屏幕尺寸缩放
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            // 设计基准分辨率: 1920×1080
            scaler.referenceResolution = new Vector2(1920, 1080);
            // 宽高匹配权重 0.5: 宽度和高度各占一半, 兼顾横竖屏比例变化
            scaler.matchWidthOrHeight = 0.5f;

            // 4. 添加图形射线检测器: UI 元素能够接收点击/触摸事件的前提
            canvasObj.AddComponent<GraphicRaycaster>();

            // 5. 创建 Dump 按钮 (锚点左中, 位于最左侧)
            Button btnDump = CreateButton(canvasObj.transform, "Btn_Dump", "Dump", new Vector2(10, 0));
            // 绑定点击回调: 点击时向外广播 OnDumpClicked 事件 (?. 防止无人订阅时空引用)
            btnDump.onClick.AddListener(() => OnDumpClicked?.Invoke());

            // 6. 创建 GetNode 按钮 (在 Dump 按钮右侧, x=120), 初始文字为关闭状态
            Button btnGetNode = CreateButton(canvasObj.transform, "Btn_GetNode", "GetNode[off]", new Vector2(120, 0));
            // 缓存按钮上的 Text 组件, 供 ToggleGetNode() 切换文字/颜色时复用, 避免重复查找
            _txtGetNode = btnGetNode.GetComponentInChildren<Text>();
            // 绑定点击回调: 切换 GetNode 开关状态 (ToggleGetNode 定义在主文件中)
            btnGetNode.onClick.AddListener(ToggleGetNode);

            // 7. 创建长按信息展示面板 (预创建并隐藏, 需要时再显示)
            CreateInfoPanel(canvasObj.transform);
        }

        /// <summary>
        /// 通用按钮工厂方法: 用纯代码创建一个 "半透明黑底 + 居中白字" 的按钮
        /// </summary>
        /// <param name="parent">父节点 (通常是主画布)</param>
        /// <param name="name">按钮游戏对象的名称</param>
        /// <param name="text">按钮上显示的文字</param>
        /// <param name="position">相对锚点 (左中) 的偏移位置</param>
        /// <returns>创建好的 Button 组件</returns>
        private Button CreateButton(Transform parent, string name, string text, Vector2 position)
        {
            // 1. 创建按钮根对象并挂到父节点下 (worldPositionStays = false, 保持本地布局)
            GameObject btnObj = new GameObject(name);
            btnObj.transform.SetParent(parent, false);

            // 2. 添加背景图: 半透明黑色, 作为按钮的可视外观与点击热区
            Image bg = btnObj.AddComponent<Image>();
            bg.color = new Color(0, 0, 0, 0.7f);
            // 必须开启射线检测, 否则按钮无法被点击
            bg.raycastTarget = true;

            // 3. 添加 Button 组件 (点击交互逻辑)
            Button btn = btnObj.AddComponent<Button>();

            // 4. 配置按钮的 RectTransform 布局
            RectTransform rect = btnObj.GetComponent<RectTransform>();
            // 锚点固定在父容器左侧垂直居中 (0, 0.5)
            rect.anchorMin = new Vector2(0, 0.5f);
            rect.anchorMax = new Vector2(0, 0.5f);
            // 轴心也设在左中, 使 anchoredPosition 以左边缘为基准计算
            rect.pivot = new Vector2(0, 0.5f);
            // 应用传入的偏移位置
            rect.anchoredPosition = position;
            // 按钮尺寸: 宽 100 × 高 40
            rect.sizeDelta = new Vector2(100, 40);

            // 5. 创建按钮内部的文字子对象
            GameObject txtObj = new GameObject("Text");
            txtObj.transform.SetParent(btnObj.transform, false);
            Text txtComp = txtObj.AddComponent<Text>();
            txtComp.text = text;
            // 文字关闭射线检测, 让点击事件穿透到底层的按钮背景上
            txtComp.raycastTarget = false;
            // 使用统一的默认字体 (兼容不同 Unity 版本, 见 GetDefaultFont)
            txtComp.font = GetDefaultFont();
            // 文字居中显示, 白色
            txtComp.alignment = TextAnchor.MiddleCenter;
            txtComp.color = Color.white;

            // 6. 让文字铺满整个按钮 (四角锚点拉伸 + 边距归零)
            RectTransform txtRect = txtObj.GetComponent<RectTransform>();
            txtRect.anchorMin = Vector2.zero;
            txtRect.anchorMax = Vector2.one;
            txtRect.sizeDelta = Vector2.zero;

            return btn;
        }

        /// <summary>
        /// 创建长按后弹出的节点信息展示面板 (预创建, 默认隐藏)
        /// 采用 "对象池" 思想: 提前建好, 用时 SetActive(true), 避免每次长按临时 Instantiate
        /// </summary>
        /// <param name="parent">父节点 (主画布)</param>
        private void CreateInfoPanel(Transform parent)
        {
            // 1. 创建面板根对象并缓存到 _infoPanel 字段
            GameObject panelObj = new GameObject("NodeInfoPanel");
            panelObj.transform.SetParent(parent, false);
            _infoPanel = panelObj;

            // 2. 面板背景: 更深的半透明黑 (0.85), 保证白字清晰可读
            Image bg = panelObj.AddComponent<Image>();
            bg.color = new Color(0, 0, 0, 0.85f);

            // 3. 垂直布局组: 让面板内的文字按纵向自动排列, 并留出内边距
            VerticalLayoutGroup vlg = panelObj.AddComponent<VerticalLayoutGroup>();
            vlg.padding = new RectOffset(10, 10, 8, 8);  // 左右各 10, 上下各 8
            vlg.childAlignment = TextAnchor.UpperLeft;  // 子元素左上对齐
            vlg.childControlWidth = true;  // 由布局组控制子元素宽度
            vlg.childControlHeight = true;  // 由布局组控制子元素高度

            // 4. 内容自适应: 面板高度随文字内容自动撑开, 宽度保持不变
            ContentSizeFitter csf = panelObj.AddComponent<ContentSizeFitter>();
            csf.horizontalFit = ContentSizeFitter.FitMode.Unconstrained;  // 宽度不自适应 (由下方固定)
            csf.verticalFit = ContentSizeFitter.FitMode.PreferredSize;  // 高度按内容自适应

            // 5. 限定面板最大宽度为基准分辨率的一半 (960), 防止长文本横向撑得太宽
            RectTransform panelRect = panelObj.GetComponent<RectTransform>();
            RectTransform canvasRect = _canvas.GetComponent<RectTransform>();
            float maxWidth = 1920f * 0.50f;
            panelRect.sizeDelta = new Vector2(maxWidth, 0);  // 高度给 0, 交给 ContentSizeFitter 撑开

            // 6. 创建面板内的富文本组件并缓存到 _infoText 字段
            GameObject txtObj = new GameObject("InfoText");
            txtObj.transform.SetParent(panelObj.transform, false);
            _infoText = txtObj.AddComponent<Text>();
            _infoText.font = GetDefaultFont();
            _infoText.fontSize = 14;
            _infoText.color = Color.white;
            // 开启富文本, 支持 <color> 等标签对节点信息进行高亮
            _infoText.supportRichText = true;
            // 水平换行 + 垂直溢出: 文字过长时自动换行, 高度不足时向下溢出 (配合自适应撑开面板)
            _infoText.horizontalOverflow = HorizontalWrapMode.Wrap;
            _infoText.verticalOverflow = VerticalWrapMode.Overflow;
            // 文字不参与射线检测
            _infoText.raycastTarget = false;

            // 7. 初始隐藏面板, 等到用户长按触发 GetNode 时再显示
            _infoPanel.SetActive(false);
        }

        /// <summary>
        /// 获取一个可用的默认字体 (跨 Unity 版本兼容)
        /// 依次降级尝试, 保证任何版本/平台下都能拿到可渲染文字的字体
        /// </summary>
        /// <returns>可用的 Font 实例</returns>
        private Font GetDefaultFont()
        {
            // 首选: 新版 Unity 内置的 LegacyRuntime.ttf
            Font font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            // 次选: 旧版 Unity 内置的 Arial.ttf (新版已移除该内置资源)
            if (font == null) 
                font = Resources.GetBuiltinResource<Font>("Arial.ttf");

            // 兜底: 从操作系统动态创建 Arial 字体
            if (font == null) 
                font = Font.CreateDynamicFontFromOSFont("Arial", 14);

            return font;
        }
    }
}