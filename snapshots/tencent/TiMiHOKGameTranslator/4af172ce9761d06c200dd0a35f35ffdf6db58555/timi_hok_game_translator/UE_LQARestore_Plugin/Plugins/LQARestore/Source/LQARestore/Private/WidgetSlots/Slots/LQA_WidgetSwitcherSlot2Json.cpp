#include "WidgetSlots/Slots/LQA_WidgetSwitcherSlot2Json.h"

#include "Components/Widget.h"
#include "Components/WidgetSwitcherSlot.h"
#include "Utils/JsonUtils.h"

bool FLQA_WidgetSwitcherSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UWidgetSwitcherSlot* Slot = Cast<UWidgetSwitcherSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning,
				TEXT("Failed to cast PanelSlot to UWidgetSwitcherSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}
