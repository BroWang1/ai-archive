#include "WidgetSlots/Widgets/LQA_InputKeySelector2Json.h"

#include "Components/InputKeySelector.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_InputKeySelector2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for InputKeySelector"));
		return nullptr;
	}

	UInputKeySelector* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UInputKeySelector>(ObjectData, UInputKeySelector::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UInputKeySelector>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UInputKeySelector Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_InputKeySelector2Json::GetType()
{
	return ELQAWidgetType::LQA_InputKeySelector;
}
