#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UUniformGridPanel;

// For UniformGridPanel
class FLQA_UniformGridPanel2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};