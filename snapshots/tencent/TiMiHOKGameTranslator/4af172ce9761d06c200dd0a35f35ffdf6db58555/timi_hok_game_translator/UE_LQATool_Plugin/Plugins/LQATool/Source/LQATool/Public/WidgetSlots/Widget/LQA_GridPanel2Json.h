#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UGridPanel;

// For CanvasPanel
class FLQA_GridPanel2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
