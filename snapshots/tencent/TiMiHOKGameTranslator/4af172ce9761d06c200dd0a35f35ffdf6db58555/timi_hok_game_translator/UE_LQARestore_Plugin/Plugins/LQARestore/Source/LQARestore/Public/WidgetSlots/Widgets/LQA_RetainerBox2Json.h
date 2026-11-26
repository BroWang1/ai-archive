#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class URetainerBox;

// For RetainerBox
class FLQA_RetainerBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};
