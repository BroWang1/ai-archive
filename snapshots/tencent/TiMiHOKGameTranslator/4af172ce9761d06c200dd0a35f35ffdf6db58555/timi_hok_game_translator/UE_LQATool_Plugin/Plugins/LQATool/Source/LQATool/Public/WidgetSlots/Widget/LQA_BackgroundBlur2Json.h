#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UBackgroundBlur;

// For BackgroundBlur
class FLQA_BackgroundBlur2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
