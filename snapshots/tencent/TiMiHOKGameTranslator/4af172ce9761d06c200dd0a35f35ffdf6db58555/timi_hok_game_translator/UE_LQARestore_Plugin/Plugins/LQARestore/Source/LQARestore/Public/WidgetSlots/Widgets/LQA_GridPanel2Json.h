#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UGridPanel;

// For CanvasPanel
class FLQA_GridPanel2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};