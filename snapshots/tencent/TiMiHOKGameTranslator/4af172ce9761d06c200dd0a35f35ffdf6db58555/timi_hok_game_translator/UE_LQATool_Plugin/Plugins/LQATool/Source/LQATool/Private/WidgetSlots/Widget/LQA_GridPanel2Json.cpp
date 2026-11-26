#include "WidgetSlots/Widget/LQA_GridPanel2Json.h"

#include "Components/GridPanel.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_GridPanel2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}
	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_GridPanel.ToString());
}
