#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For Slider (shell: no text/texture collection)
class FLQA_Slider2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
