#pragma once

#include "Blueprint/IUserObjectListEntry.h"
#include "Blueprint/UserWidget.h"
#include "CoreMinimal.h"
#include "UObject/Object.h"

#include "LQA_ListViewEntry.generated.h"

class UTextBlock;

UCLASS()
class ULQARestoreListItem : public UObject
{
	GENERATED_BODY()

public:
	UPROPERTY()
	FText Label;

	/** 子条目 (TreeView 层级使用) */
	UPROPERTY()
	TArray<ULQARestoreListItem*> Children;
};

/** TreeView 子节点解析器（UObject 实现，兼容 UE4 的 SetOnGetItemChildren 绑定要求） */
UCLASS()
class ULQARestoreTreeChildrenResolver : public UObject
{
	GENERATED_BODY()

public:
	void GetChildren(UObject* Item, TArray<UObject*>& OutChildren);
};

UCLASS()
class ULQARestoreListEntryWidget : public UUserWidget, public IUserObjectListEntry
{
	GENERATED_BODY()

public:
	//~ Begin UUserWidget Interface
	virtual TSharedRef<SWidget> RebuildWidget() override;
	//~ End UUserWidget Interface

protected:
	//~ Begin IUserObjectListEntry Interface
	virtual void NativeOnListItemObjectSet(UObject* ListItemObject) override;
	//~ End IUserObjectListEntry Interface

	/** 条目文本控件 */
	UPROPERTY(Transient)
	UTextBlock* EntryLabel = nullptr;

	/** 条目数据可能在 Slate 控件构建前下发, 先缓存文本待构建时应用 */
	FText CachedLabel;
};
