#include "WidgetSlots/Widgets/LQA_WidgetSwitcher2Json.h"

#include "Components/WidgetSwitcher.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_WidgetSwitcher2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for WidgetSwitcher"));
		return nullptr;
	}

	UWidgetSwitcher* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UWidgetSwitcher>(ObjectData, UWidgetSwitcher::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UWidgetSwitcher>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UWidgetSwitcher Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_WidgetSwitcher2Json::GetType()
{
	return ELQAWidgetType::LQA_WidgetSwitcher;
}
