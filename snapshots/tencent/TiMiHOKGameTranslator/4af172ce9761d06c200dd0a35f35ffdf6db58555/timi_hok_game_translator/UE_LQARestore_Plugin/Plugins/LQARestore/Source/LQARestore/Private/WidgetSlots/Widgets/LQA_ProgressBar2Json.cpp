#include "WidgetSlots/Widgets/LQA_ProgressBar2Json.h"

#include "Components/ProgressBar.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_ProgressBar2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for ProgressBar"));
		return nullptr;
	}

	UProgressBar* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UProgressBar>(ObjectData, UProgressBar::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UProgressBar>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UProgressBar Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_ProgressBar2Json::GetType()
{
	return ELQAWidgetType::LQA_ProgressBar;
}
