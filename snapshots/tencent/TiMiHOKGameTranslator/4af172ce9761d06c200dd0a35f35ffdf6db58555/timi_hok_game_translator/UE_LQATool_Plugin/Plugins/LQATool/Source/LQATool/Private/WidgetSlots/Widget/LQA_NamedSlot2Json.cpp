#include "WidgetSlots/Widget/LQA_NamedSlot2Json.h"

#include "Snapshot/LQAWidgetNode.h"
#include "WidgetSlots/WidgetDefines.h"

void FLQA_NamedSlot2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_NamedSlot.ToString());
}
