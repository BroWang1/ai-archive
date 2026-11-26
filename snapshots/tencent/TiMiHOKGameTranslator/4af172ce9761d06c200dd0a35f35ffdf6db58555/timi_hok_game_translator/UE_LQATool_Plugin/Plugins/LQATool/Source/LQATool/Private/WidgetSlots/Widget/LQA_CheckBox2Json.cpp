#include "WidgetSlots/Widget/LQA_CheckBox2Json.h"

#include "Components/CheckBox.h"
#include "Snapshot/LQAWidgetNode.h"
#include "Utils/LQAJsonUtils.h"
#include "Utils/LQATextureUtil.h"

void FLQA_CheckBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_CheckBox.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const UCheckBox* CheckBox = Cast<UCheckBox>(InWidget->SourceObject);
		if (CheckBox)
		{
#if ENGINE_MAJOR_VERSION >= 5
			UObject* ResourceObject = CheckBox->GetWidgetStyle().UncheckedImage.GetResourceObject();
#else
			UObject* ResourceObject = CheckBox->WidgetStyle.UncheckedImage.GetResourceObject();
#endif
			if (ResourceObject)
			{
				OutJsonObject->SetObjectField(
					TEXT("TextureData"), FLQATextureUtil::GetTextureJsonObj(ResourceObject, SharedTextureMap));
			}
		}
	}
}
