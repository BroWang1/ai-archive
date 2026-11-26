#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UUserWidget;

// For UserWidget
class FLQA_UserWidget2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
