#include "WidgetSlots/Widget/LQA_SizeBox2Json.h"

#include "Snapshot/LQAWidgetNode.h"
#include "WidgetSlots/WidgetDefines.h"

void FLQA_SizeBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_SizeBox.ToString());
}
