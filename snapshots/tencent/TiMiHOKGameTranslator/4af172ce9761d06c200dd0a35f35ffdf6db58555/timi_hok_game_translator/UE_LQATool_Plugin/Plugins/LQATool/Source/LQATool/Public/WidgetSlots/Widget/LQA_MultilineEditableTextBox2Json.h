#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UMultilineEditableTextBox;

// For MultilineEditableTextBox
class FLQA_MultilineEditableTextBox : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
