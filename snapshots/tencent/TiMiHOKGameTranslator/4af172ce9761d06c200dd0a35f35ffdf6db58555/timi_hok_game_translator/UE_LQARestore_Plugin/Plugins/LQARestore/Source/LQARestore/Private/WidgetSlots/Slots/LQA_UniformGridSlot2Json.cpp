#include "WidgetSlots/Slots/LQA_UniformGridSlot2Json.h"

#include "Components/UniformGridSlot.h"
#include "Components/Widget.h"
#include "Utils/JsonUtils.h"

bool FLQA_UniformGridSlot2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot)
{
	if (JsonData.IsValid() && JsonData->Values.Num() > 0)
	{
		UUniformGridSlot* Slot = Cast<UUniformGridSlot>(PanelSlot);
		if (Slot)
		{
			bool bResult = SetPanelSlotProperties(JsonData, Slot);
			Slot->SynchronizeProperties();
			return bResult;
		}
		else
		{
			UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Failed to cast PanelSlot to UUniformGridSlot. Actual type: %s"),
				PanelSlot ? *PanelSlot->GetClass()->GetName() : TEXT("nullptr"));
		}
	}
	return false;
}