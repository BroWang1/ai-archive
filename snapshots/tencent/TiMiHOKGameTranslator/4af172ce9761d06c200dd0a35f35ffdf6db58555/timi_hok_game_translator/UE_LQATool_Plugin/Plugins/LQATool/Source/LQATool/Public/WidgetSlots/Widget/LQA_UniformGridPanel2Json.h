#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

class UUniformGridPanel;

// For UniformGridPanel
class FLQA_UniformGridPanel2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
