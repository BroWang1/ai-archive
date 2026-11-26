#include "WidgetSlots/Widget/LQA_InputKeySelector2Json.h"

#include "Components/InputKeySelector.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_InputKeySelector2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_InputKeySelector.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UInputKeySelector* InputKeySelectorIns = Cast<UInputKeySelector>(InWidget->SourceObject);
		if (InputKeySelectorIns)
		{
#if ENGINE_MAJOR_VERSION >= 5
			const FText KeySelectionText = InputKeySelectorIns->GetKeySelectionText();
			const FText NoKeySpecifiedText = InputKeySelectorIns->GetNoKeySpecifiedText();
#else
			const FText KeySelectionText = InputKeySelectorIns->KeySelectionText;
			const FText NoKeySpecifiedText = InputKeySelectorIns->NoKeySpecifiedText;
#endif

			WriteTextEntry_ToJson(OutJsonObject, KeySelectionText.IsEmpty() ? NoKeySpecifiedText : KeySelectionText);
		}
	}
}
