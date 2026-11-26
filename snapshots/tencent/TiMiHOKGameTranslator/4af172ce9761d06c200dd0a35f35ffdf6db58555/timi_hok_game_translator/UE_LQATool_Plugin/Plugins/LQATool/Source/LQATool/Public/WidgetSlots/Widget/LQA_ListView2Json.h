#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For ListView
class FLQA_ListView2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
