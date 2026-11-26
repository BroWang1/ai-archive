#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UWidgetSwitcher;

// For WidgetSwitcher
class FLQA_WidgetSwitcher2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};
