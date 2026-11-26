#include "WidgetSlots/Widget/LQA_BackgroundBlur2Json.h"

#include "Components/BackgroundBlur.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_BackgroundBlur2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_BackgroundBlur.ToString());
}
