#include "WidgetSlots/Widgets/LQA_SafeZone2Json.h"

#include "Components/SafeZone.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_SafeZone2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for SafeZone"));
		return nullptr;
	}

	USafeZone* SafeZone = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			SafeZone = GetAsObject<USafeZone>(ObjectData, USafeZone::StaticClass());
		}
	}
	else
	{
		SafeZone = NewObject<USafeZone>();
	}

	if (!SafeZone)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore USafeZone Failed!"));
		return nullptr;
	}
	return SafeZone;
}
