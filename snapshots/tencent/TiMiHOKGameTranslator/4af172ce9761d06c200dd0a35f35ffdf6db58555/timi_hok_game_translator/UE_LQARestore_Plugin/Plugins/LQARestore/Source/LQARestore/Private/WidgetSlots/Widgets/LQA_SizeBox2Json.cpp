#include "WidgetSlots/Widgets/LQA_SizeBox2Json.h"

#include "Components/SizeBox.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

UWidget* FLQA_SizeBox2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for SizeBox"));
		return nullptr;
	}

	USizeBox* SizeBox = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);

		if (ObjectData.IsValid())
		{
			TSharedPtr<FJsonObject> ProcessedObject = MakeShareable(new FJsonObject());
			for (const TPair<FString, TSharedPtr<FJsonValue>>& KeyValuePair : ObjectData->Values)
			{
				const FString& Key = KeyValuePair.Key;
				TSharedPtr<FJsonValue> Value = KeyValuePair.Value;
				if (Key.Contains(TEXT("Mobile")))
				{
					continue;
				}

				FString NewKey = Key;
				if (Key.Contains(TEXT("HD")))
				{
					NewKey = Key.Replace(TEXT("HD"), TEXT(""), ESearchCase::CaseSensitive);
				}

				ProcessedObject->SetField(NewKey, Value);
			}
			SizeBox = GetAsObject<USizeBox>(ProcessedObject, USizeBox::StaticClass());
		}
	}
	else
	{
		SizeBox = NewObject<USizeBox>();
	}

	if (!SizeBox)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore USizeBox Failed!"));
		return nullptr;
	}
	return SizeBox;
}
