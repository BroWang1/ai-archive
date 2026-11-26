#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UImage;

// For Image
class FLQA_Image2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
