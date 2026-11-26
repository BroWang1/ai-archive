#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UMenuAnchor;

// For MenuAnchor
class FLQA_MenuAnchor2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};
