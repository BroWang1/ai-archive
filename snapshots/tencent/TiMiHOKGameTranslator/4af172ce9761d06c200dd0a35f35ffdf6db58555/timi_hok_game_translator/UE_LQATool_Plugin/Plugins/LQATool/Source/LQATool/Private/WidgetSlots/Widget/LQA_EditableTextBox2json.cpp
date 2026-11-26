#include "WidgetSlots/Widget/LQA_EditableTextBox2Json.h"

#include "Components/EditableTextBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_EditableTextBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_EditableTextBox.ToString());
	if (InWidget->SourceObject.IsValid())
	{
		const UEditableTextBox* EditableText = Cast<UEditableTextBox>(InWidget->SourceObject);
		if (EditableText)
		{
			WriteTextEntry_ToJson(OutJsonObject, EditableText->GetText());
#if ENGINE_MAJOR_VERSION >= 5
			WriteTextEntry_ToJson(OutJsonObject, EditableText->GetHintText(), TEXT("hinttextStr"), TEXT("HintTextKey"),
				TEXT("HintTextSourceStr"));
#else
			WriteTextEntry_ToJson(OutJsonObject, EditableText->HintText, TEXT("hinttextStr"), TEXT("HintTextKey"),
				TEXT("HintTextSourceStr"));
#endif
		}
	}
}
