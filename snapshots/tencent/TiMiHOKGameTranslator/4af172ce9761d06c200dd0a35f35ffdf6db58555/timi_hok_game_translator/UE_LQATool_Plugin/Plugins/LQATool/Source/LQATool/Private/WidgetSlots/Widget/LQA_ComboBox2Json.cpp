#include "WidgetSlots/Widget/LQA_ComboBox2Json.h"

#include "Components/ComboBoxString.h"
#include "Snapshot/LQAWidgetNode.h"
#include "WidgetSlots/WidgetDefines.h"

void FLQA_ComboBox2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
	TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_ComboBox.ToString());

	if (!InWidget->SourceObject.IsValid())
	{
		return;
	}

	UObject* SourceObj = InWidget->SourceObject.Get();

	const UComboBoxString* ComboBoxStringIns = Cast<UComboBoxString>(SourceObj);
	if (!ComboBoxStringIns)
	{
		return;
	}

	TArray<TSharedPtr<FJsonValue>> OptionJsonArray;
	const int32 OptionCount = ComboBoxStringIns->GetOptionCount();
	OptionJsonArray.Reserve(OptionCount);
	for (int32 Index = 0; Index < OptionCount; ++Index)
	{
		OptionJsonArray.Emplace(MakeShared<FJsonValueString>(ComboBoxStringIns->GetOptionAtIndex(Index)));
	}
	OutJsonObject->SetArrayField(TEXT("OptionStrings"), OptionJsonArray);

	const FString SelectedOption = ComboBoxStringIns->GetSelectedOption();
	if (!SelectedOption.IsEmpty())
	{
		OutJsonObject->SetStringField(*CommonStrKey, SelectedOption);
	}
}
