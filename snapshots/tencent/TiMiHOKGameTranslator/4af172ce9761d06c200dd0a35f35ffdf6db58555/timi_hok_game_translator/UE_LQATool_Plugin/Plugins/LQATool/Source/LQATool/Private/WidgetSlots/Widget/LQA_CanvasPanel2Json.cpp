#include "WidgetSlots/Widget/LQA_CanvasPanel2Json.h"

#include "Components/CanvasPanel.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQAJsonUtils.h"

void FLQA_CanvasPanel2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}
	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Canvas.ToString());
}
