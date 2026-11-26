#include "WidgetSlots/Widgets/LQA_TextScroller2Json.h"

#include "Components/TextBlock.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_TextScroller2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for TextScroller"));
		return nullptr;
	}

	UTextBlock* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UTextBlock>(ObjectData, UTextBlock::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UTextBlock>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UTextBlock Failed!"));
		return nullptr;
	}
	return Widget;
}