#include "WidgetSlots/Widget/LQA_Button2Json.h"

#include "Components/Button.h"
#include "Engine/Texture2D.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQAJsonUtils.h"
#include "Utils/LQATextureUtil.h"

void FLQA_Button2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Button.ToString());
	if (InWidget->SourceObject.IsValid())
	{
		const UButton* Button = Cast<UButton>(InWidget->SourceObject);
		if (Button)
		{
			// 记录Brush
#if ENGINE_MAJOR_VERSION >= 5
			UObject* ResourceObject = Button->GetStyle().Normal.GetResourceObject();
			FVector2D ImageSize = Button->GetStyle().Normal.ImageSize;
#else
			UObject* ResourceObject = Button->WidgetStyle.Normal.GetResourceObject();
			FVector2D ImageSize = Button->WidgetStyle.Normal.ImageSize;
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
