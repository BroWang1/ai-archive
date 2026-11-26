#include "WidgetSlots/Slots/LQA_OverlaySlot2Json.h"

#include "Components/OverlaySlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_OverlaySlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UOverlaySlot* Slot = Cast<UOverlaySlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UOverlaySlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}