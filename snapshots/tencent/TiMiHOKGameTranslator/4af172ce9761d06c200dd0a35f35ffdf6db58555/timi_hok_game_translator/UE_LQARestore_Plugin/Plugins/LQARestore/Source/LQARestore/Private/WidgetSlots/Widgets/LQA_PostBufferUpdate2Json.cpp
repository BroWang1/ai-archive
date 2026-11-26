#include "WidgetSlots/Widgets/LQA_PostBufferUpdate2Json.h"

#if ENGINE_MAJOR_VERSION >= 5

#include "Components/PostBufferUpdate.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_PostBufferUpdate2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for PostBufferUpdate"));
		return nullptr;
	}

	UPostBufferUpdate* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UPostBufferUpdate>(ObjectData, UPostBufferUpdate::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UPostBufferUpdate>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UPostBufferUpdate Failed!"));
		return nullptr;
	}

	return Widget;
}

ELQAWidgetType FLQA_PostBufferUpdate2Json::GetType()
{
	return ELQAWidgetType::LQA_PostBufferUpdate;
}

#else

// UE4.27 无 UPostBufferUpdate，提供空实现保证注册表链接通过
UWidget* FLQA_PostBufferUpdate2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	return nullptr;
}

ELQAWidgetType FLQA_PostBufferUpdate2Json::GetType()
{
	return ELQAWidgetType::LQA_PostBufferUpdate;
}

#endif // ENGINE_MAJOR_VERSION >= 5
