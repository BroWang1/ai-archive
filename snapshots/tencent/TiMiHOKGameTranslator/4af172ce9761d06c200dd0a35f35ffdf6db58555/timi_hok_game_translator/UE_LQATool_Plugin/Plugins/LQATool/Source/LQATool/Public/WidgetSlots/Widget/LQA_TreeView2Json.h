#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For TreeView
class FLQA_TreeView2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
