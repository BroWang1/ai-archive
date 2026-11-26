#pragma once

#include "Components/InputKeySelector.h"
#include "WidgetSlots/Widget2JsonInterface.h"

class UInputKeySelector;

// For InputKeySelector
class FLQA_InputKeySelector2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
