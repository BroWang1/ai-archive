#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UScrollBox;

// For ScrollBox
class FLQA_ScrollBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
