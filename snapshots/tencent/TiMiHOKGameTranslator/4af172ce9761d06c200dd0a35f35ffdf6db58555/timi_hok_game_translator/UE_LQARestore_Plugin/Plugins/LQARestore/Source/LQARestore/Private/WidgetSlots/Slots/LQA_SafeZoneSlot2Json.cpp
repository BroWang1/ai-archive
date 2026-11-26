#include "WidgetSlots/Slots/LQA_SafeZoneSlot2Json.h"

#include "Components/SafeZoneSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_SafeZoneSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		USafeZoneSlot* Slot = Cast<USafeZoneSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to USafeZoneSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}