#include "WidgetSlots/Widget/LQA_NativeWidgetHost2Json.h"

#include "Snapshot/LQAWidgetNode.h"
#include "WidgetSlots/WidgetDefines.h"

void FLQA_NativeWidgetHost2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_NativeWidgetHost.ToString());
}
