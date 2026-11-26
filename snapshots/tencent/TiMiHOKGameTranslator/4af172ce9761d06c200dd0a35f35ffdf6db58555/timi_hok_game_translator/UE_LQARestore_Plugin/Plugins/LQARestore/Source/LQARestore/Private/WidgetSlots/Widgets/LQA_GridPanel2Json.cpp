#include "WidgetSlots/Widgets/LQA_GridPanel2Json.h"

#include "Components/GridPanel.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_GridPanel2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for GridPanel"));
		return nullptr;
	}

	UGridPanel* GridPanel = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			GridPanel = GetAsObject<UGridPanel>(ObjectData, UGridPanel::StaticClass());
		}
	}
	else
	{
		GridPanel = NewObject<UGridPanel>();
	}

	if (!GridPanel)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UGridPanel Failed!"));
		return nullptr;
	}
	return GridPanel;
}
