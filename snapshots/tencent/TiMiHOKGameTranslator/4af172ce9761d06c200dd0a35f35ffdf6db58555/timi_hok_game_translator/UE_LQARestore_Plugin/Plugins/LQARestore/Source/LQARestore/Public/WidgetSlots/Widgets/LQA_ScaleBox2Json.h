#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UScaleBox;

// For ScaleBox
class FLQA_ScaleBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};