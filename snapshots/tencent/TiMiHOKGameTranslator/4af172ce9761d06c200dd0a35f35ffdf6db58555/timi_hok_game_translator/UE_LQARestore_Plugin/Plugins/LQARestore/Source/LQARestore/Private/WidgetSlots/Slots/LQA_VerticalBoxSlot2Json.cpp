#include "WidgetSlots/Slots/LQA_VerticalBoxSlot2Json.h"

#include "Components/VerticalBoxSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_VerticalBoxSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UVerticalBoxSlot* Slot = Cast<UVerticalBoxSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UVerticalBoxSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}