#pragma once

#include "CoreMinimal.h"
#include "Json.h"
#include "JsonUtilities.h"
#include "WidgetSlots/Slot2JsonInterface.h"

class FLQA_PanelSlot2Json : public FSlot2JsonInterface
{
public:
	virtual void ToJson(
		const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject) override;
};
