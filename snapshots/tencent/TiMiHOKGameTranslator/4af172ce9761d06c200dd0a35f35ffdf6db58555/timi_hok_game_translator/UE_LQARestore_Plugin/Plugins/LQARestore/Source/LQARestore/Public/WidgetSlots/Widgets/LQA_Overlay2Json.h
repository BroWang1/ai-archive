#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UOverlay;

// For Overlay
class FLQA_Overlay2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};
