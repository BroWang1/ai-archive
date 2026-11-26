#include "WidgetSlots/Widgets/LQA_MultilineEditableTextBlock2Json.h"

#include "Components/MultiLineEditableText.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_MultilineEditableTextBlock2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for MultiLineEditableText"));
		return nullptr;
	}

	UMultiLineEditableText* NewTextBlock = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewTextBlock = GetAsObject<UMultiLineEditableText>(ObjectData, UMultiLineEditableText::StaticClass());
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

ELQAWidgetType FLQA_MultilineEditableTextBlock2Json::GetType()
{
	return ELQAWidgetType::LQA_MultilineEditableText;
}