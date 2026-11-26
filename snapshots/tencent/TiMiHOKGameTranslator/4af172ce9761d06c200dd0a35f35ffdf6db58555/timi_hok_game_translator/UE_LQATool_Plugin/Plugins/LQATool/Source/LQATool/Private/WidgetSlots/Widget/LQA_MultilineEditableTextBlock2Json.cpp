#include "WidgetSlots/Widget/LQA_MultilineEditableTextBlock2Json.h"

#include "Components/MultiLineEditableText.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_MultilineEditableTextBlock2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_MultilineEditableText.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UMultiLineEditableText* EditableText = Cast<UMultiLineEditableText>(InWidget->SourceObject);
		if (EditableText)
		{
			WriteTextEntry_ToJson(OutJsonObject, EditableText->GetText());
			WriteTextEntry_ToJson(OutJsonObject, EditableText->GetHintText(), TEXT("hinttextStr"), TEXT("HintTextKey"),
				TEXT("HintTextSourceStr"));
		}
	}
}
