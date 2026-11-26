#include "WidgetSlots/Slots/LQA_HorizontalBoxSlot2Json.h"

#include "Components/HorizontalBoxSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_HorizontalBoxSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UHorizontalBoxSlot* Slot = Cast<UHorizontalBoxSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UHorizontalBoxSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}