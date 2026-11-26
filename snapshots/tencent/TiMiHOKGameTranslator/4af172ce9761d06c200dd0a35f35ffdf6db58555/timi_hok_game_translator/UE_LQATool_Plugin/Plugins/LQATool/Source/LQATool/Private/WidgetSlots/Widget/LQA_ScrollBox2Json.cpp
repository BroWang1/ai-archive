#include "WidgetSlots/Widget/LQA_ScrollBox2Json.h"

#include "Components/ScrollBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_ScrollBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_ScrollBox.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UScrollBox* ScrollBoxIns = Cast<UScrollBox>(InWidget->SourceObject.Get());
		if (ScrollBoxIns)
		{
			OutJsonObject->SetNumberField(TEXT("ScrollOffset"), ScrollBoxIns->GetScrollOffset());
		}
	}
}
