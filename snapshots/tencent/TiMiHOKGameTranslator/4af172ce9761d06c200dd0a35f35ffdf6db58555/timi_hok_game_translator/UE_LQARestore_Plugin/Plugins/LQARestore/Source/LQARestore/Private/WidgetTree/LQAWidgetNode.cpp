#include "WidgetTree/LQAWidgetNode.h"

#include "LQABase.h"
#include "Layout/ArrangedWidget.h"       // FArrangedWidget: 已排布控件
#include "Types/ReflectionMetadata.h"    // FReflectionMetaData: UMG 反射元数据
#include "Widgets/SWidget.h"             // SWidget: Slate 控件基类

// 关闭编译器优化 (通常用于调试, 便于单步跟踪本文件逻辑)
LQA_DISABLE_OPTIMIZATION

// ===== 控件类型名 / 插槽类型名常量的实际定义 =====

namespace LQASlotNames
{
// —— 插槽类型名: 字符串需与运行时插槽类型名严格一致 ——
const FName LQA_ButtonSlot(TEXT("ButtonSlot"));
const FName LQA_CanvasPanelSlot(TEXT("CanvasPanelSlot"));
const FName LQA_ScrollBoxSlot(TEXT("ScrollBoxSlot"));
const FName LQA_VerticalBoxSlot(TEXT("VerticalBoxSlot"));
const FName LQA_HorizontalBoxSlot(TEXT("HorizontalBoxSlot"));
const FName LQA_ScaleBoxSlot(TEXT("ScaleBoxSlot"));
const FName LQA_SafeZoneSlot(TEXT("SafeZoneSlot"));
const FName LQA_WrapBoxSlot(TEXT("WrapBoxSlot"));
const FName LQA_SizeBoxSlot(TEXT("SizeBoxSlot"));
const FName LQA_GridSlot(TEXT("GridSlot"));
const FName LQA_UniformGridSlot(TEXT("UniformGridSlot"));
const FName LQA_OverlaySlot(TEXT("OverlaySlot"));
const FName LQA_BorderSlot(TEXT("BorderSlot"));
const FName LQA_WidgetSwitcherSlot(TEXT("WidgetSwitcherSlot"));
const FName LQA_StackBoxSlot(TEXT("StackBoxSlot"));
const FName LQA_WindowTitleBarAreaSlot(TEXT("WindowTitleBarAreaSlot"));

// 项目自定义插槽名可在此处添加
}

