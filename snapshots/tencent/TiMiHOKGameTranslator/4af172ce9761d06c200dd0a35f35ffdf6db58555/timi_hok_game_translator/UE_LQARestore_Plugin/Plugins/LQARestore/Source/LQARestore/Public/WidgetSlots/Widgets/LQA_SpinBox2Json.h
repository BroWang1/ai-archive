#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class USpinBox;

// For SpinBox
class FLQA_SpinBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};
