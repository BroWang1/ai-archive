#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UVerticalBox;

// For VerticalBox
class FLQA_VerticalBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};