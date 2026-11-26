#include "WidgetSlots/Widgets/LQA_RichTextBlock2Json.h"

#include "Components/RichTextBlock.h"
#include "Engine/DataTable.h"
#include "Utils/JsonUtils.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

namespace
{
UDataTable* RestoreRichTextStyleSet(const TSharedPtr<FJsonObject>& JsonData)
{
	if (!JsonData.IsValid() || !JsonData->HasField(TEXT("RichTextStyleSetData")))
	{
		return nullptr;
	}

	const TSharedPtr<FJsonObject> StyleSetObject = JsonData->GetObjectField(TEXT("RichTextStyleSetData"));
	if (!StyleSetObject.IsValid())
	{
		return nullptr;
	}

	UDataTable* Table = NewObject<UDataTable>();
	Table->RowStruct = FRichTextStyleRow::StaticStruct();

	for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : StyleSetObject->Values)
	{
		const TSharedPtr<FJsonObject> RowObject = Pair.Value.IsValid() ? Pair.Value->AsObject() : nullptr;
		if (!RowObject.IsValid())
		{
			continue;
		}

		FRichTextStyleRow Row;
		// 字段名大小写对齐到反射属性名, 保证反序列化命中
		FJsonUtils::StandardizeCaseForImport(RowObject, FRichTextStyleRow::StaticStruct());
		if (FJsonObjectConverter::JsonObjectToUStruct(
				RowObject.ToSharedRef(), FRichTextStyleRow::StaticStruct(), &Row, 0, 0))
		{
			Table->AddRow(FName(*Pair.Key), Row);
		}
	}

	return Table->GetRowMap().Num() > 0 ? Table : nullptr;
}
}  // namespace

UWidget* FLQA_RichTextBlock2Json::FromJson(
	const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for RichTextBlock"));
		return nullptr;
	}

	URichTextBlock* NewTextBlock = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			// Use the TextStyleSet carried by the snapshot JSON (no hardcoded project asset path)
			NewTextBlock = GetAsObject<URichTextBlock>(ObjectData, URichTextBlock::StaticClass());
		}
	}

	if (NewTextBlock)
	{
		// 样式表若未能随对象路径加载 (Transient 路径在还原环境不存在), 则从快照数据重建
#if ENGINE_MAJOR_VERSION >= 5
		if (!NewTextBlock->GetTextStyleSet())
		{
			NewTextBlock->SetTextStyleSet(RestoreRichTextStyleSet(JsonData));
		}
#else
		NewTextBlock->SetTextStyleSet(RestoreRichTextStyleSet(JsonData));
#endif

		const FText Text = GetTextFromJson(JsonData);
		NewTextBlock->SetText(Text);

		return NewTextBlock;
	}
	else
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Restore RichTextBlock Failed!"));
	}

	return nullptr;
}

ELQAWidgetType FLQA_RichTextBlock2Json::GetType()
{
	return ELQAWidgetType::LQA_RichText;
}