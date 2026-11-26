#pragma once

#include "Components/RetainerBox.h"
#include "WidgetSlots/Widget2JsonInterface.h"

class URetainerBox;

// For RetainerBox
class FLQA_RetainerBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
