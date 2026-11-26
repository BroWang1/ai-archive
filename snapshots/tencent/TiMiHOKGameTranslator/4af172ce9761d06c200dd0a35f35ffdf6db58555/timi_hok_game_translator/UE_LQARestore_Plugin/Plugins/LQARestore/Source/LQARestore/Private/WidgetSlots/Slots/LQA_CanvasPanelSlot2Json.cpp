#include "WidgetSlots/Slots/LQA_CanvasPanelSlot2Json.h"

#include "Components/CanvasPanelSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_CanvasPanelSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UCanvasPanelSlot* Slot = Cast<UCanvasPanelSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UCanvasPanelSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}