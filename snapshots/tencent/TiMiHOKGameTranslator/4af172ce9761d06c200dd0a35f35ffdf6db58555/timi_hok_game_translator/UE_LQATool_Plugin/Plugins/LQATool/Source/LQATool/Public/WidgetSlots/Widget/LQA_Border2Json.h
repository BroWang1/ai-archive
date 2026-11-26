#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UBorder;

// For Border
class FLQA_Border2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
