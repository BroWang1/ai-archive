#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UCircularThrobber;

// For CircularThrobber (collects Image texture)
class FLQA_CircularThrobber2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
