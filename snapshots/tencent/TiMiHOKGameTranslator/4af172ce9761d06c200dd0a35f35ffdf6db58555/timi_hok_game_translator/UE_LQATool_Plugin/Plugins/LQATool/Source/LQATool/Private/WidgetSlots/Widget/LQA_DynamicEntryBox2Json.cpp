#include "WidgetSlots/Widget/LQA_DynamicEntryBox2Json.h"

#include "Snapshot/LQAWidgetNode.h"
#include "WidgetSlots/WidgetDefines.h"

// 输出动态条目框: WidgetType 取实际 Slate 根类型名, 由 WidgetClass 标识动态条目框
void FLQA_DynamicEntryBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), InWidget->BaseWidgetType);
}
