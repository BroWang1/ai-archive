#include "WidgetSlots/Slots/LQA_WindowTitleBarAreaSlot2Json.h"

#include "Components/Widget.h"
#include "Components/WindowTitleBarAreaSlot.h"
#include "Utils/JsonUtils.h"

bool FLQA_WindowTitleBarAreaSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UWindowTitleBarAreaSlot* Slot = Cast<UWindowTitleBarAreaSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning,
				TEXT("Failed to cast PanelSlot to UWindowTitleBarAreaSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}
