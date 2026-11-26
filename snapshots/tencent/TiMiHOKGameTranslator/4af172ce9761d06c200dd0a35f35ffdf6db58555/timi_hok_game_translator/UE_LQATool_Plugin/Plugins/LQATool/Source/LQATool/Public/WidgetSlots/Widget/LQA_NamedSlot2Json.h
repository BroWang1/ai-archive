#pragma once

#include "WidgetSlots/Widget2JsonInterface.h"

// For NamedSlot (Slate 层根为 SBox, 类型由注册表按 UNamedSlot 判定)
class FLQA_NamedSlot2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(TSharedPtr<FLQAWidgetNode> InWidget, TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
