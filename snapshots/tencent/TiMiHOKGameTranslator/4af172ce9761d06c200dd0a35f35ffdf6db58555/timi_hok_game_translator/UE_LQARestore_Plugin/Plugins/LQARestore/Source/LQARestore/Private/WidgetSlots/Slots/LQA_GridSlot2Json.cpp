#include "WidgetSlots/Slots/LQA_GridSlot2Json.h"

#include "Components/GridSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_GridSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UGridSlot* Slot = Cast<UGridSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UGridSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}