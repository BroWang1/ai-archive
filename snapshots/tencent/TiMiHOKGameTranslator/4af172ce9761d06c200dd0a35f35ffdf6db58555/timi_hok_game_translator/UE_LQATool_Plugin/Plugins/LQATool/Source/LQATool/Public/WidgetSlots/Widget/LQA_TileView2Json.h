#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For TileView
class FLQA_TileView2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
