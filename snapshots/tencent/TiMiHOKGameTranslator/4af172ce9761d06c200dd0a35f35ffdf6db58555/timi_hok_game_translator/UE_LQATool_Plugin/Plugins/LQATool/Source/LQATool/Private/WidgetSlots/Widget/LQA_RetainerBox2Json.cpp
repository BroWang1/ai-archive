#include "WidgetSlots/Widget/LQA_RetainerBox2Json.h"

#include "Snapshot/LQAWidgetNode.h"

void FLQA_RetainerBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_RetainerBox.ToString());
}
