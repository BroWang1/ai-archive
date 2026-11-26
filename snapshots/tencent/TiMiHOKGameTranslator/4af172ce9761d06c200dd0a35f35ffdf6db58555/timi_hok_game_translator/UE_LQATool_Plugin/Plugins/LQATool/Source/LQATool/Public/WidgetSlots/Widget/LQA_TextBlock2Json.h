#pragma once

#include "Components/TextBlock.h"
#include "WidgetSlots/Widget2JsonInterface.h"

class UTextBlock;

// For TextBlock
class FLQA_TextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
