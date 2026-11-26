#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UWindowTitleBarArea;

// For WindowTitleBarArea (Slate: SWindowTitleBarArea)
class FLQA_WindowTitleBarArea2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};
