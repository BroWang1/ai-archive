#include "WidgetSlots/Widget/LQA_EditableTextBlock2Json.h"

#include "Components/EditableText.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_EditableTextBlock2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_EditableText.ToString());
	if (InWidget->SourceObject.IsValid())
	{
		const UEditableText* EditableText = Cast<UEditableText>(InWidget->SourceObject);
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
