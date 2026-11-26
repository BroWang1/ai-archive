#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UPlatformPaddingBox;

// For PlatformPaddingBox
class FLQA_PlatformPaddingBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};