namespace LQAWidgetNames
{
// —— 控件类型名: 字符串为 Slate 控件的运行时类型名 (SWidget::GetType 返回值) ——
const FName LQA_TextBlock(TEXT("STextBlock"));
const FName LQA_RichTextBlock(TEXT("SRichTextBlock"));
const FName LQA_EditableText(TEXT("SEditableText"));
const FName LQA_EditableTextBox(TEXT("SEditableTextBox"));
const FName LQA_MultilineEditableText(TEXT("SMultilineEditableText"));
const FName LQA_MultilineEditableTextBox(TEXT("SMultilineEditableTextBox"));
const FName LQA_ComboBox(TEXT("SComboBox"));
const FName LQA_LEDRichTextBlock(TEXT("SLEDRichTextBlock"));  // 项目自定义控件
const FName LQA_Image(TEXT("SImage"));
const FName LQA_Button(TEXT("SButton"));
const FName LQA_UserWidget(TEXT("SObjectWidget"));  // UMG UserWidget 对应的 Slate 实现
const FName LQA_Canvas(TEXT("SConstraintCanvas"));
const FName LQA_RetainerBox(TEXT("SRetainerWidget"));
const FName LQA_ScrollBox(TEXT("SScrollBox"));
const FName LQA_VerticalBox(TEXT("SVerticalBox"));
const FName LQA_HorizontalBox(TEXT("SHorizontalBox"));
const FName LQA_ScaleBox(TEXT("SScaleBox"));
const FName LQA_SafeZone(TEXT("SSafeZone"));
const FName LQA_WrapBox(TEXT("SWrapBox"));
const FName LQA_SizeBox(TEXT("SBox"));
const FName LQA_CheckBox(TEXT("SCheckBox"));
const FName LQA_GridPanel(TEXT("SGridPanel"));
const FName LQA_UniformGridPanel(TEXT("SUniformGridPanel"));
const FName LQA_Overlay(TEXT("SOverlay"));
const FName LQA_Border(TEXT("SBorder"));
const FName LQA_BackgroundBlur(TEXT("SBackgroundBlur"));
const FName LQA_WidgetSwitcher(TEXT("SWidgetSwitcher"));
const FName LQA_StackBox(TEXT("SStackBox"));

const FName LQA_ProgressBar(TEXT("SProgressBar"));
const FName LQA_Throbber(TEXT("SThrobber"));
const FName LQA_CircularThrobber(TEXT("SCircularThrobber"));
const FName LQA_Slider(TEXT("SSlider"));
const FName LQA_SpinBox(TEXT("SSpinBox"));
const FName LQA_Spacer(TEXT("SSpacer"));

const FName LQA_ScrollBar(TEXT("SScrollBar"));
const FName LQA_InputKeySelector(TEXT("SInputKeySelector"));
const FName LQA_MenuAnchor(TEXT("SMenuAnchor"));
const FName LQA_InvalidationBox(TEXT("SInvalidationPanel"));
const FName LQA_PostBufferUpdate(TEXT("SPostBufferUpdate"));
const FName LQA_ListView(TEXT("ListViewT<ItemType>"));
const FName LQA_TileView(TEXT("TileViewT<ItemType>"));
const FName LQA_TreeView(TEXT("TreeViewT<ItemType>"));
const FName LQA_WindowTitleBarArea(TEXT("SWindowTitleBarArea"));
const FName LQA_ExpandableArea(TEXT("SExpandableArea"));

// 项目自定义控件名可在此处添加
}

namespace LQAWidgetClassNames
{
// —— UMG 实际类型标识: 字符串需与采集侧输出的 "WidgetClass" 字段值严格一致 ——
const FName LQA_DynamicEntryBox(TEXT("DynamicEntryBox"));
}

/**
 * 构造函数: 从已排布控件中取出 Slate 控件引用, 交给 HandleWidget 处理
 */
FLQAWidgetNode::FLQAWidgetNode(const FArrangedWidget& InWidgetGeometry)
{
	HandleWidget(InWidgetGeometry.Widget);
}

/**
 * 处理单个控件: 识别类型并提取来源对象
 * 处理流程:
 *   1. 获取控件运行时类型名并转换为 LQA 枚举;
 *   2. 读取 UMG 反射元数据, 无元数据则跳过 (非 UMG 生成的控件);
 *   3. 类型未识别 (LQA_Undefined) 则跳过;
 *   4. 记录元数据中的来源 UObject
 */
void FLQAWidgetNode::HandleWidget(const TSharedRef<SWidget>& InWidget)
{
	// 获取控件的运行时类型名, 并映射为 LQA 控件类型枚举
	const FName WidgetType = InWidget->GetType();
	const ELQAWidgetType WidgetNodeType = GetWidgetType(WidgetType);

	// UMG 控件会携带反射元数据, 用于反向追踪到对应的 UObject
	const TSharedPtr<FReflectionMetaData> MetaData = InWidget->GetMetaData<FReflectionMetaData>();
	if (!MetaData.IsValid())
	{
		// 没有元数据: 说明不是 UMG 蓝图生成的控件, 无法追踪来源, 直接返回
		return;
	}

	if (WidgetNodeType == ELQAWidgetType::LQA_Undefined)
	{
		// 不是 LQA 关心的控件类型, 跳过
		return;
	}

	// 记录创建该控件的来源对象 (弱引用)
	SourceObject = MetaData->SourceObject;
}

