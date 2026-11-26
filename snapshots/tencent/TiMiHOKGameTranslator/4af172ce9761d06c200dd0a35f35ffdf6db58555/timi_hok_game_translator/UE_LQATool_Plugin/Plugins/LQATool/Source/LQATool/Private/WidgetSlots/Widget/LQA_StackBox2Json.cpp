#include "WidgetSlots/Widget/LQA_StackBox2Json.h"

#include "Snapshot/LQAWidgetNode.h"

void FLQA_StackBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_StackBox.ToString());
}
