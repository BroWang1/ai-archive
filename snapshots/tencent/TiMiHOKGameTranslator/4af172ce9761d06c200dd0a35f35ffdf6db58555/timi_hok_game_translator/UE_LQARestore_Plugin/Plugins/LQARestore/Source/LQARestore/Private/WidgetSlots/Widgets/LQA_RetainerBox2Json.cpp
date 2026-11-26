#include "WidgetSlots/Widgets/LQA_RetainerBox2Json.h"

#include "Components/RetainerBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_RetainerBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for RetainerBox"));
		return nullptr;
	}

	URetainerBox* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = GetAsObject<URetainerBox>(ObjectData, URetainerBox::StaticClass());
		}
	}
	else
	{
		Widget = NewObject<URetainerBox>();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore URetainerBox Failed!"));
		return nullptr;
	}
	return Widget;
}

ELQAWidgetType FLQA_RetainerBox2Json::GetType()
{
	return ELQAWidgetType::LQA_RetainerBox;
}
