#include "Validation/LQAGalleryWidgetItem.h"

#include "Blueprint/WidgetTree.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/SizeBox.h"
#include "Components/TextBlock.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Runtime/Launch/Resources/Version.h"
#include "Validation/LQAGalleryWidgetText.h"
#include "Validation/LQAGalleryWidget_UE5.h"

#if ENGINE_MAJOR_VERSION < 5 && WITH_EDITOR
#include "Engine/Blueprint.h"
#endif

namespace
{
void MarkEntryClassCooked()
{
	UClass* EntryClass = ULQAGalleryEntryWidget::StaticClass();
	EntryClass->bCooked = true;

#if ENGINE_MAJOR_VERSION < 5 && WITH_EDITOR
	if (!EntryClass->ClassGeneratedBy)
	{
		EntryClass->ClassGeneratedBy = NewObject<UBlueprint>(GetTransientPackage(), NAME_None, RF_Transient);
	}
#endif
}
}

// ===========================================================================
// 列表派生类：构造期指定 EntryWidgetClass（该成员为 protected，无 setter）
// ===========================================================================

ULQAGalleryListView::ULQAGalleryListView(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	MarkEntryClassCooked();
	EntryWidgetClass = ULQAGalleryEntryWidget::StaticClass();
}

ULQAGalleryTileView::ULQAGalleryTileView(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	MarkEntryClassCooked();
	EntryWidgetClass = ULQAGalleryEntryWidget::StaticClass();

	// 瓷砖尺寸：宽度需容纳条目文本，避免相邻 tile 内容溢出重叠
	SetEntryWidth(200.f);
	SetEntryHeight(28.f);
}

ULQAGalleryTreeView::ULQAGalleryTreeView(const FObjectInitializer& ObjectInitializer)
	: Super(ObjectInitializer)
{
	MarkEntryClassCooked();
	EntryWidgetClass = ULQAGalleryEntryWidget::StaticClass();
}

// ===========================================================================
// 列表条目
// ===========================================================================

TSharedRef<SWidget> ULQAGalleryEntryWidget::RebuildWidget()
{
	// 纯 C++ 构造条目内容：单个 TextBlock
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		EntryLabel = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("Gallery_Entry_Label"));
		EntryLabel->SetText(LQAGalleryWidgetText::ContentTextBlock());
		WidgetTree->RootWidget = EntryLabel;
	}

	return Super::RebuildWidget();
}

void ULQAGalleryEntryWidget::NativeOnListItemObjectSet(UObject* ListItemObject)
{
	IUserObjectListEntry::NativeOnListItemObjectSet(ListItemObject);

	if (!EntryLabel)
	{
		return;
	}

	// 文本来源：列表项数据（由画廊构造时用 LQAGalleryText 常量填充）
	const ULQAGalleryListItem* ListItem = Cast<ULQAGalleryListItem>(ListItemObject);
	EntryLabel->SetText(ListItem ? ListItem->Label : LQAGalleryWidgetText::ContentTextBlock());
	EntryLabel->SetAutoWrapText(ListItem ? ListItem->bAutoWrapText : true);
	EntryLabel->SetColorAndOpacity(FSlateColor(ListItem ? ListItem->TextColor : FLinearColor::White));
}

// ===========================================================================
// 动态条目框条目
// ===========================================================================

TSharedRef<SWidget> ULQAGalleryDynamicEntryWidget::RebuildWidget()
{
	// 纯 C++ 构造条目内容：单个 TextBlock
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		EntryLabel = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(),
			TEXT("Gallery_DynamicEntry_Label"));
		EntryLabel->SetText(PendingText.IsEmpty() ? LQAGalleryWidgetText::DynamicEntryBoxText(1) : PendingText);
		WidgetTree->RootWidget = EntryLabel;
	}

	return Super::RebuildWidget();
}

void ULQAGalleryDynamicEntryWidget::SetEntryText(const FText& InText)
{
	PendingText = InText;

	if (EntryLabel)
	{
		EntryLabel->SetText(InText);
	}
}

// ===========================================================================
// 菜单内容
// ===========================================================================

