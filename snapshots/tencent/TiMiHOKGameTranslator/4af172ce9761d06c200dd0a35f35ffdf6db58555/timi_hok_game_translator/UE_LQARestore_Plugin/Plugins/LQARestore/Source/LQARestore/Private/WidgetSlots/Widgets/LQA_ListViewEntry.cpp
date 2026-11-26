#include "WidgetSlots/Widgets/LQA_ListViewEntry.h"

#include "Blueprint/WidgetTree.h"
#include "Components/TextBlock.h"

TSharedRef<SWidget> ULQARestoreListEntryWidget::RebuildWidget()
{
	// 列表条目只有一个 TextBlock, 首次构建时创建根控件
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		EntryLabel = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("LQA_Restore_Entry_Label"));
		if (EntryLabel)
		{
			EntryLabel->SetText(CachedLabel);
			WidgetTree->RootWidget = EntryLabel;
		}
	}

	return Super::RebuildWidget();
}

void ULQARestoreListEntryWidget::NativeOnListItemObjectSet(UObject* ListItemObject)
{
	IUserObjectListEntry::NativeOnListItemObjectSet(ListItemObject);

	// 条目控件会被列表复用, 每次绑定数据时都刷新文本
	const ULQARestoreListItem* ListItem = Cast<ULQARestoreListItem>(ListItemObject);
	CachedLabel = ListItem ? ListItem->Label : FText::GetEmpty();

	if (EntryLabel)
	{
		EntryLabel->SetText(CachedLabel);
	}
}
