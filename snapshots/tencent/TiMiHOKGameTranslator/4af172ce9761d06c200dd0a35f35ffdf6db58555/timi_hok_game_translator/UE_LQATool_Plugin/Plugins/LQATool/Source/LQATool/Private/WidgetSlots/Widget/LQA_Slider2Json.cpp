#include "WidgetSlots/Widget/LQA_Slider2Json.h"

#include "Components/Slider.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_Slider2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Slider.ToString());
}
