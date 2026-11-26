#include "WidgetSlots/Widgets/LQA_ScaleBox2Json.h"

#include "Components/ScaleBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_ScaleBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for ScaleBox"));
		return nullptr;
	}

	UScaleBox* ScaleBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			ScaleBox = GetAsObject<UScaleBox>(ObjectData, UScaleBox::StaticClass());
		}
	}
	else
	{
		ScaleBox = NewObject<UScaleBox>();
	}

	if (!ScaleBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UScaleBox Failed!"));
		return nullptr;
	}
	return ScaleBox;
}
