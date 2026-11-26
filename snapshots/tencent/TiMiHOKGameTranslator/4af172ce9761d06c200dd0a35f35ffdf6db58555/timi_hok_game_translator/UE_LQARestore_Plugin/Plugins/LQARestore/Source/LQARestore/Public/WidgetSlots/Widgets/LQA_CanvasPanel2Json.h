#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UCanvasPanel;

// For CanvasPanel
class FLQA_CanvasPanel2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};