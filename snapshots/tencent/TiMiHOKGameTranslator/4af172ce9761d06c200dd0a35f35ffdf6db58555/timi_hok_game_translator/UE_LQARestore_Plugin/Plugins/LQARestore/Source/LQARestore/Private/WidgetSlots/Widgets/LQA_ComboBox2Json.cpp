#include "WidgetSlots/Widgets/LQA_ComboBox2Json.h"

#include "Components/ComboBoxString.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_ComboBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for ComboBox"));
		return nullptr;
	}

	TSharedPtr<FJsonObject> ObjectData;
	if (JsonData->HasField(CommonObjectKey))
	{
		ObjectData = JsonData->GetObjectField(CommonObjectKey);
	}

	UComboBoxString* Widget = nullptr;
	if (ObjectData.IsValid())
	{
		Widget = GetAsObject<UComboBoxString>(ObjectData, UComboBoxString::StaticClass());
	}
	else
	{
		Widget = NewObject<UComboBoxString>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UComboBoxString Failed!"));
		return nullptr;
	}

	if (JsonData->HasField(TEXT("OptionStrings")))
	{
		const TArray<TSharedPtr<FJsonValue>>& OptionValues = JsonData->GetArrayField(TEXT("OptionStrings"));
		for (const TSharedPtr<FJsonValue>& OptionValue : OptionValues)
		{
			if (OptionValue.IsValid())
			{
				Widget->AddOption(OptionValue->AsString());
			}
		}
	}
	else if (ObjectData.IsValid() && ObjectData->HasField(TEXT("Options")))
	{
		const TArray<TSharedPtr<FJsonValue>>& OptionValues = ObjectData->GetArrayField(TEXT("Options"));
		for (const TSharedPtr<FJsonValue>& OptionValue : OptionValues)
		{
			if (OptionValue.IsValid())
			{
				Widget->AddOption(OptionValue->AsString());
			}
		}
	}

	FString SelectedOption;
	if (JsonData->HasField(CommonStrKey))
	{
		SelectedOption = JsonData->GetStringField(CommonStrKey);
	}
	if (SelectedOption.IsEmpty() && ObjectData.IsValid() && ObjectData->HasField(TEXT("SelectedOption")))
	{
		SelectedOption = ObjectData->GetStringField(TEXT("SelectedOption"));
	}

	if (!SelectedOption.IsEmpty() && Widget->FindOptionIndex(SelectedOption) != INDEX_NONE)
	{
		Widget->SetSelectedOption(SelectedOption);
	}

	return Widget;
}

ELQAWidgetType FLQA_ComboBox2Json::GetType()
{
	return ELQAWidgetType::LQA_ComboBoxStringText;
}
