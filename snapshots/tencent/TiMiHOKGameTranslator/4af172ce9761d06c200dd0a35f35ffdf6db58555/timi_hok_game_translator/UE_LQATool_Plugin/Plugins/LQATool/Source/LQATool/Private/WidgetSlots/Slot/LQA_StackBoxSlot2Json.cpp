#include "WidgetSlots/Slot/LQA_StackBoxSlot2Json.h"

#if ENGINE_MAJOR_VERSION >= 5

#include "Components/Widget.h"
#include "Components/StackBoxSlot.h"
#include "Utils/LQAJsonUtils.h"

void FLQA_StackBoxSlot2Json::ToJson(
	const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	if (InWidget->SourceObject.IsValid())
	{
		UWidget* SourceUwg = Cast<UWidget>(InWidget->SourceObject);
		if (!SourceUwg)
		{
			return;
		}

		UStackBoxSlot* Slot = Cast<UStackBoxSlot>(SourceUwg->Slot);
		if (Slot)
		{
			TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject);
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, Slot))
			{
				OutJsonObject->SetObjectField(TEXT("Slot"), JsonObject);
				OutJsonObject->SetStringField(TEXT("SlotType"), TEXT("UStackBoxSlot"));
			}
		}
	}
}

#else

void FLQA_StackBoxSlot2Json::ToJson(
	const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject)
{
}

#endif // ENGINE_MAJOR_VERSION >= 5
