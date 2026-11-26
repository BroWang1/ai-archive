#include "WidgetSlots/Widget/LQA_SpinBox2Json.h"

#include "Components/SpinBox.h"
#include "Snapshot/LQAWidgetNode.h"

void FLQA_SpinBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_SpinBox.ToString());
}
