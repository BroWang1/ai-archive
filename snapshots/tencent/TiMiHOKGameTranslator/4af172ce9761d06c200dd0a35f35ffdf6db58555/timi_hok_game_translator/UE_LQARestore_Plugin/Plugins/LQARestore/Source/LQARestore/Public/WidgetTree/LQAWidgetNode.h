#pragma once

#include "Templates/SharedPointer.h"

// 前向声明, 减少头文件依赖, 加快编译速度
class SWidget;   // Slate 控件基类
class UObject;   // UE 对象基类
// struct FArrangedWidget;  // 已排布的控件 (含几何信息), 此处用注释保留说明

/**
 * 命名空间: 存放各类 “控件类型名” 常量 (FName)
 * 这些名字对应 Slate 控件运行时的类型名 (如 "STextBlock"),
 * 用于在 LQA 处理流程中识别控件类型
 */
namespace LQAWidgetNames
{
// —— 控件类型名常量 (extern 声明, 定义在 .cpp 中) ——
extern const FName LQA_TextBlock;                // 普通文本块
extern const FName LQA_RichTextBlock;            // 富文本块
extern const FName LQA_EditableText;             // 单行可编辑文本
extern const FName LQA_EditableTextBox;          // 单行可编辑文本框
extern const FName LQA_MultilineEditableText;    // 多行可编辑文本
extern const FName LQA_MultilineEditableTextBox; // 多行可编辑文本框
extern const FName LQA_ComboBox;                 // 下拉框
extern const FName LQA_LEDRichTextBlock;         // 项目自定义的 LED 富文本块
extern const FName LQA_Image;                    // 图片控件
extern const FName LQA_Button;                   // 按钮
extern const FName LQA_UserWidget;               // 用户控件 (UMG 包装的 SObjectWidget)
extern const FName LQA_Canvas;                   // 画布容器
extern const FName LQA_RetainerBox;              // 渲染缓存容器
extern const FName LQA_ScrollBox;                // 滚动容器
extern const FName LQA_VerticalBox;              // 垂直布局容器
extern const FName LQA_HorizontalBox;            // 水平布局容器
extern const FName LQA_ScaleBox;                 // 缩放容器
extern const FName LQA_SafeZone;                 // 安全区容器 (适配刘海屏等)
extern const FName LQA_WrapBox;                  // 自动换行容器
extern const FName LQA_SizeBox;                  // 固定尺寸容器
extern const FName LQA_CheckBox;                 // 复选框
extern const FName LQA_GridPanel;                // 网格面板
extern const FName LQA_UniformGridPanel;         // 等分网格面板
extern const FName LQA_Overlay;                  // 层叠容器
extern const FName LQA_Border;                   // 边框容器
extern const FName LQA_BackgroundBlur;           // 背景模糊容器
extern const FName LQA_WidgetSwitcher;           // 控件切换器
extern const FName LQA_StackBox;                 // 堆叠盒 (垂直/水平堆叠布局)
extern const FName LQA_ProgressBar;              // 进度条
extern const FName LQA_Throbber;                 // 加载指示器
extern const FName LQA_CircularThrobber;         // 环形加载指示器
extern const FName LQA_Slider;                   // 滑动条
extern const FName LQA_SpinBox;                  // 数值输入框
extern const FName LQA_Spacer;                   // 空白占位
extern const FName LQA_ScrollBar;                // 滚动条
extern const FName LQA_InputKeySelector;         // 按键选择器
extern const FName LQA_MenuAnchor;               // 菜单锚点
extern const FName LQA_InvalidationBox;          // 失效缓存容器 (性能优化)
extern const FName LQA_PostBufferUpdate;         // 后处理缓冲更新控件 (无视觉表现)
extern const FName LQA_ListView;                 // 列表视图
extern const FName LQA_TileView;                 // 平铺视图
extern const FName LQA_TreeView;                 // 树形视图
extern const FName LQA_WindowTitleBarArea;       // 窗口标题栏区域
extern const FName LQA_ExpandableArea;           // 可展开/折叠区域
}  // namespace LQAWidgetNames

