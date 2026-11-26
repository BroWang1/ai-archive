#include "WidgetSlots/Widgets/LQA_Button2Json.h"

#include "Components/Button.h"
#include "Core/RestoreWindowUtils.h"
#include "Engine/Texture2D.h"
#include "Utils/TextureUtils.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_Button2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for Button"));
		return nullptr;
	}

	UButton* NewButton = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewButton = GetAsObject<UButton>(ObjectData, UButton::StaticClass());
			NewButton->PostLoad();
		}
	}

	if (!NewButton)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore Button Failed!"));
		return nullptr;
	}

	const TSharedPtr<FJsonObject> TextureData = JsonData->GetObjectField(TEXT("TextureData"));
	UTexture2D* NewTexture = FTextureUtils::GetTextureFromJsonObj(TextureData, RestoreWindowProxy);
	// UTexture2D* NewTexture = FTextureUtils::GetTextureFromMergedTexture(JsonData, TextureName);
	if (NewTexture)
	{
		FSlateBrush Brush;
		Brush.SetResourceObject(NewTexture);

		NewTexture->bForceMiplevelsToBeResident = true;
		NewTexture->bIgnoreStreamingMipBias = true;

		FButtonStyle ButtonStyle;
		ButtonStyle.SetNormal(Brush);
		ButtonStyle.SetPressed(Brush);
		ButtonStyle.SetDisabled(Brush);
		ButtonStyle.SetHovered(Brush);

		NewButton->SetStyle(ButtonStyle);
	}
	return NewButton;
}

ELQAWidgetType FLQA_Button2Json::GetType()
{
	return ELQAWidgetType::LQA_Button;
}