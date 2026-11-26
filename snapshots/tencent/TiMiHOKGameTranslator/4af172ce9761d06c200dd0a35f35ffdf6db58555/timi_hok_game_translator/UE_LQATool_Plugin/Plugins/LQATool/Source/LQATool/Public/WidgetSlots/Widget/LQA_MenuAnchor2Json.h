#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For MenuAnchor
class FLQA_MenuAnchor2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
