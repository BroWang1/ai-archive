#include "WidgetSlots/Widget/LQA_Image2Json.h"

#include "Components/Image.h"
#include "Engine/Texture2D.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQAJsonUtils.h"
#include "Utils/LQATextureUtil.h"

void FLQA_Image2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Image.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		UImage* Image = Cast<UImage>(InWidget->SourceObject);
		if (Image)
		{
#if ENGINE_MAJOR_VERSION >= 5
			UObject* ResourceObject = Image->GetBrush().GetResourceObject();
			FVector2D ImageSize = Image->GetBrush().ImageSize;
#else
			UObject* ResourceObject = Image->Brush.GetResourceObject();
			FVector2D ImageSize = Image->Brush.ImageSize;
#endif
			if (ResourceObject)
			{
				const TSharedPtr<FJsonObject> TextureObj =
					FLQATextureUtil::GetTextureJsonObj(ResourceObject, SharedTextureMap);
				OutJsonObject->SetObjectField(TEXT("TextureData"), TextureObj);
			}
		}
	}
}
