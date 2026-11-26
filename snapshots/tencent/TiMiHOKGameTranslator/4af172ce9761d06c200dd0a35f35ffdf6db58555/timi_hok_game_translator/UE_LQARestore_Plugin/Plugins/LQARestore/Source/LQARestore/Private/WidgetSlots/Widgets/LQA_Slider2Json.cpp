#include "WidgetSlots/Widgets/LQA_Slider2Json.h"

#include "Components/Slider.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_Slider2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for Slider"));
		return nullptr;
	}

	USlider* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<USlider>(ObjectData, USlider::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<USlider>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore USlider Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_Slider2Json::GetType()
{
	return ELQAWidgetType::LQA_Slider;
}
