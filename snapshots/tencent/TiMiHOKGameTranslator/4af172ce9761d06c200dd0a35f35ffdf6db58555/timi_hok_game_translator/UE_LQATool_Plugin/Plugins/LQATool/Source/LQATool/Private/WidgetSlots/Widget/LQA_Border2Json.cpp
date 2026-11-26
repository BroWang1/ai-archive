#include "WidgetSlots/Widget/LQA_Border2Json.h"

#include "Components/Border.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQATextureUtil.h"

void FLQA_Border2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Border.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UBorder* Border = Cast<UBorder>(InWidget->SourceObject);
		if (Border)
		{
			UObject* ResourceObject = Border->Background.GetResourceObject();
			if (ResourceObject)
			{
				OutJsonObject->SetObjectField(
					TEXT("TextureData"), FLQATextureUtil::GetTextureJsonObj(ResourceObject, SharedTextureMap));
			}
		}
	}
}
