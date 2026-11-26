#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UCanvasPanel;

// For CanvasPanel
class FLQA_CanvasPanel2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
