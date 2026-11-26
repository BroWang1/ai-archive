#pragma once

#include "Components/RichTextBlock.h"
#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For RichTextBlock
class FLQA_RichTextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};