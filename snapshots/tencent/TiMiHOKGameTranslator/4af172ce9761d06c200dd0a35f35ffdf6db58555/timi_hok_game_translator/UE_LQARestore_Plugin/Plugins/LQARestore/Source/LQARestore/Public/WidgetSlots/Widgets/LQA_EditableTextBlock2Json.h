#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For EditableTextBlock
class FLQA_EditableTextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};