#include "WidgetSlots/Slots/LQA_StackBoxSlot2Json.h"

#if ENGINE_MAJOR_VERSION >= 5

#include "Components/Widget.h"
#include "Components/StackBoxSlot.h"
#include "Utils/JsonUtils.h"

bool FLQA_StackBoxSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UStackBoxSlot* Slot = Cast<UStackBoxSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning,
				TEXT("Failed to cast PanelSlot to UStackBoxSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}

#else

bool FLQA_StackBoxSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	return false;
}

#endif // ENGINE_MAJOR_VERSION >= 5
