#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For SpinBox (shell: no text/texture collection)
class FLQA_SpinBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
