#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UBackgroundBlur;

// For BackgroundBlur
class FLQA_BackgroundBlur2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};