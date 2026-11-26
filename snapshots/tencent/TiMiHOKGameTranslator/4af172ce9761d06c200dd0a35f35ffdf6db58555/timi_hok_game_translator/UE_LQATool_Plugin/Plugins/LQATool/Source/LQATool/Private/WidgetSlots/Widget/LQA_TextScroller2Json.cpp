#include "WidgetSlots/Widget/LQA_TextScroller2Json.h"

#include "Snapshot/LQAWidgetNode.h"

void FLQA_TextScroller2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_TextScroller.ToString());

	// 滚动文本控件的文本来源与其 UObject (TextBlock 或其派生类) 一致
	if (InWidget->SourceObject.IsValid())
	{
		const UTextBlock* TextScrollerIns = Cast<UTextBlock>(InWidget->SourceObject);
		if (TextScrollerIns)
		{
			const FText Text = TextScrollerIns->GetText();
			UE_LOG(LogLQAToolWidget2Json, Verbose, TEXT("Find Text Scroller Content = %s"), *Text.ToString());
			WriteTextEntry_ToJson(OutJsonObject, Text);
		}
	}
}
