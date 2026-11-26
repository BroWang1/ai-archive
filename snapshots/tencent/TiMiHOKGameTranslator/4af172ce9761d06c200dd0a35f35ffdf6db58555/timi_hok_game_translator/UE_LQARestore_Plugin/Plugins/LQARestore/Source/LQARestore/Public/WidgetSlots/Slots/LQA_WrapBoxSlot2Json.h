#pragma once

#include "CoreMinimal.h"
#include "Json.h"
#include "JsonUtilities.h"
#include "WidgetSlots/Core/Slot2JsonInterface.h"

class FLQA_WrapBoxSlot2Json : public FSlot2JsonInterface
{
public:
	virtual bool FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot) override;

private:
};