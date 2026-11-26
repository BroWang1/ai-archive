#include "WidgetSlots/Widget/LQA_Throbber2Json.h"

#include "Components/Throbber.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQATextureUtil.h"

void FLQA_Throbber2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_Throbber.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		if (const UThrobber* ThrobberIns = Cast<UThrobber>(InWidget->SourceObject.Get()))
		{
#if ENGINE_MAJOR_VERSION >= 5
			UObject* ResourceObject = ThrobberIns->GetImage().GetResourceObject();
#else
			UObject* ResourceObject = ThrobberIns->Image.GetResourceObject();
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