/**
 * 命名空间: 存放 UMG 实际控件类型标识 (FName)
 * --------------------------------------------------------------------
 * 部分 UMG 控件的 Slate 根类型是复用的 (例如 UDynamicEntryBox 依 EntryBoxType
 * 分别以 SHorizontalBox / SVerticalBox / SWrapBox 作为 Slate 根), 仅凭 WidgetType
 * (Slate 运行时类型名) 无法区分其真实 UMG 类型。
 * 采集侧对这些控件会通过 JSON 的 "WidgetClass" 字段输出该标识,
 * 还原侧据此还原出正确的布局语义。
 */
namespace LQAWidgetClassNames
{
extern const FName LQA_DynamicEntryBox;          // 动态条目框 (UDynamicEntryBox)
}  // namespace LQAWidgetClassNames

/**
 * 命名空间: 存放各类 “插槽类型名” 常量 (FName)
 * 插槽（Slot）描述子控件在父容器中的布局方式,
 * 用于在 LQA 处理流程中识别布局插槽类型
 */
namespace LQASlotNames
{
// —— 插槽类型名常量 (extern 声明, 定义在 .cpp 中) ——
extern const FName LQA_ButtonSlot;        // 按钮插槽
extern const FName LQA_CanvasPanelSlot;   // 画布插槽 (支持锚点/绝对定位)
extern const FName LQA_ScrollBoxSlot;     // 滚动容器插槽
extern const FName LQA_VerticalBoxSlot;   // 垂直布局插槽
extern const FName LQA_HorizontalBoxSlot; // 水平布局插槽
extern const FName LQA_ScaleBoxSlot;      // 缩放容器插槽
extern const FName LQA_SafeZoneSlot;      // 安全区插槽
extern const FName LQA_WrapBoxSlot;       // 换行容器插槽
extern const FName LQA_SizeBoxSlot;       // 固定尺寸插槽
extern const FName LQA_GridSlot;          // 网格插槽
extern const FName LQA_UniformGridSlot;   // 等分网格插槽
extern const FName LQA_OverlaySlot;       // 层叠插槽
extern const FName LQA_BorderSlot;        // 边框插槽
extern const FName LQA_WidgetSwitcherSlot;// 控件切换器插槽
extern const FName LQA_StackBoxSlot;      // 堆叠盒插槽
extern const FName LQA_WindowTitleBarAreaSlot; // 窗口标题栏区域插槽
}  // namespace LQASlotNames

/**
 * 枚举: LQA 支持的控件类型
 * 将各种 UI 控件归类, 便于 LQA 流程按类型做差异化处理
 * 底层类型为 uint8, 以节省内存
 */
enum class ELQAWidgetType : uint8
{
	// —— 文本类控件 ——
	LQA_TextBlock,                 // 普通文本块
	LQA_RichText,                  // 富文本
	LQA_EditableText,              // 单行可编辑文本
	LQA_EditableTextBox,           // 单行可编辑文本框
	LQA_MultilineEditableText,     // 多行可编辑文本
	LQA_MultilineEditableTextBox,  // 多行可编辑文本框
	LQA_ComboBoxStringText,        // 下拉框文本
	LQA_LEDRichText,               // LED 富文本

	// —— 可视化类控件 ——
	LQA_Image,     // 图片
	LQA_Button,    // 按钮
	LQA_CheckBox,  // 复选框
	LQA_ProgressBar,       // 进度条
	LQA_Slider,            // 滑动条
	LQA_SpinBox,           // 数值输入框
	LQA_Throbber,          // 加载指示器
	LQA_CircularThrobber,  // 环形加载指示器
	LQA_Spacer,            // 空白占位

