#include "WidgetSlots/Widgets/LQA_EditableTextBox2Json.h"

#include "Components/EditableTextBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_EditableTextBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for EditableTextBox"));
		return nullptr;
	}

	UEditableTextBox* NewTextBlock = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewTextBlock = GetAsObject<UEditableTextBox>(ObjectData, UEditableTextBox::StaticClass());
		}
	}

	if (NewTextBlock)
	{
		const FText Text = GetTextFromJson(JsonData);
		const FText HintText =
			GetTextFromJson(JsonData, TEXT("hinttextStr"), TEXT("HintTextKey"), TEXT("HintTextSourceStr"));
		NewTextBlock->SetText(Text);
		NewTextBlock->SetHintText(HintText);

		return NewTextBlock;
	}
	else
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Restore RichTextBlock Failed!"));
	}

	return nullptr;
}

ELQAWidgetType FLQA_EditableTextBox2Json::GetType()
{
	return ELQAWidgetType::LQA_EditableTextBox;
}
