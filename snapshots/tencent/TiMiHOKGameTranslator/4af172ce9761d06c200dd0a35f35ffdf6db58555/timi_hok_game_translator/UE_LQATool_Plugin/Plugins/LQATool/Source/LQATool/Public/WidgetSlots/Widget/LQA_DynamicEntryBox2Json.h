#pragma once

#include "CoreMinimal.h"
#include "Json.h"
#include "WidgetSlots/Widget2JsonInterface.h"

class FLQA_DynamicEntryBox2Json : public FWidget2JsonInterface
{
public:
	virtual void ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) override;
};
