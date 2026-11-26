#include "WidgetSlots/Slot/LQA_SizeBoxSlot2Json.h"

#include "Components/SizeBoxSlot.h"
#include "Components/Widget.h"
#include "Utils/LQAJsonUtils.h"

void FLQA_SizeBoxSlot2Json::ToJson(
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

		USizeBoxSlot* Slot = Cast<USizeBoxSlot>(SourceUwg->Slot);
		if (Slot)
		{
			TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot))
			{
				OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
				OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("USizeBoxSlot"));
			}
		}
	}
}
