#include "WidgetSlots/Widget/LQA_TextBlock2Json.h"

#include "Snapshot/LQAWidgetNode.h"

void FLQA_TextBlock2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_TextBlock.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UTextBlock* TextBlockIns = Cast<UTextBlock>(InWidget->SourceObject);
		if (TextBlockIns)
		{
			const FText Text = TextBlockIns->GetText();
			UE_LOG(LogLQAToolWidget2Json, Verbose, TEXT("Find Text Block Content = %s"), *Text.ToString());
			WriteTextEntry_ToJson(OutJsonObject, Text);
		}
	}
}
