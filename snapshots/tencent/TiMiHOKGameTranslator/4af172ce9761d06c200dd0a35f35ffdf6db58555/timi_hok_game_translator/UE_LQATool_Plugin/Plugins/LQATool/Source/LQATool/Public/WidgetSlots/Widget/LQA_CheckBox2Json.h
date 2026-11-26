#pragma once
#include "WidgetSlots/Widget2JsonInterface.h"

class UCheckBox;

// For CheckBox
class FLQA_CheckBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
