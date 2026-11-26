#include "WidgetSlots/Widgets/LQA_ScrollBar2Json.h"

#include "Components/ScrollBar.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_ScrollBar2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for ScrollBar"));
		return nullptr;
	}

	UScrollBar* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UScrollBar>(ObjectData, UScrollBar::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UScrollBar>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UScrollBar Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_ScrollBar2Json::GetType()
{
	return ELQAWidgetType::LQA_ScrollBar;
}
