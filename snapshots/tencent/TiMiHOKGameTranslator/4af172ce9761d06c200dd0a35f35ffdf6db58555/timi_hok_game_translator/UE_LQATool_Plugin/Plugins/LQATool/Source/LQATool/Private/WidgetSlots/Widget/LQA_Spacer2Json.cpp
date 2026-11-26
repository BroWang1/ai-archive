#include "WidgetSlots/Widget/LQA_Spacer2Json.h"

#include "Components/Spacer.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_Spacer2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Spacer.ToString());
}
