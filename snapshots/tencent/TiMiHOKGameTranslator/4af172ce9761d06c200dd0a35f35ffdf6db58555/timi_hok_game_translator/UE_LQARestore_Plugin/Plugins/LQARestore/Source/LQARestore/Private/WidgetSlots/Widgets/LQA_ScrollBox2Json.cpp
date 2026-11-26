#include "WidgetSlots/Widgets/LQA_ScrollBox2Json.h"

#include "Components/ScrollBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_ScrollBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for ScrollBox"));
		return nullptr;
	}

	UScrollBox* ScrollBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			ScrollBox = GetAsObject<UScrollBox>(ObjectData, UScrollBox::StaticClass());
		}
	}
	else
	{
		ScrollBox = NewObject<UScrollBox>();
	}

	if (!ScrollBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UScrollBox Failed!"));
		return nullptr;
	}

	if (JsonData->HasField(TEXT("ScrollOffset")))
	{
		ScrollBox->SetScrollOffset(JsonData->GetNumberField(TEXT("ScrollOffset")));
	}

	return ScrollBox;
}
