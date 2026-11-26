#include "WidgetSlots/Slot/LQA_OverlaySlot2Json.h"

#include "Components/OverlaySlot.h"
#include "Components/Widget.h"
#include "Utils/LQAJsonUtils.h"

void FLQA_OverlaySlot2Json::ToJson(
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

		UOverlaySlot* Slot = Cast<UOverlaySlot>(SourceUwg->Slot);
		if (Slot)
		{
			TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot))
			{
				OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
				OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("UOverlaySlot"));
			}
		}
	}
}
