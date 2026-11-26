#include "WidgetSlots/Widgets/LQA_DynamicEntryBox2Json.h"

#include "Components/HorizontalBox.h"
#include "Components/Overlay.h"
#include "Components/VerticalBox.h"
#include "Components/WrapBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

// UDynamicEntryBoxBase::EntryBoxType 字段名, 决定动态条目采用何种布局容器
static const FString EntryBoxTypeKey = TEXT("EntryBoxType");

UWidget* FLQA_DynamicEntryBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for DynamicEntryBox"));
		return nullptr;
	}

	// 取 ObjectData (UDynamicEntryBox 的属性集合)
	TSharedPtr<FJsonObject> ObjectData;
	if (JsonData->HasField(CommonObjectKey))
	{
		ObjectData = JsonData->GetObjectField(CommonObjectKey);
	}

	// —— 判定布局方式 ——
	// 优先取 ObjectData.EntryBoxType; 缺失时从 WidgetType (Slate 根类型名) 反推,
	// 二者皆无则按水平布局兜底。
	FString LayoutType;
	if (ObjectData.IsValid())
	{
		ObjectData->TryGetStringField(EntryBoxTypeKey, LayoutType);
	}
	if (LayoutType.IsEmpty() && JsonData->HasField(TEXT("WidgetType")))
	{
		const FString SlateRootType = JsonData->GetStringField(TEXT("WidgetType"));
		if (SlateRootType == TEXT("SVerticalBox"))
		{
			LayoutType = TEXT("Vertical");
		}
		else if (SlateRootType == TEXT("SWrapBox"))
		{
			LayoutType = TEXT("Wrap");
		}
		else if (SlateRootType == TEXT("SOverlay"))
		{
			LayoutType = TEXT("Overlay");
		}
		else
		{
			LayoutType = TEXT("Horizontal");
		}
	}
	if (LayoutType.IsEmpty())
	{
		LayoutType = TEXT("Horizontal");
	}

	// —— 按布局方式降级还原为等价的 UPanelWidget 容器 ——
	// Radial (SRadialBox) 还原端暂无对应实现, 与 Horizontal 一并按水平布局降级。
	UWidget* RestoredWidget = nullptr;
	if (ObjectData.IsValid())
	{
		if (LayoutType == TEXT("Vertical"))
		{
			RestoredWidget = GetAsObject<UVerticalBox>(ObjectData, UVerticalBox::StaticClass());
		}
		else if (LayoutType == TEXT("Wrap") || LayoutType == TEXT("VerticalWrap"))
		{
			RestoredWidget = GetAsObject<UWrapBox>(ObjectData, UWrapBox::StaticClass());
		}
		else if (LayoutType == TEXT("Overlay"))
		{
			RestoredWidget = GetAsObject<UOverlay>(ObjectData, UOverlay::StaticClass());
		}
		else
		{
			RestoredWidget = GetAsObject<UHorizontalBox>(ObjectData, UHorizontalBox::StaticClass());
		}
	}

	// ObjectData 缺失或反序列化失败: 按布局方式兜底创建对应的空容器
	if (!RestoredWidget)
	{
		if (LayoutType == TEXT("Vertical"))
		{
			RestoredWidget = NewObject<UVerticalBox>();
		}
		else if (LayoutType == TEXT("Wrap") || LayoutType == TEXT("VerticalWrap"))
		{
			RestoredWidget = NewObject<UWrapBox>();
		}
		else if (LayoutType == TEXT("Overlay"))
		{
			RestoredWidget = NewObject<UOverlay>();
		}
		else
		{
			RestoredWidget = NewObject<UHorizontalBox>();
		}
	}

	if (!RestoredWidget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UDynamicEntryBox Failed!"));
		return nullptr;
	}

	UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("DynamicEntryBox restored as '%s' (EntryBoxType=%s)"),
		*RestoredWidget->GetClass()->GetName(), *LayoutType);
	return RestoredWidget;
}
