#include "WidgetSlots/Widgets/LQA_Image2Json.h"

#include "Components/Image.h"
#include "Core/RestoreWindowUtils.h"
#include "Engine/Texture2D.h"
#include "Utils/TextureUtils.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_Image2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for Image"));
		return nullptr;
	}

	TSharedPtr<FJsonObject> TextureData;
	UImage* NewImage = nullptr;
	FString ResourceName;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewImage = GetAsObject<UImage>(ObjectData, UImage::StaticClass());
			if (!ObjectData->HasField(TEXT("Brush")))
			{
				return nullptr;
			}

			if (JsonData->HasField(TEXT("TextureData")))
			{
				TextureData = JsonData->GetObjectField(TEXT("TextureData"));
				const TSharedPtr<FJsonObject> BrushData = ObjectData->GetObjectField(TEXT("Brush"));
				TextureData->SetObjectField(TEXT("Brush"), BrushData);

				if (BrushData->HasField(TEXT("resourceObject")))
				{
					ResourceName = BrushData->GetStringField(TEXT("resourceObject"));
					TextureData->SetStringField(TEXT("resourceObject"), ResourceName);
				}
			}
		}
	}

	if (!NewImage)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore Image Failed!"));
		return nullptr;
	}

	if (TextureData.IsValid() && ResourceName != "")
	{
		FTextureUtils::UpdateImageBrushFromJsonObj(NewImage, TextureData, RestoreWindowProxy);
		// FTextureUtils::SetImageBrushFromJsonObj(NewImage, TextureData, RestoreWindowProxy);
		NewImage->SynchronizeProperties();
	}

	return NewImage;
}

ELQAWidgetType FLQA_Image2Json::GetType()
{
	return ELQAWidgetType::LQA_Image;
}
