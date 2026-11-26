#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UScrollBox;

// For ScrollBox
class FLQA_ScrollBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};