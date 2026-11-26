#include "WidgetSlots/Widgets/LQA_CircularThrobber2Json.h"

#include "Components/CircularThrobber.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_CircularThrobber2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for CircularThrobber"));
		return nullptr;
	}

	UCircularThrobber* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UCircularThrobber>(ObjectData, UCircularThrobber::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UCircularThrobber>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UCircularThrobber Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_CircularThrobber2Json::GetType()
{
	return ELQAWidgetType::LQA_CircularThrobber;
}
