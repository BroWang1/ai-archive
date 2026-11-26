#include "WidgetSlots/Widgets/LQA_Throbber2Json.h"

#include "Components/Throbber.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_Throbber2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for Throbber"));
		return nullptr;
	}

	UThrobber* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UThrobber>(ObjectData, UThrobber::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UThrobber>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UThrobber Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_Throbber2Json::GetType()
{
	return ELQAWidgetType::LQA_Throbber;
}
