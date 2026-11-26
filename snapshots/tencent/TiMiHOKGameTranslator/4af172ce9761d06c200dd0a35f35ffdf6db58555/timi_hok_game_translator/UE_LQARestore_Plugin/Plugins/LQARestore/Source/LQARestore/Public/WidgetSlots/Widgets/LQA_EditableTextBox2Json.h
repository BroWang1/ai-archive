#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For EditableTextBox
class FLQA_EditableTextBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};