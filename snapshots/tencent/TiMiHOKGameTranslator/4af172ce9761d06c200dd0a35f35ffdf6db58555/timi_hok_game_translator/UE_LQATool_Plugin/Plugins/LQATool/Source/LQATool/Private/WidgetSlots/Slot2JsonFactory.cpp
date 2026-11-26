#include "WidgetSlots/Slot2JsonFactory.h"

#include "Snapshot/LQAWidgetNode.h"
// 以下为各种具体 Slot 类型对应的序列化处理器头文件
// 每个 Slot 类型都对应 UMG 中的一种布局容器 (如 CanvasPanel、VerticalBox 等)
#include "WidgetSlots/Slot/LQA_BackgroundBlurSlot2Json.h"
#include "WidgetSlots/Slot/LQA_BorderSlot2Json.h"
#include "WidgetSlots/Slot/LQA_ButtonSlot2Json.h"
#include "WidgetSlots/Slot/LQA_CanvasPanelSlot2Json.h"
#include "WidgetSlots/Slot/LQA_GridSlot2Json.h"
#include "WidgetSlots/Slot/LQA_HorizontalBoxSlot2Json.h"
#include "WidgetSlots/Slot/LQA_OverlaySlot2Json.h"
#include "WidgetSlots/Slot/LQA_PanelSlot2Json.h"
#include "WidgetSlots/Slot/LQA_SafeZoneSlot2Json.h"
#include "WidgetSlots/Slot/LQA_ScaleBoxSlot2Json.h"
#include "WidgetSlots/Slot/LQA_ScrollBoxSlot2Json.h"
#include "WidgetSlots/Slot/LQA_SizeBoxSlot2Json.h"
#include "WidgetSlots/Slot/LQA_StackBoxSlot2Json.h"
#include "WidgetSlots/Slot/LQA_UniformGridSlot2Json.h"
#include "WidgetSlots/Slot/LQA_VerticalBoxSlot2Json.h"
#include "WidgetSlots/Slot/LQA_WidgetSwitcherSlot2Json.h"
#include "WidgetSlots/Slot/LQA_WindowTitleBarAreaSlot2Json.h"
#include "WidgetSlots/Slot2JsonInterface.h"
#include "WidgetSlots/Slot/LQA_WrapBoxSlot2Json.h"

/**
 * 根据控件节点的 Slot 类型创建对应的序列化处理器
 * 核心逻辑: 通过 switch 分发, 将枚举类型映射到具体的处理器实例
 */
TSharedPtr<FSlot2JsonInterface> FSlot2JsonFactory::MakeSlotData(const TSharedPtr<FLQAWidgetNode> WidgetNode)
{
	// 入参校验: 节点无效时打印警告并返回空指针
	if (!WidgetNode.IsValid())
	{
		UE_LOG(LogLQAToolSlot2Json, Warning, TEXT("MakeSlotData: Invalid WidgetNode passed."));
		return nullptr;
	}

	// 根据节点的 Slot 类型, 创建并返回对应的序列化处理器
	// MakeShareable: 将 new 出来的裸指针包装为 TSharedPtr, 由智能指针托管生命周期
	switch (WidgetNode->GetSlotType())
	{
		case ELQASlotType::LQA_ButtonSlot:            // 按钮槽
			return MakeShareable(new FLQA_ButtonSlot2Json());
		case ELQASlotType::LQA_CanvasPanelSlot:       // 画布面板槽 (绝对定位)
			return MakeShareable(new FLQA_CanvasPanelSlot2Json());
		case ELQASlotType::LQA_ScrollBoxSlot:         // 滚动框槽
			return MakeShareable(new FLQA_ScrollBoxSlot2Json());
		case ELQASlotType::LQA_VerticalBoxSlot:       // 垂直布局框槽
			return MakeShareable(new FLQA_VerticalBoxSlot2Json());
		case ELQASlotType::LQA_HorizontalBoxSlot:     // 水平布局框槽
			return MakeShareable(new FLQA_HorizontalBoxSlot2Json());
		case ELQASlotType::LQA_ScaleBoxSlot:          // 缩放框槽
			return MakeShareable(new FLQA_ScaleBoxSlot2Json());
		case ELQASlotType::LQA_SafeZoneSlot:          // 安全区域槽 (适配刘海屏等)
			return MakeShareable(new FLQA_SafeZoneSlot2Json());
		case ELQASlotType::LQA_WrapBoxSlot:           // 自动换行框槽
			return MakeShareable(new FLQA_WrapBoxSlot2Json());
		case ELQASlotType::LQA_SizeBoxSlot:           // 固定尺寸框槽
			return MakeShareable(new FLQA_SizeBoxSlot2Json());
		case ELQASlotType::LQA_GridSlot:              // 网格槽
			return MakeShareable(new FLQA_GridSlot2Json());
		case ELQASlotType::LQA_UniformGridSlot:       // 均匀网格槽
			return MakeShareable(new FLQA_UniformGridSlot2Json());
		case ELQASlotType::LQA_OverlaySlot:           // 叠加层槽
			return MakeShareable(new FLQA_OverlaySlot2Json());
		case ELQASlotType::LQA_BorderSlot:            // 边框槽
			return MakeShareable(new FLQA_BorderSlot2Json());
		case ELQASlotType::LQA_WidgetSwitcherSlot:    // 控件切换器槽
			return MakeShareable(new FLQA_WidgetSwitcherSlot2Json());
		case ELQASlotType::LQA_BackgroundBlurSlot:    // 背景模糊槽
			return MakeShareable(new FLQA_BackgroundBlurSlot2Json());
		case ELQASlotType::LQA_StackBoxSlot:          // 堆叠框槽
			return MakeShareable(new FLQA_StackBoxSlot2Json());
		case ELQASlotType::LQA_WindowTitleBarAreaSlot:// 窗口标题栏区域槽
			return MakeShareable(new FLQA_WindowTitleBarAreaSlot2Json());
		case ELQASlotType::LQA_PanelSlot:             // 单子容器内容槽
			return MakeShareable(new FLQA_PanelSlot2Json());
		default:
			// 未知/不支持的 Slot 类型, 不做处理
			break;
	}

	// 未匹配到任何已知类型时返回空指针
	return nullptr;
}

/**
 * 对外统一入口: 将指定控件节点的 Slot 数据序列化为 JSON 对象
 */
TSharedPtr<FJsonObject> FSlot2JsonFactory::Slot2Json(const TSharedPtr<FLQAWidgetNode>& Widget)
{
	// 创建一个空的 JSON 对象作为返回结果的容器
	TSharedPtr<FJsonObject> NewObject = MakeShared<FJsonObject>();

	// 入参校验: 节点无效时打印警告并返回空 JSON 对象 (而非 nullptr, 便于调用方直接使用)
	if (!Widget.IsValid())
	{
		UE_LOG(LogLQAToolSlot2Json, Warning, TEXT("Slot2Json: Invalid WidgetNode passed."));
		return NewObject;
	}

	// 通过工厂方法获取与该节点 Slot 类型匹配的序列化处理器
	const TSharedPtr<FSlot2JsonInterface> Interface = MakeSlotData(Widget);
	if (Interface.IsValid())
	{
		// 调用处理器的 ToJson, 将 Slot 数据写入 NewObject
		Interface->ToJson(Widget, NewObject);
	}

	// 返回最终的 JSON 对象 (即使没有匹配到处理器, 也返回空对象)
	return NewObject;
}