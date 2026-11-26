#include "WidgetSlots/Widget/LQA_WidgetSwitcher2Json.h"

#include "Components/WidgetSwitcher.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_WidgetSwitcher2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_WidgetSwitcher.ToString());
}
