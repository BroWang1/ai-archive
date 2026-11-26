#pragma once

#include "Blueprint/IUserObjectListEntry.h"
#include "Blueprint/UserWidget.h"
#include "Components/ListView.h"
#include "Components/TileView.h"
#include "Components/TreeView.h"
#include "CoreMinimal.h"

#include "LQAGalleryWidgetItem.generated.h"

class UBorder;
class UButton;
class UHorizontalBox;
class UPanelWidget;
class UTextBlock;
class UVerticalBox;

/**
 * LQA 验证画廊的子控件集合（UE5 版本），与 ULQAGalleryWidget_UE5 配套使用。
 *
 * 约束：纯 C++ 构造，不新增资产；文本只能取自 LQAGalleryText。
 */

// ===========================================================================
// 1. 列表项数据
// ===========================================================================

/** 列表项数据对象：承载条目文本与配色 */
UCLASS()
class ULQAGalleryListItem : public UObject
{
	GENERATED_BODY()

public:
	UPROPERTY()
	FText Label;

	/** 条目文本是否自动换行（默认 true；BUG 示例置 false 制造溢出） */
	UPROPERTY()
	bool bAutoWrapText = true;

	/** 条目文本颜色（由画廊按当前主题写入） */
	UPROPERTY()
	FLinearColor TextColor = FLinearColor::White;
};

// ===========================================================================
// 2. 列表派生类
// ===========================================================================

/** 画廊 ListView：构造期指定 EntryWidgetClass（引擎中该成员为 protected，无 setter） */
UCLASS()
class ULQAGalleryListView : public UListView
{
	GENERATED_BODY()

public:
	ULQAGalleryListView(const FObjectInitializer& ObjectInitializer);
};

/** 画廊 TileView：同 ULQAGalleryListView，用于设置 EntryWidgetClass */
UCLASS()
class ULQAGalleryTileView : public UTileView
{
	GENERATED_BODY()

public:
	ULQAGalleryTileView(const FObjectInitializer& ObjectInitializer);
};

/** 画廊 TreeView：同 ULQAGalleryListView，用于设置 EntryWidgetClass */
UCLASS()
class ULQAGalleryTreeView : public UTreeView
{
	GENERATED_BODY()

public:
	ULQAGalleryTreeView(const FObjectInitializer& ObjectInitializer);
};

// ===========================================================================
// 3. 列表条目
// ===========================================================================

/** 画廊列表条目，作为列表三件套的 EntryWidgetClass */
UCLASS()
class ULQAGalleryEntryWidget : public UUserWidget, public IUserObjectListEntry
{
	GENERATED_BODY()

public:
	virtual TSharedRef<SWidget> RebuildWidget() override;

protected:
	/** 绑定所属列表项数据（ULQAGalleryListItem::Label） */
	virtual void NativeOnListItemObjectSet(UObject* ListItemObject) override;

	UPROPERTY(Transient)
	UTextBlock* EntryLabel = nullptr;
};

/** 画廊动态条目框条目，由 UDynamicEntryBox::CreateEntry 创建 */
UCLASS()
class ULQAGalleryDynamicEntryWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual TSharedRef<SWidget> RebuildWidget() override;

	/** 设置条目文本；控件尚未构建时先缓存，构建后应用 */
	void SetEntryText(const FText& InText);

protected:
	UPROPERTY(Transient)
	UTextBlock* EntryLabel = nullptr;

	/** 待应用文本（控件未构建时缓存） */
	FText PendingText;
};

// ===========================================================================
// 4. 菜单内容
// ===========================================================================

/** 画廊菜单内容，由 UMenuAnchor::MenuClass 引用 */
UCLASS()
class ULQAGalleryMenuWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual TSharedRef<SWidget> RebuildWidget() override;

protected:
	/** 按钮 1 点击（仅用于构成可交互控件，不做业务处理） */
	UFUNCTION()
	void OnFirstButtonClicked();

	/** 按钮 2 点击（仅用于构成可交互控件，不做业务处理） */
	UFUNCTION()
	void OnSecondButtonClicked();

	/** 使用已登记文本构造一个按钮 */
	UButton* MakeMenuButton(UPanelWidget* Parent, const FText& Label, bool bFirst);

	UPROPERTY(Transient)
	UVerticalBox* MenuBox = nullptr;

	UPROPERTY(Transient)
	UTextBlock* MenuLabel = nullptr;

	UPROPERTY(Transient)
	UButton* FirstButton = nullptr;

	UPROPERTY(Transient)
	UButton* SecondButton = nullptr;
};

// ===========================================================================
// 5. 嵌套子 UserWidget
// ===========================================================================

/** 画廊嵌套子 UserWidget，由画廊 CreateWidget 动态创建 */
UCLASS()
class ULQAGalleryChildWidget : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual TSharedRef<SWidget> RebuildWidget() override;

	/** 按主题设置标签与图标颜色 */
	void SetThemeColors(const FLinearColor& InLabelColor, const FLinearColor& InIconColor);

protected:
	UPROPERTY(Transient)
	UHorizontalBox* ChildBox = nullptr;

	/** 图标位（纯色块，避免依赖任何贴图资产） */
	UPROPERTY(Transient)
	UBorder* ChildIcon = nullptr;

	UPROPERTY(Transient)
	UTextBlock* ChildLabel = nullptr;

	/** 标签颜色（子控件未构建时先缓存） */
	FLinearColor LabelColor = FLinearColor::White;

	/** 图标颜色（子控件未构建时先缓存） */
	FLinearColor IconColor = FLinearColor(0.20f, 0.60f, 0.90f, 1.f);
};
