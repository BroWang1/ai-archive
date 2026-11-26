#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UTexture2D;

// For Image
class FLQA_Image2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};