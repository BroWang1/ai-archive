#include "WidgetSlots/Widget/LQA_UniformGridPanel2Json.h"

#include "Components/UniformGridPanel.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_UniformGridPanel2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}
	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_UniformGridPanel.ToString());
}
