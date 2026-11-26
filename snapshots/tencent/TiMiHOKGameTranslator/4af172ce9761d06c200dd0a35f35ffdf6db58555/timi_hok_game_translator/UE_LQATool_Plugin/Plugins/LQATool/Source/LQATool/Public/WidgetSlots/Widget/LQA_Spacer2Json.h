#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For Spacer (shell: no text/texture collection)
class FLQA_Spacer2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
