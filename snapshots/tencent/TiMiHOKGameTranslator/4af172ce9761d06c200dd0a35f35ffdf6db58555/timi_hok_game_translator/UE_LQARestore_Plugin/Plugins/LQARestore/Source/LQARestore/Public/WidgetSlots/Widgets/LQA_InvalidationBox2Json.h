#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UInvalidationBox;

// For InvalidationBox (Slate: SInvalidationPanel)
class FLQA_InvalidationBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};
