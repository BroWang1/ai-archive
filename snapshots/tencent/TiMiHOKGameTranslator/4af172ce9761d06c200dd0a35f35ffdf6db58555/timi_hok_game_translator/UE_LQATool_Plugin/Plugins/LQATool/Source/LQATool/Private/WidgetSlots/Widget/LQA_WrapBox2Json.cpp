#include "WidgetSlots/Widget/LQA_WrapBox2Json.h"

#include "Components/WrapBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_WrapBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_WrapBox.ToString());
}
