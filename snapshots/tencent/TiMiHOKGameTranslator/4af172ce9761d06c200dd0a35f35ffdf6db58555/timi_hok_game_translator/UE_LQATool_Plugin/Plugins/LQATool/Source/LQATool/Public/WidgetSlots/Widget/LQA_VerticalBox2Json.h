#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UVerticalBox;

// For VerticalBox
class FLQA_VerticalBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
