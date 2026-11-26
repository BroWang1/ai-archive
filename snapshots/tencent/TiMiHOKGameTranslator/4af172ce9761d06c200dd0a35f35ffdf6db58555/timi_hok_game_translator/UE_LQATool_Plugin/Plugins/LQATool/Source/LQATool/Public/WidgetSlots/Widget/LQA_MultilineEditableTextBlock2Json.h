#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UMultilineEditableTextBlock;

// For MultilineEditableTextBlock
class FLQA_MultilineEditableTextBlock2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
