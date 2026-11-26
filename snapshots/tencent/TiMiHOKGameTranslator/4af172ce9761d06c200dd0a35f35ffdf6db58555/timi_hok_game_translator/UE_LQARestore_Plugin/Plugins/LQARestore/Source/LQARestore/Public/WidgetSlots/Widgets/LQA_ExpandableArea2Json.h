#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UExpandableArea;

// For ExpandableArea (Slate: SExpandableArea)
class FLQA_ExpandableArea2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};