/**
 * 控件类型名 -> LQA 控件类型枚举 的映射查询
 * 使用静态局部 TMap (只初始化一次), 避免每次调用重复构建映射表
 * @return 命中则返回对应枚举, 未命中返回 LQA_Undefined
 */
ELQAWidgetType FLQAWidgetNode::GetWidgetType(const FName& WidgetTypeName)
{
	using namespace LQAWidgetNames;

	// 静态映射表: 键为控件类型名常量, 值为 LQA 枚举; 首次调用时构建并常驻
	static const TMap<FName, ELQAWidgetType> WidgetTypeMap = {
		// 文本类控件
		{LQA_TextBlock, ELQAWidgetType::LQA_TextBlock}, {LQA_RichTextBlock, ELQAWidgetType::LQA_RichText},
		{LQA_EditableText, ELQAWidgetType::LQA_EditableText},
		{LQA_EditableTextBox, ELQAWidgetType::LQA_EditableTextBox},
		{LQA_MultilineEditableText, ELQAWidgetType::LQA_MultilineEditableText},
		{LQA_MultilineEditableTextBox, ELQAWidgetType::LQA_MultilineEditableTextBox},
		{LQA_ComboBox, ELQAWidgetType::LQA_ComboBoxStringText}, {LQA_LEDRichTextBlock, ELQAWidgetType::LQA_LEDRichText},

		// 可视化类控件
		{LQA_Image, ELQAWidgetType::LQA_Image}, {LQA_Button, ELQAWidgetType::LQA_Button},
		{LQA_CheckBox, ELQAWidgetType::LQA_CheckBox},

		// 容器类控件
		{LQA_UserWidget, ELQAWidgetType::LQA_UserWidget}, {LQA_Canvas, ELQAWidgetType::LQA_Canvas},
		{LQA_RetainerBox, ELQAWidgetType::LQA_RetainerBox}, {LQA_ScrollBox, ELQAWidgetType::LQA_ScrollBox},
		{LQA_VerticalBox, ELQAWidgetType::LQA_VerticalBox}, {LQA_HorizontalBox, ELQAWidgetType::LQA_HorizontalBox},
		{LQA_ScaleBox, ELQAWidgetType::LQA_ScaleBox}, {LQA_SafeZone, ELQAWidgetType::LQA_SafeZone},
		{LQA_WrapBox, ELQAWidgetType::LQA_WrapBox}, {LQA_SizeBox, ELQAWidgetType::LQA_SizeBox},
		{LQA_GridPanel, ELQAWidgetType::LQA_GridPanel}, {LQA_UniformGridPanel, ELQAWidgetType::LQA_UniformGridPanel},
		{LQA_Overlay, ELQAWidgetType::LQA_Overlay}, {LQA_Border, ELQAWidgetType::LQA_Border},
		{LQA_BackgroundBlur, ELQAWidgetType::LQA_BackgroundBlur},
		{LQA_WidgetSwitcher, ELQAWidgetType::LQA_WidgetSwitcher},
		{LQA_StackBox, ELQAWidgetType::LQA_StackBox},
		{LQA_WindowTitleBarArea, ELQAWidgetType::LQA_WindowTitleBarArea},
		{LQA_InvalidationBox, ELQAWidgetType::LQA_InvalidationBox},
		{LQA_ExpandableArea, ELQAWidgetType::LQA_ExpandableArea},

		// 项目自定义控件映射可在此处添加
	};

	// 在映射表中查找: 命中返回对应枚举值
	if (const ELQAWidgetType* FoundType = WidgetTypeMap.Find(WidgetTypeName))
	{
		return *FoundType;
	}
	// 未命中: 返回未定义类型作为兜底
	return ELQAWidgetType::LQA_Undefined;
}

// 恢复编译器优化 (与前面的 LQA_DISABLE_OPTIMIZATION 配对)
LQA_ENABLE_OPTIMIZATION