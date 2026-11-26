#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UBorder;

// For Border
class FLQA_Border2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};