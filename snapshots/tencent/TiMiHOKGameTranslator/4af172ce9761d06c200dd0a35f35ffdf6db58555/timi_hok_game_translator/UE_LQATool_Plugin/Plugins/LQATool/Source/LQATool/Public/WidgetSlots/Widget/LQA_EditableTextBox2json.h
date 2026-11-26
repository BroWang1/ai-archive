#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UEditableTextBox;

// For EditableTextBox
class FLQA_EditableTextBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
