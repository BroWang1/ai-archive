#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UButton;

// For Button
class FLQA_Button2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
