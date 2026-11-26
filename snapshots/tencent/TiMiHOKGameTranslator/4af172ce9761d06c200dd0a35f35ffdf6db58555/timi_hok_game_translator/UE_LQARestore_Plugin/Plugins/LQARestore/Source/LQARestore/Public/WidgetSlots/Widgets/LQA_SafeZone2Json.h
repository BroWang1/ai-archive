#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class USafeZone;

// For SafeZone
class FLQA_SafeZone2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};