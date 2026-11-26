#include "WidgetSlots/Widgets/LQA_ExpandableArea2Json.h"

#include "Components/ExpandableArea.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_ExpandableArea2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for ExpandableArea"));
		return nullptr;
	}

	UExpandableArea* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<UExpandableArea>(ObjectData, UExpandableArea::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<UExpandableArea>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UExpandableArea Failed!"));
		return nullptr;
	}
	return Widget;
}
