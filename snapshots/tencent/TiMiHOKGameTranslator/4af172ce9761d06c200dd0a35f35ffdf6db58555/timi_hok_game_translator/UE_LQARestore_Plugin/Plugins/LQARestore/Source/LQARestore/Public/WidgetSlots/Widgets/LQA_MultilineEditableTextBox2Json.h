#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For MultilineEditableTextBox
class FLQA_MultilineEditableTextBox : public FWidget2JsonInterface
{
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};