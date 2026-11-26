#include "WidgetSlots/Widgets/LQA_PlatformPaddingBox2Json.h"

#include "Components/SafeZone.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_PlatformPaddingBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for PlatformPaddingBox"));
		return nullptr;
	}

	USafeZone* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<USafeZone>(ObjectData, USafeZone::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<USafeZone>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore USafeZone Failed!"));
		return nullptr;
	}
	return Widget;
}
