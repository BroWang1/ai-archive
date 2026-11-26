#include "WidgetSlots/Widget/LQA_CircularThrobber2Json.h"

#include "Components/CircularThrobber.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQATextureUtil.h"

void FLQA_CircularThrobber2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_CircularThrobber.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		if (const UCircularThrobber* CircularThrobberIns = Cast<UCircularThrobber>(InWidget->SourceObject.Get()))
		{
#if ENGINE_MAJOR_VERSION >= 5
			UObject* ResourceObject = CircularThrobberIns->GetImage().GetResourceObject();
#else
			UObject* ResourceObject = CircularThrobberIns->Image.GetResourceObject();
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
