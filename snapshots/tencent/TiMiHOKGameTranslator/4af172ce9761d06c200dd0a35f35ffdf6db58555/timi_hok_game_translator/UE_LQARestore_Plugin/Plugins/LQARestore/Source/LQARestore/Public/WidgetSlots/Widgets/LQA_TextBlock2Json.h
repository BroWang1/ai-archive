#pragma once

#include "Components/TextBlock.h"
#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UTextBlock;

// For TextBlock
class FLQA_TextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};