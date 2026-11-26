#include "WidgetSlots/Widgets/LQA_VerticalBox2Json.h"

#include "Components/VerticalBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_VerticalBox2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for VerticalBox"));
		return nullptr;
	}

	UVerticalBox* VerticalBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			VerticalBox = GetAsObject<UVerticalBox>(ObjectData, UVerticalBox::StaticClass());
		}
	}
	else
	{
		VerticalBox = NewObject<UVerticalBox>();
	}

	if (!VerticalBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UVerticalBox Failed!"));
		return nullptr;
	}
	return VerticalBox;
}
