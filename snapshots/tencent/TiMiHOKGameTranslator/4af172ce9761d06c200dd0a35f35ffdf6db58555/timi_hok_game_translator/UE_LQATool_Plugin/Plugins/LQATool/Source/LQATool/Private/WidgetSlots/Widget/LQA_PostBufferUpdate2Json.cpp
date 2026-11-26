#include "WidgetSlots/Widget/LQA_PostBufferUpdate2Json.h"

#include "Snapshot/LQAWidgetNode.h"

void FLQA_PostBufferUpdate2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_PostBufferUpdate.ToString());
}
