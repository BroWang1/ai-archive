#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For ScrollBar
class FLQA_ScrollBar2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
