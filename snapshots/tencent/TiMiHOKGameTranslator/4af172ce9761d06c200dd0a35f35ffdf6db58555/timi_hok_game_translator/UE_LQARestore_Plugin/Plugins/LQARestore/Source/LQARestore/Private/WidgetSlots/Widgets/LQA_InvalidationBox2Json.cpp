#include "WidgetSlots/Widgets/LQA_InvalidationBox2Json.h"

#include "Components/InvalidationBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_InvalidationBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for InvalidationBox"));
		return nullptr;
	}

	UInvalidationBox* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UInvalidationBox>(ObjectData, UInvalidationBox::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UInvalidationBox>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UInvalidationBox Failed!"));
		return nullptr;
	}
	return Widget;
}
