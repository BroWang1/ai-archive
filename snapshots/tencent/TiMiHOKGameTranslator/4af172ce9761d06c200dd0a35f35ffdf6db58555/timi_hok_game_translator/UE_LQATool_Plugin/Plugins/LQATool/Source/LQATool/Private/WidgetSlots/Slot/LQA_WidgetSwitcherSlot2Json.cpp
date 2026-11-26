#include "WidgetSlots/Slot/LQA_WidgetSwitcherSlot2Json.h"

#include "Components/Widget.h"
#include "Components/WidgetSwitcherSlot.h"
#include "Utils/LQAJsonUtils.h"

void FLQA_WidgetSwitcherSlot2Json::ToJson(
	const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	if (InWidget->SourceObject.IsValid())
	{
		UWidget* SourceUwg = Cast<UWidget>(InWidget->SourceObject);
		if (!SourceUwg)
		{
			return;
		}

		UWidgetSwitcherSlot* Slot = Cast<UWidgetSwitcherSlot>(SourceUwg->Slot);
		if (Slot)
		{
			TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot))
			{
				OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
				OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("UWidgetSwitcherSlot"));
			}
		}
	}
}
