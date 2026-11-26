#include "WidgetSlots/Widget/LQA_SafeZone2Json.h"

#include "Components/SafeZone.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_SafeZone2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_SafeZone.ToString());
}
