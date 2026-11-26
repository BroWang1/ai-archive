#include "WidgetSlots/Widgets/LQA_MenuAnchor2Json.h"

#include "Components/MenuAnchor.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_MenuAnchor2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for MenuAnchor"));
		return nullptr;
	}

	// 注: UMenuAnchor 的 MenuContent 依赖 UClass 引用, JSON 快照中不含该引用,
	// 此处仅还原 MenuAnchor 自身及其常规子控件 (子控件由外层框架递归挂载)
	UMenuAnchor* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UMenuAnchor>(ObjectData, UMenuAnchor::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UMenuAnchor>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UMenuAnchor Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_MenuAnchor2Json::GetType()
{
	return ELQAWidgetType::LQA_MenuAnchor;
}
