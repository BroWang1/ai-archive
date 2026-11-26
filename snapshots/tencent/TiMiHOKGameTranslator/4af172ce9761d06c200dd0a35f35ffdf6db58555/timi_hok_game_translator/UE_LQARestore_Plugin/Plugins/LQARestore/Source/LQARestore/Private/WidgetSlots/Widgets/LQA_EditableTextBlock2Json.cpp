#include "WidgetSlots/Widgets/LQA_EditableTextBlock2Json.h"

#include "Components/EditableText.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_EditableTextBlock2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for EditableText"));
		return nullptr;
	}

	UEditableText* NewTextBlock = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewTextBlock = GetAsObject<UEditableText>(ObjectData, UEditableText::StaticClass());
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

ELQAWidgetType FLQA_EditableTextBlock2Json::GetType()
{
	return ELQAWidgetType::LQA_EditableText;
}
