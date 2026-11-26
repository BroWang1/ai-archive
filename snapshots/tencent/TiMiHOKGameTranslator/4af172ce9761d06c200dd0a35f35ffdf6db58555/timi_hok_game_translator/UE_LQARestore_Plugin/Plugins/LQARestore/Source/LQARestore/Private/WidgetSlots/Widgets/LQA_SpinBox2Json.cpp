#include "WidgetSlots/Widgets/LQA_SpinBox2Json.h"

#include "Components/SpinBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_SpinBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for SpinBox"));
		return nullptr;
	}

	USpinBox* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<USpinBox>(ObjectData, USpinBox::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<USpinBox>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore USpinBox Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_SpinBox2Json::GetType()
{
	return ELQAWidgetType::LQA_SpinBox;
}
