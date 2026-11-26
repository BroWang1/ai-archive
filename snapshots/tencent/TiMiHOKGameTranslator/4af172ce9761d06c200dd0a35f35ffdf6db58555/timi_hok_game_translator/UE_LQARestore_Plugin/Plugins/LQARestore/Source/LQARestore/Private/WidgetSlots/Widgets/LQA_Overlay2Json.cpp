#include "WidgetSlots/Widgets/LQA_Overlay2Json.h"

#include "Components/Overlay.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_Overlay2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for Overlay"));
		return nullptr;
	}

	UOverlay* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UOverlay>(ObjectData, UOverlay::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UOverlay>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UOverlay Failed!"));
		return nullptr;
	}
	return Widget;
}
