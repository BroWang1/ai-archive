#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For MultilineEditableTextBlock
class FLQA_MultilineEditableTextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};