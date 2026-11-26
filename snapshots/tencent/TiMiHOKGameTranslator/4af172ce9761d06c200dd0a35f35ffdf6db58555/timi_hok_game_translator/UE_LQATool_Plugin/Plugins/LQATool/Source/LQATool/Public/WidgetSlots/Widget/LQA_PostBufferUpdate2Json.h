#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For PostBufferUpdate
class FLQA_PostBufferUpdate2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
