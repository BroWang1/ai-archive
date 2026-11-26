#include "WidgetSlots/Widgets/LQA_CheckBox2Json.h"

#include "Components/CheckBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_CheckBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for CheckBox"));
		return nullptr;
	}

	UCheckBox* CheckBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			CheckBox = GetAsObject<UCheckBox>(ObjectData, UCheckBox::StaticClass());
		}
	}
	else
	{
		CheckBox = NewObject<UCheckBox>();
	}

	if (!CheckBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UCheckBox Failed!"));
		return nullptr;
	}
	return CheckBox;
}

ELQAWidgetType FLQA_CheckBox2Json::GetType()
{
	return ELQAWidgetType::LQA_CheckBox;
}
