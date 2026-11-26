#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UStackBox;

// For StackBox (Slate: SStackBox)
class FLQA_StackBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};
