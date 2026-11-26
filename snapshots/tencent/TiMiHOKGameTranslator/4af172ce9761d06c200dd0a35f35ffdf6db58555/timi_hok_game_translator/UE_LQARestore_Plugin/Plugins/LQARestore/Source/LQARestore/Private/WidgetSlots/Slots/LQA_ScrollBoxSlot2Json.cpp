#include "WidgetSlots/Slots/LQA_ScrollBoxSlot2Json.h"

#include "Components/ScrollBoxSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_ScrollBoxSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UScrollBoxSlot* Slot = Cast<UScrollBoxSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UScrollBoxSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}