#include "WidgetSlots/Widgets/LQA_HorizontalBox2Json.h"

#include "Components/HorizontalBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_HorizontalBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for HorizontalBox"));
		return nullptr;
	}

	UHorizontalBox* HorizontalBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			HorizontalBox = GetAsObject<UHorizontalBox>(ObjectData, UHorizontalBox::StaticClass());
		}
	}
	else
	{
		HorizontalBox = NewObject<UHorizontalBox>();
	}

	if (!HorizontalBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UHorizontalBox Failed!"));
		return nullptr;
	}
	return HorizontalBox;
}
