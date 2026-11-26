#include "WidgetSlots/Widgets/LQA_WrapBox2Json.h"

#include "Components/WrapBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_WrapBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for WrapBox"));
		return nullptr;
	}

	UWrapBox* WrapBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			WrapBox = GetAsObject<UWrapBox>(ObjectData, UWrapBox::StaticClass());
		}
	}
	else
	{
		WrapBox = NewObject<UWrapBox>();
	}

	if (!WrapBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UWrapBox Failed!"));
		return nullptr;
	}
	return WrapBox;
}
