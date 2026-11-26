#include "WidgetSlots/Widgets/LQA_StackBox2Json.h"

#if ENGINE_MAJOR_VERSION >= 5

#include "Components/StackBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_StackBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for StackBox"));
		return nullptr;
	}

	UStackBox* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UStackBox>(ObjectData, UStackBox::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UStackBox>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UStackBox Failed!"));
		return nullptr;
	}
	return Widget;
}

#else

UWidget* FLQA_StackBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	return nullptr;
}

#endif // ENGINE_MAJOR_VERSION >= 5
