#include "WidgetSlots/Widget/LQA_MultilineEditableTextBox2Json.h"

#include "Components/MultiLineEditableTextBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_MultilineEditableTextBox::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_MultilineEditableTextBox.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UMultiLineEditableTextBox* EditableText = Cast<UMultiLineEditableTextBox>(InWidget->SourceObject);
		if (EditableText)
		{
			WriteTextEntry_ToJson(OutJsonObject, EditableText->GetText());
			WriteTextEntry_ToJson(OutJsonObject, EditableText->GetHintText(), TEXT("hinttextStr"), TEXT("HintTextKey"),
				TEXT("HintTextSourceStr"));
		}
	}
}
