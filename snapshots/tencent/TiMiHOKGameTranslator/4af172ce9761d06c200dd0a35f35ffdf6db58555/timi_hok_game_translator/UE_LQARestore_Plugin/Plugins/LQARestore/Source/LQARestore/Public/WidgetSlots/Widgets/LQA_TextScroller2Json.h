#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"
class UTextScroller;

// For TextScroller
class FLQA_TextScroller2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};