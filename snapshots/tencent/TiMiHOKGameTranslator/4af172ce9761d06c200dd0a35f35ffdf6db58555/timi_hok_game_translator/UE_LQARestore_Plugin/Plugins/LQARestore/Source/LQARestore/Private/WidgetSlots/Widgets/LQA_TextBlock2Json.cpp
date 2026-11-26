#include "WidgetSlots/Widgets/LQA_TextBlock2Json.h"

#include "Components/TextBlock.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_TextBlock2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for TextBlock"));
		return nullptr;
	}

	UTextBlock* NewTextBlock = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			NewTextBlock = GetAsObject<UTextBlock>(ObjectData, UTextBlock::StaticClass());
		}
	}

	if (NewTextBlock)
	{
		FText Text = GetTextFromJson(JsonData);
		NewTextBlock->SetText(Text);
		return NewTextBlock;
	}
	else
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Restore TextBlock Failed!"));
	}

	return nullptr;
}

ELQAWidgetType FLQA_TextBlock2Json::GetType()
{
	return ELQAWidgetType::LQA_TextBlock;
}