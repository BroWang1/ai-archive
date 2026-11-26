#include "WidgetSlots/Widgets/LQA_UniformGridPanel2Json.h"

#include "Components/UniformGridPanel.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_UniformGridPanel2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for UniformGridPanel"));
		return nullptr;
	}

	UUniformGridPanel* UniformGridPanel = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			UniformGridPanel = GetAsObject<UUniformGridPanel>(ObjectData, UUniformGridPanel::StaticClass());
		}
	}
	else
	{
		UniformGridPanel = NewObject<UUniformGridPanel>();
	}

	if (!UniformGridPanel)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UUniformGridPanel Failed!"));
		return nullptr;
	}
	return UniformGridPanel;
}
