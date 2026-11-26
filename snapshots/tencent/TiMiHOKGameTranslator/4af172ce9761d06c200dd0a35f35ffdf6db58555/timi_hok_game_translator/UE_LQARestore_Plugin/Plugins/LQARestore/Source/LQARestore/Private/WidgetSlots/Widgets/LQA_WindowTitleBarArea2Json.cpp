#include "WidgetSlots/Widgets/LQA_WindowTitleBarArea2Json.h"

#include "Components/WindowTitleBarArea.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_WindowTitleBarArea2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for WindowTitleBarArea"));
		return nullptr;
	}

	UWindowTitleBarArea* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UWindowTitleBarArea>(ObjectData, UWindowTitleBarArea::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UWindowTitleBarArea>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UWindowTitleBarArea Failed!"));
		return nullptr;
	}
	return Widget;
}
