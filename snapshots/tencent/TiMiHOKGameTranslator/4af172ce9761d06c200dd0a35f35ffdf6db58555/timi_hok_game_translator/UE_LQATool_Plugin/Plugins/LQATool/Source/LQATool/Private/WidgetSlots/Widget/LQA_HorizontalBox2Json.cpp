#include "WidgetSlots/Widget/LQA_HorizontalBox2Json.h"

#include "Components/HorizontalBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_HorizontalBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_HorizontalBox.ToString());
}
