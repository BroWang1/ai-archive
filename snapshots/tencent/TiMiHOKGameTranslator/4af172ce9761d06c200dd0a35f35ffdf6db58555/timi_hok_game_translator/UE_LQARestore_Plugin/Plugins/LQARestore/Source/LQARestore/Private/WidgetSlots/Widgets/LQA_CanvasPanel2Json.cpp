#include "WidgetSlots/Widgets/LQA_CanvasPanel2Json.h"

#include "Components/CanvasPanel.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_CanvasPanel2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for CanvasPanel"));
		return nullptr;
	}

	UCanvasPanel* CanvasPanel = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			CanvasPanel = GetAsObject<UCanvasPanel>(ObjectData, UCanvasPanel::StaticClass());
		}
	}
	else
	{
		CanvasPanel = NewObject<UCanvasPanel>();
	}

	if (!CanvasPanel)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore CanvasPanel Failed!"));
		return nullptr;
	}
	return CanvasPanel;
}
