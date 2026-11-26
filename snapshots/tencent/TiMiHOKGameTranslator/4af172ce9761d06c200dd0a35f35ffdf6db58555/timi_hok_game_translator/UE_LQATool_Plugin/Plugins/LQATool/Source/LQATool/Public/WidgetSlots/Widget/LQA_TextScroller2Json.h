#pragma once

#include "Components/TextBlock.h"
#include "WidgetSlots/Widget2JsonInterface.h"

class UTextBlock;

// For TextScroller
class FLQA_TextScroller2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
