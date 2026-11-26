#include "WidgetSlots/Slot/LQA_WrapBoxSlot2Json.h"

#include "Components/Widget.h"
#include "Components/WrapBoxSlot.h"
#include "Utils/LQAJsonUtils.h"

void FLQA_WrapBoxSlot2Json::ToJson(
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

		UWrapBoxSlot* Slot = Cast<UWrapBoxSlot>(SourceUwg->Slot);
		if (Slot)
		{
			TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot))
			{
				OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
				OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("UWrapBoxSlot"));
			}
		}
	}
}
