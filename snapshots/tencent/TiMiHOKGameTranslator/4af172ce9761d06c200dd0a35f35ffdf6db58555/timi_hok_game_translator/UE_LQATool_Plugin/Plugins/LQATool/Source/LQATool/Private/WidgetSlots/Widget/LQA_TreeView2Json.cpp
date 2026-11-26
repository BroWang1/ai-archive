#include "WidgetSlots/Widget/LQA_TreeView2Json.h"

#include "Snapshot/LQAWidgetNode.h"

void FLQA_TreeView2Json::ToJson(const TSharedPtr<FLQAWidgetNode> InWidget,
	const TSharedPtr<FJsonObject> OutJsonObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	OutJsonObject->SetStringField(TEXT("WidgetType"), LQAWidgetNames::LQA_TreeView.ToString());

	TArray<TSharedPtr<FJsonValue>> ListItems;
	CollectListEntryTexts(InWidget, ListItems);
	if (ListItems.Num() > 0)
	{
		OutJsonObject->SetArrayField(TEXT("ListItems"), ListItems);
	}
}
