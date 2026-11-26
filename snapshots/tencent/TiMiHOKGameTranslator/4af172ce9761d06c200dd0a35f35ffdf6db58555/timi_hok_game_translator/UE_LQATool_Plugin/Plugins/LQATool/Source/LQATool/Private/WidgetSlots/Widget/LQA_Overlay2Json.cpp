#include "WidgetSlots/Widget/LQA_Overlay2Json.h"

#include "Components/Overlay.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_Overlay2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Overlay.ToString());
}
