#include "WidgetSlots/Widget/LQA_ProgressBar2Json.h"

#include "Components/ProgressBar.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQATextureUtil.h"

void FLQA_ProgressBar2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_ProgressBar.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		if (const UProgressBar* ProgressBar = Cast<UProgressBar>(InWidget->SourceObject.Get()))
		{
#if ENGINE_MAJOR_VERSION >= 5
			UObject* ResourceObject = ProgressBar->GetWidgetStyle().FillImage.GetResourceObject();
#else
			UObject* ResourceObject = ProgressBar->WidgetStyle.FillImage.GetResourceObject();
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
