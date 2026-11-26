#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UInputKeySelector;

// For InputKeySelector
class FLQA_InputKeySelector2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};
