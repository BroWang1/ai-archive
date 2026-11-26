#include "WidgetSlots/Widgets/LQA_MultilineEditableTextBox2Json.h"

#include "Components/MultiLineEditableTextBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_MultilineEditableTextBox::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for MultiLineEditableTextBox"));
		return nullptr;
	}

	UMultiLineEditableTextBox* NewTextBlock = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewTextBlock = GetAsObject<UMultiLineEditableTextBox>(ObjectData, UMultiLineEditableTextBox::StaticClass());
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

ELQAWidgetType FLQA_MultilineEditableTextBox::GetType()
{
	return ELQAWidgetType::LQA_MultilineEditableTextBox;
}