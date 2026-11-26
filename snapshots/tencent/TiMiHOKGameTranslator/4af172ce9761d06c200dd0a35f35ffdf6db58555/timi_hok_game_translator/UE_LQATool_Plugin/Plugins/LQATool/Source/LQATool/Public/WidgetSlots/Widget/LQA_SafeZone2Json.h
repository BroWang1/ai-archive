#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class USafeZone;

// For SafeZone
class FLQA_SafeZone2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
