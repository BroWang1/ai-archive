#pragma once
#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UCheckBox;

// For CheckBox
class FLQA_CheckBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};