#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UProgressBar;

// For ProgressBar (collects FillImage texture)
class FLQA_ProgressBar2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
