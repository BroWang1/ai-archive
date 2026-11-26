#include "WidgetSlots/Widgets/LQA_BackgroundBlur2Json.h"

#include "Components/BackgroundBlur.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_BackgroundBlur2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for BackgroundBlur"));
		return nullptr;
	}

	UBackgroundBlur* BackgroundBlur = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			BackgroundBlur = GetAsObject<UBackgroundBlur>(ObjectData, UBackgroundBlur::StaticClass());
		}
	}
	else
	{
		BackgroundBlur = NewObject<UBackgroundBlur>();
	}

	if (!BackgroundBlur)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore BackgroundBlur Failed!"));
		return nullptr;
	}
	return BackgroundBlur;
}