UButton* ULQAGalleryMenuWidget::MakeMenuButton(UPanelWidget* Parent, const FText& Label, bool bFirst)
{
	UButton* Button = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass());
	UTextBlock* ButtonText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass());
	ButtonText->SetText(Label);
	ButtonText->SetColorAndOpacity(FSlateColor(FLQAGalleryTheme::ControlText()));
	Button->AddChild(ButtonText);

	if (Parent)
	{
		if (UVerticalBoxSlot* ButtonSlot = Cast<UVerticalBoxSlot>(Parent->AddChild(Button)))
		{
			ButtonSlot->SetPadding(FMargin(0.f, 2.f));
		}
	}

	if (bFirst)
	{
		Button->OnClicked.AddDynamic(this, &ULQAGalleryMenuWidget::OnFirstButtonClicked);
		FirstButton = Button;
	}
	else
	{
		Button->OnClicked.AddDynamic(this, &ULQAGalleryMenuWidget::OnSecondButtonClicked);
		SecondButton = Button;
	}

	return Button;
}

TSharedRef<SWidget> ULQAGalleryMenuWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		MenuBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("Gallery_Menu_Box"));

		MenuLabel = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("Gallery_Menu_Label"));
		MenuLabel->SetText(LQAGalleryWidgetText::ContentTextBlock());
		MenuLabel->SetColorAndOpacity(FSlateColor(FLQAGalleryTheme::Dark().TextOnPanel));
		if (UVerticalBoxSlot* LabelSlot = MenuBox->AddChildToVerticalBox(MenuLabel))
		{
			LabelSlot->SetPadding(FMargin(4.f, 2.f));
		}

		MakeMenuButton(MenuBox, LQAGalleryWidgetText::ContentButton(), true);
		MakeMenuButton(MenuBox, LQAGalleryWidgetText::ContentButton(), false);

		// 菜单弹层固定深色底，不随主题切换
		UBorder* PopupBorder = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("Gallery_Menu_Border"));
		PopupBorder->SetBrushColor(FLQAGalleryTheme::Dark().BarBackground);
		PopupBorder->SetPadding(FMargin(4.f));
		PopupBorder->SetContent(MenuBox);

		WidgetTree->RootWidget = PopupBorder;
	}

	return Super::RebuildWidget();
}

void ULQAGalleryMenuWidget::OnFirstButtonClicked()
{
	UE_LOG(LogTemp, Verbose, TEXT("[LQAGallery] Menu button 1 clicked."));
}

void ULQAGalleryMenuWidget::OnSecondButtonClicked()
{
	UE_LOG(LogTemp, Verbose, TEXT("[LQAGallery] Menu button 2 clicked."));
}

// ===========================================================================
// 嵌套子 UserWidget
// ===========================================================================

TSharedRef<SWidget> ULQAGalleryChildWidget::RebuildWidget()
{
	if (WidgetTree && !WidgetTree->RootWidget)
	{
		ChildBox = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("Gallery_Child_Box"));

		// 图标：纯色块（固定 24x24），避免引入贴图资产
		USizeBox* IconSizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		IconSizeBox->SetMinDesiredWidth(24.f);
		IconSizeBox->SetMinDesiredHeight(24.f);
		ChildIcon = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("Gallery_Child_Icon"));
		ChildIcon->SetBrushColor(IconColor);
		IconSizeBox->AddChild(ChildIcon);

		if (UHorizontalBoxSlot* IconSlot = ChildBox->AddChildToHorizontalBox(IconSizeBox))
		{
			IconSlot->SetPadding(FMargin(0.f, 0.f, 8.f, 0.f));
			IconSlot->SetVerticalAlignment(VAlign_Center);
		}

		ChildLabel = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("Gallery_Child_Label"));
		ChildLabel->SetText(LQAGalleryWidgetText::ContentTextBlock());
		ChildLabel->SetColorAndOpacity(FSlateColor(LabelColor));
		if (UHorizontalBoxSlot* LabelSlot = ChildBox->AddChildToHorizontalBox(ChildLabel))
		{
			LabelSlot->SetVerticalAlignment(VAlign_Center);
		}

		WidgetTree->RootWidget = ChildBox;
	}

	return Super::RebuildWidget();
}

void ULQAGalleryChildWidget::SetThemeColors(const FLinearColor& InLabelColor, const FLinearColor& InIconColor)
{
	LabelColor = InLabelColor;
	IconColor = InIconColor;

	if (ChildLabel)
	{
		ChildLabel->SetColorAndOpacity(FSlateColor(LabelColor));
	}

	if (ChildIcon)
	{
		ChildIcon->SetBrushColor(IconColor);
	}
}