	// —— 容器类控件 ——
	LQA_UserWidget,        // 用户控件
	LQA_Canvas,            // 画布
	LQA_RetainerBox,       // 渲染缓存容器
	LQA_ScrollBox,         // 滚动容器
	LQA_VerticalBox,       // 垂直布局容器
	LQA_HorizontalBox,     // 水平布局容器
	LQA_ScaleBox,          // 缩放容器
	LQA_SafeZone,          // 安全区容器
	LQA_WrapBox,           // 换行容器
	LQA_SizeBox,           // 固定尺寸容器
	LQA_GridPanel,         // 网格面板
	LQA_UniformGridPanel,  // 等分网格面板
	LQA_Overlay,           // 层叠容器
	LQA_Border,            // 边框容器
	LQA_BackgroundBlur,    // 背景模糊容器
	LQA_WidgetSwitcher,    // 控件切换器
	LQA_StackBox,          // 堆叠盒
	LQA_WindowTitleBarArea,// 窗口标题栏区域
	LQA_ScrollBar,         // 滚动条
	LQA_InputKeySelector,  // 按键选择器
	LQA_MenuAnchor,        // 菜单锚点
	LQA_InvalidationBox,   // 失效缓存容器
	LQA_PostBufferUpdate,  // 后处理缓冲更新控件 (无视觉表现)
	LQA_ListView,          // 列表视图
	LQA_TileView,          // 平铺视图
	LQA_TreeView,          // 树形视图
	LQA_ExpandableArea,    // 可展开/折叠区域

	// 项目自定义控件类型可在此处扩展

	// 未定义 / 未知控件类型 (兜底值)
	LQA_Undefined
};

/**
 * 枚举: LQA 支持的插槽类型
 * 将各种布局插槽归类, 便于 LQA 流程做布局相关处理
 * 底层类型为 uint8, 以节省内存
 */
enum class ELQASlotType : uint8
{
	// —— 标准插槽 ——
	LQA_ButtonSlot,        // 按钮插槽
	LQA_CanvasPanelSlot,   // 画布插槽
	LQA_ScrollBoxSlot,     // 滚动容器插槽
	LQA_VerticalBoxSlot,   // 垂直布局插槽
	LQA_HorizontalBoxSlot, // 水平布局插槽
	LQA_ScaleBoxSlot,      // 缩放容器插槽
	LQA_SafeZoneSlot,      // 安全区插槽
	LQA_WrapBoxSlot,       // 换行容器插槽
	LQA_SizeBoxSlot,       // 固定尺寸插槽
	LQA_GridSlot,          // 网格插槽
	LQA_UniformGridSlot,   // 等分网格插槽
	LQA_OverlaySlot,       // 层叠插槽
	LQA_BorderSlot,        // 边框插槽
	LQA_WidgetSwitcherSlot,// 控件切换器插槽
	LQA_StackBoxSlot,      // 堆叠盒插槽
	LQA_WindowTitleBarAreaSlot, // 窗口标题栏区域插槽


	// 项目自定义插槽类型可在此处扩展

	// 未定义 / 未知插槽类型 (兜底值)
	LQA_UndefinedSlot
};

/**
 * 控件节点数据模型
 * 以树形层级结构描述一个 UI 控件, 供 LQA 分析使用
 * 每个节点对应一个已排布的 Slate 控件, 并记录其来源 UObject
 */
class FLQAWidgetNode
{
public:
	/**
	 * 构造函数
	 * @param InWidgetGeometry 已排布的控件 (包含控件引用与几何信息)
	 * explicit 禁止隐式转换, 避免 FArrangedWidget 被意外当作构造参数
	 */
	explicit FLQAWidgetNode(const FArrangedWidget& InWidgetGeometry);

private:
	/**
	 * 处理控件: 检测控件类型并提取元数据
	 * @param InWidget 需要处理的 Slate 控件
	 */
	void HandleWidget(const TSharedRef<SWidget>& InWidget);

	/**
	 * 将控件类型名转换为 LQA 控件类型枚举
	 * @param WidgetTypeName 控件类型名 (如 "STextBlock")
	 * @return 对应的 ELQAWidgetType 枚举值; 未匹配时返回 LQA_Undefined
	 * static: 不依赖实例状态, 可作为工具函数直接调用
	 */
	static ELQAWidgetType GetWidgetType(const FName& WidgetTypeName);

public:
	/** 对创建该控件的 UObject 的弱引用 (不影响其生命周期, 避免循环引用) */
	TWeakObjectPtr<UObject> SourceObject;
};