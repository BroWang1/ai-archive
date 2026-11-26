#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UComboBox;

// For ComboBox
class FLQA_ComboBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
