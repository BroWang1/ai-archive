#include "WidgetSlots/Core/Slot2JsonFactory.h"

// 接口基类头文件
#include "WidgetSlots/Core/Slot2JsonInterface.h"

// 各类具体槽类型对应的 Slot2Json 实现头文件
#include "WidgetSlots/Slots/LQA_BorderSlot2Json.h"			// Border (边框) 槽
#include "WidgetSlots/Slots/LQA_ButtonSlot2Json.h"			// Button (按钮) 槽
#include "WidgetSlots/Slots/LQA_CanvasPanelSlot2Json.h"		// CanvasPanel (画布面板) 槽
#include "WidgetSlots/Slots/LQA_GridSlot2Json.h"			// Grid (网格) 槽
#include "WidgetSlots/Slots/LQA_HorizontalBoxSlot2Json.h"	// HorizontalBox (水平布局) 槽
#include "WidgetSlots/Slots/LQA_OverlaySlot2Json.h"			// Overlay (叠加) 槽
#include "WidgetSlots/Slots/LQA_SafeZoneSlot2Json.h"		// SafeZone (安全区) 槽
#include "WidgetSlots/Slots/LQA_ScaleBoxSlot2Json.h"		// ScaleBox (缩放盒) 槽
#include "WidgetSlots/Slots/LQA_ScrollBoxSlot2Json.h"		// ScrollBox (滚动盒) 槽
#include "WidgetSlots/Slots/LQA_SizeBoxSlot2Json.h"			// SizeBox (尺寸盒) 槽
#include "WidgetSlots/Slots/LQA_UniformGridSlot2Json.h"		// UniformGrid (均匀网格) 槽
#include "WidgetSlots/Slots/LQA_VerticalBoxSlot2Json.h"		// VerticalBox (垂直布局) 槽
#include "WidgetSlots/Slots/LQA_WidgetSwitcherSlot2Json.h"	// WidgetSwitcher (控件切换器) 槽
#include "WidgetSlots/Slots/LQA_StackBoxSlot2Json.h"			// StackBox (堆叠盒) 槽
#include "WidgetSlots/Slots/LQA_WindowTitleBarAreaSlot2Json.h" // WindowTitleBarArea (窗口标题栏区域) 槽
#include "WidgetSlots/Slots/LQA_WrapBoxSlot2Json.h"			// WrapBox (自动换行盒) 槽

// 控件树节点定义
#include "WidgetTree/LQAWidgetNode.h"

// 根据 JSON 中的槽类型 (SlotType) 创建对应的 Slot2Json 接口实例
TSharedPtr<FSlot2JsonInterface> FSlot2JsonFactory::MakeSlotData(const TSharedPtr<FJsonObject> JsonData)
{
	// 校验: JSON 必须同时包含 "SlotType" (槽类型) 和 "Slot" (槽数据) 两个字段, 否则无法处理
	if (!JsonData->HasField(TEXT("SlotType")) || !JsonData->HasField(TEXT("Slot")))
	{
		return nullptr;
	}

	// 读取槽类型字符串
	FString SlotType = JsonData->GetStringField(TEXT("SlotType"));

	// UE 的类名通常以 "U" 为前缀 (如 UCanvasPanelSlot), 这里去掉首字母 "U",
	// 以便与下方不带前缀的类型名 (如 "CanvasPanelSlot") 进行匹配
	if (SlotType.StartsWith(TEXT("U")))
	{
		SlotType = SlotType.RightChop(1);
	}

	// 转换为 FName, 便于高效比较
	const FName SlotTypeName = FName(*SlotType);

	// 依次匹配各已知槽类型, 命中后创建对应的 Slot2Json 实现并以共享指针返回

	if (SlotTypeName == FName(TEXT("BorderSlot")))
	{
		return MakeShareable(new FLQA_BorderSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("ButtonSlot")))
	{
		return MakeShareable(new FLQA_ButtonSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("CanvasPanelSlot")))
	{
		return MakeShareable(new FLQA_CanvasPanelSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("GridSlot")))
	{
		return MakeShareable(new FLQA_GridSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("HorizontalBoxSlot")))
	{
		return MakeShareable(new FLQA_HorizontalBoxSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("OverlaySlot")))
	{
		return MakeShareable(new FLQA_OverlaySlot2Json());
	}
	if (SlotTypeName == FName(TEXT("SafeZoneSlot")))
	{
		return MakeShareable(new FLQA_SafeZoneSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("ScaleBoxSlot")))
	{
		return MakeShareable(new FLQA_ScaleBoxSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("ScrollBoxSlot")))
	{
		return MakeShareable(new FLQA_ScrollBoxSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("SizeBoxSlot")))
	{
		return MakeShareable(new FLQA_SizeBoxSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("UniformGridSlot")))
	{
		return MakeShareable(new FLQA_UniformGridSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("VerticalBoxSlot")))
	{
		return MakeShareable(new FLQA_VerticalBoxSlot2Json());
	}
	if (SlotTypeName == FName(TEXT("WrapBoxSlot")))
	{
		return MakeShareable(new FLQA_WrapBoxSlot2Json());
	}
	if (SlotTypeName == LQASlotNames::LQA_WidgetSwitcherSlot)
	{
		return MakeShareable(new FLQA_WidgetSwitcherSlot2Json());
	}
	if (SlotTypeName == LQASlotNames::LQA_StackBoxSlot)
	{
		return MakeShareable(new FLQA_StackBoxSlot2Json());
	}
	if (SlotTypeName == LQASlotNames::LQA_WindowTitleBarAreaSlot)
	{
		return MakeShareable(new FLQA_WindowTitleBarAreaSlot2Json());
	}

	// 未匹配到任何已知槽类型: 记录警告日志并返回空指针
	UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Unknown SlotTypeName: %s"), *SlotType);
	return nullptr;
}

// 从 JSON 数据还原面板槽 (Panel Slot)
bool FSlot2JsonFactory::SlotFromJson(const TSharedPtr<FJsonObject>& SlotJsonObj, UPanelSlot* PanelSlot)
{
	// 先根据槽类型创建对应的接口实例
	const TSharedPtr<FSlot2JsonInterface> Interface = MakeSlotData(SlotJsonObj);
	if (Interface.IsValid())
	{
		// 接口有效时, 取出 "Slot" 子对象, 调用 FromJson 将其中的属性还原到目标 PanelSlot 上
		return Interface->FromJson(SlotJsonObj->GetObjectField(TEXT("Slot")), PanelSlot);
	}

	// 未能创建有效接口 (槽类型未知或 JSON 缺少必要字段), 还原失败
	return false;
}