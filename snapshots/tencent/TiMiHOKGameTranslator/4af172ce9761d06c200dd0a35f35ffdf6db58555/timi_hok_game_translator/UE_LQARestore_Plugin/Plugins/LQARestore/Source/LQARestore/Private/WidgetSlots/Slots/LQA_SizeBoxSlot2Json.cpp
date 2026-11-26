#include "WidgetSlots/Slots/LQA_SizeBoxSlot2Json.h"

#include "Components/SizeBoxSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_SizeBoxSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		USizeBoxSlot* Slot = Cast<USizeBoxSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to USizeBoxSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}