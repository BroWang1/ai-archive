#include "WidgetSlots/Slot/LQA_PanelSlot2Json.h"

#include "Components/PanelSlot.h"
#include "Components/Widget.h"
#include "Utils/LQAJsonUtils.h"

// 输出单子容器内容槽: UPanelSlot 基类无可序列化的布局属性时仍写入空 Slot 对象与槽类型
void FLQA_PanelSlot2Json::ToJson(
	const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	if (!InWidget->SourceObject.IsValid())
	{
		return;
	}

	UWidget* SourceUwg = Cast<UWidget>(InWidget->SourceObject);
	if (!SourceUwg)
	{
		return;
	}

	UPanelSlot* Slot = Cast<UPanelSlot>(SourceUwg->Slot);
	if (!Slot)
	{
		return;
	}

	TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
	FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot);

	OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
	OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("UPanelSlot"));
}
