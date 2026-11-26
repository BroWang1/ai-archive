#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class USizeBox;

// For SizeBox
class FLQA_SizeBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};