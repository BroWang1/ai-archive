#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For InvalidationBox
class FLQA_InvalidationBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
