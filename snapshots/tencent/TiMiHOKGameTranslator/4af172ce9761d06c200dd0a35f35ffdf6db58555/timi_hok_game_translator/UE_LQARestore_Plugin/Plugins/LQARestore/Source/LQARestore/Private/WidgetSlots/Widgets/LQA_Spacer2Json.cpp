#include "WidgetSlots/Widgets/LQA_Spacer2Json.h"

#include "Components/Spacer.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_Spacer2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for Spacer"));
		return nullptr;
	}

	USpacer* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<USpacer>(ObjectData, USpacer::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<USpacer>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore USpacer Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_Spacer2Json::GetType()
{
	return ELQAWidgetType::LQA_Spacer;
}
