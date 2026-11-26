#include "WidgetSlots/Widget/LQA_RichTextBlock2Json.h"

#include "Engine/DataTable.h"
#include "Snapshot/LQAWidgetNode.h"
#include "UObject/UnrealType.h"

namespace
{
void SerializeRichTextStyleSet(const URichTextBlock* RichTextBlock, const TSharedPtr<FJsonObject>& OutJsonObject)
{
	if (!RichTextBlock || !OutJsonObject.IsValid())
	{
		return;
	}

#if ENGINE_MAJOR_VERSION >= 5
	const UDataTable* StyleSet = RichTextBlock->GetTextStyleSet();
#else
	const UDataTable* StyleSet = nullptr;
	const FObjectProperty* TextStyleSetProp =
		FindFProperty<FObjectProperty>(URichTextBlock::StaticClass(), TEXT("TextStyleSet"));
	if (TextStyleSetProp)
	{
		StyleSet = Cast<UDataTable>(TextStyleSetProp->GetObjectPropertyValue_InContainer(RichTextBlock));
	}
#endif
	if (!StyleSet || StyleSet->GetRowStruct() != FRichTextStyleRow::StaticStruct())
	{
		return;
	}

	TSharedPtr<FJsonObject> StyleSetObject = MakeShared<FJsonObject>();
	for (const TPair<FName, uint8*>& RowPair : StyleSet->GetRowMap())
	{
		const auto* Row = reinterpret_cast<const FRichTextStyleRow*>(RowPair.Value);
		if (!Row)
		{
			continue;
		}

		TSharedRef<FJsonObject> RowObject = MakeShared<FJsonObject>();
		if (FJsonObjectConverter::UStructToJsonObject(FRichTextStyleRow::StaticStruct(), Row, RowObject, 0, 0))
		{
			StyleSetObject->SetObjectField(RowPair.Key.ToString(), RowObject);
		}
	}

	if (StyleSetObject->Values.Num() > 0)
	{
		OutJsonObject->SetObjectField(TEXT("RichTextStyleSetData"), StyleSetObject);
	}
}
}  // namespace

void FLQA_RichTextBlock2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_RichTextBlock.ToString());

	if (InWidget->SourceObject.IsValid())
	{
		const URichTextBlock* TextBlockIns = Cast<URichTextBlock>(InWidget->SourceObject);
		if (TextBlockIns)
		{
			const FText Text = TextBlockIns->GetText();

			UE_LOG(LogLQAToolWidget2Json, Verbose, TEXT("Find Text Block Content = %s"), *Text.ToString());
			WriteTextEntry_ToJson(OutJsonObject, Text);

			// 样式表是运行时 Transient 对象, 序列化其行内容供还原端重建
			SerializeRichTextStyleSet(TextBlockIns, OutJsonObject);
		}
	}
}
