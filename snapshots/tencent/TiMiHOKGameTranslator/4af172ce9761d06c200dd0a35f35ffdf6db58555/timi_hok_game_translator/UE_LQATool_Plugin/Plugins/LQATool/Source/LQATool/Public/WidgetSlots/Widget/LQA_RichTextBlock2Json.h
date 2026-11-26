#pragma once

#include "Components/RichTextBlock.h"
#include "WidgetSlots/Widget2JsonInterface.h"

class URichTextBlock;

// For RichTextBlock
class FLQA_RichTextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
