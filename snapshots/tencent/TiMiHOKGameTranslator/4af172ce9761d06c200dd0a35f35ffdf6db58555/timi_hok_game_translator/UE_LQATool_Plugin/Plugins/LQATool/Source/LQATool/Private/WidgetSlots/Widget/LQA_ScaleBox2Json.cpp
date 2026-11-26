#include "WidgetSlots/Widget/LQA_ScaleBox2Json.h"

#include "Components/ScaleBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_ScaleBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_ScaleBox.ToString());
}
