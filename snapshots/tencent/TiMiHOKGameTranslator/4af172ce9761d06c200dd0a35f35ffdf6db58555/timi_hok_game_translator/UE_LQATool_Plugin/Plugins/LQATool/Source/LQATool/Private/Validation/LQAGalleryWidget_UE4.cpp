#include "Validation/LQAGalleryWidget_UE4.h"

#include "Blueprint/WidgetTree.h"
#include "Components/BackgroundBlur.h"
#include "Components/Border.h"
#include "Components/Button.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/CheckBox.h"
#include "Components/CircularThrobber.h"
#include "Components/ComboBoxString.h"
#include "Components/DynamicEntryBox.h"
#include "Components/EditableText.h"
#include "Components/EditableTextBox.h"
#include "Components/ExpandableArea.h"
#include "Components/GridPanel.h"
#include "Components/GridSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/InputKeySelector.h"
#include "Components/InvalidationBox.h"
#include "Components/MenuAnchor.h"
#include "Components/MultiLineEditableText.h"
#include "Components/MultiLineEditableTextBox.h"
#include "Components/NamedSlot.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
#include "Components/ProgressBar.h"
#include "Components/RetainerBox.h"
#include "Components/RichTextBlock.h"
#include "Components/SafeZone.h"
#include "Components/ScaleBox.h"
#include "Components/ScrollBar.h"
#include "Components/ScrollBox.h"
#include "Components/SizeBox.h"
#include "Components/Slider.h"
#include "Components/Spacer.h"
#include "Components/SpinBox.h"
#include "Components/TextBlock.h"
#include "Components/Throbber.h"
#include "Components/UniformGridPanel.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/WidgetSwitcher.h"
#include "Components/WindowTitleBarArea.h"
#include "Components/WrapBox.h"
#include "Engine/DataTable.h"
#include "Engine/Font.h"
#include "Engine/Texture2D.h"
#include "Engine/World.h"
#include "Styling/CoreStyle.h"
#include "Styling/SlateTypes.h"
#include "TextureResource.h"
#include "UObject/UnrealType.h"

#include "Validation/LQAGalleryWidgetItem.h"
#include "Validation/LQAGalleryWidgetText.h"

namespace
{
	/** 画廊固定使用的引擎字体（不读项目默认字体配置） */
	FSlateFontInfo UE4GetRichTextFont(const TCHAR* Typeface, int32 Size = 24)
	{
		const FName TypefaceName(Typeface);
		if (UFont* EngineFont = LoadObject<UFont>(nullptr, TEXT("/Engine/EngineFonts/Roboto.Roboto")))
		{
			return FSlateFontInfo(EngineFont, Size, TypefaceName);
		}

		return FCoreStyle::GetDefaultFontStyle(TypefaceName, Size);
	}

	FSlateFontInfo UE4GetEditableTextFont(const FSlateFontInfo& InSourceFont)
	{
		FSlateFontInfo FontInfo = UE4GetRichTextFont(TEXT("Regular"));
		FontInfo.CompositeFont = InSourceFont.CompositeFont;
		return FontInfo;
	}

	/** 向富文本样式表追加一行样式 */
	void UE4AddRichTextStyleRow(UDataTable* Table, const FName& RowName, const FSlateFontInfo& Font, const FLinearColor& Color)
	{
		FRichTextStyleRow Row;
		Row.TextStyle.Font = Font;
		Row.TextStyle.ColorAndOpacity = FSlateColor(Color);
		Table->AddRow(RowName, Row);
	}
}


// ===========================================================================
// 生命周期与总装
// ===========================================================================

TSharedRef<SWidget> ULQAGalleryWidget_UE4::RebuildWidget()
{
	if (!RootPanel && WidgetTree)
	{
		BuildAll(true, true, false);
	}
	return Super::RebuildWidget();
}

void ULQAGalleryWidget_UE4::BuildAll(bool bIncludeWidgets, bool bIncludeLayouts, bool bIncludeBugs)
{
	if (!WidgetTree)
	{
		return;
	}

	// ---- 根画布 ----
	UCanvasPanel* Canvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("GalleryRoot"));
	WidgetTree->RootWidget = Canvas;
	RootPanel = Canvas;

	// ---- 页面背景：全屏纯色，不参与命中测试 ----
	UBorder* Background = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("Gallery_Background"));
	Background->SetVisibility(ESlateVisibility::SelfHitTestInvisible);
	Canvas->AddChild(Background);
	if (UCanvasPanelSlot* BackgroundSlot = Cast<UCanvasPanelSlot>(Background->Slot))
	{
		BackgroundSlot->SetAnchors(FAnchors(0.f, 0.f, 1.f, 1.f));
		BackgroundSlot->SetOffsets(FMargin(0.f));
		BackgroundSlot->SetZOrder(0);
	}
	BackgroundBorder = Background;

	// ---- 交互控制条：固定顶部，不随滚动 ----
	UWidget* ControlBar = BuildControlBar();
	if (ControlBar)
	{
		Canvas->AddChild(ControlBar);
		if (UCanvasPanelSlot* ControlSlot = Cast<UCanvasPanelSlot>(ControlBar->Slot))
		{
			ControlSlot->SetAnchors(FAnchors(0.f, 0.f, 1.f, 0.f));
			ControlSlot->SetOffsets(FMargin(8.f, 8.f, 8.f, 0.f));
			ControlSlot->SetAutoSize(true);
			ControlSlot->SetZOrder(10);
		}
	}

	// ---- 滚动内容区（顶部避让控制条）----
	UScrollBox* Scroll = WidgetTree->ConstructWidget<UScrollBox>(UScrollBox::StaticClass(), TEXT("GalleryScroll"));
	GalleryScroll = Scroll;
	Canvas->AddChild(Scroll);
	if (UCanvasPanelSlot* ScrollSlot = Cast<UCanvasPanelSlot>(Scroll->Slot))
	{
		ScrollSlot->SetAnchors(FAnchors(0.f, 0.f, 1.f, 1.f));
		ScrollSlot->SetOffsets(FMargin(20.f, ControlBarHeight, 20.f, 20.f));
		ScrollSlot->SetZOrder(1);
	}

	UVerticalBox* VBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("GalleryVBox"));
	Scroll->AddChild(VBox);
	ContentBox = VBox;

	VBox->AddChildToVerticalBox(MakeSectionHeader(LQAGalleryWidgetText::Title()));

	if (bIncludeWidgets)
	{
		VBox->AddChildToVerticalBox(MakeSectionHeader(LQAGalleryWidgetText::SectionText()));
		VBox->AddChildToVerticalBox(BuildTextSection());

		VBox->AddChildToVerticalBox(MakeSectionHeader(LQAGalleryWidgetText::SectionInput()));
		VBox->AddChildToVerticalBox(BuildInputSection());

		VBox->AddChildToVerticalBox(MakeSectionHeader(LQAGalleryWidgetText::SectionPresent()));
		VBox->AddChildToVerticalBox(BuildDisplaySection());
	}

	if (bIncludeLayouts)
	{
		VBox->AddChildToVerticalBox(MakeSectionHeader(LQAGalleryWidgetText::SectionLayout()));
		VBox->AddChildToVerticalBox(BuildLayoutSection());
	}

	if (bIncludeBugs)
	{
		VBox->AddChildToVerticalBox(MakeSectionHeader(LQAGalleryWidgetText::SectionBug()));
		VBox->AddChildToVerticalBox(BuildBugSection());
	}

	ApplyTheme();
}

// ===========================================================================
// 行 / 文本 / 纹理辅助
// ===========================================================================

UTextBlock* ULQAGalleryWidget_UE4::MakeTextBlock(const FText& Text, FName WidgetName, ELQAGalleryTextRole Role)
{
	UTextBlock* TextBlock = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), WidgetName);
	TextBlock->SetText(Text);
	RegisterThemedText(TextBlock, Role);
	return TextBlock;
}

void ULQAGalleryWidget_UE4::RegisterThemedText(UTextBlock* TextBlock, ELQAGalleryTextRole Role)
{
	if (!TextBlock)
	{
		return;
	}

	switch (Role)
	{
	case ELQAGalleryTextRole::Secondary: SecondaryTexts.Add(TextBlock); break;
	case ELQAGalleryTextRole::OnAccent: OnAccentTexts.Add(TextBlock); break;
	case ELQAGalleryTextRole::OnPanel: OnPanelTexts.Add(TextBlock); break;
	case ELQAGalleryTextRole::OnControl: OnControlTexts.Add(TextBlock); break;
	default: PrimaryTexts.Add(TextBlock); break;
	}
}

UWidget* ULQAGalleryWidget_UE4::MakeSectionHeader(const FText& Title)
{
	UBorder* Border = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
	Border->SetPadding(FMargin(8.f, 4.f));

	Border->SetContent(MakeTextBlock(Title, NAME_None, ELQAGalleryTextRole::OnAccent));
	HeaderBorders.Add(Border);
	return Border;
}

UWidget* ULQAGalleryWidget_UE4::MakeSizedRow(const FText& Label, UWidget* Content, const FVector2D& Size)
{
	UHorizontalBox* Row = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());

	// 标签列：固定宽度（以最长标签 MultiLineEditableTextBox 为准），保证各行内容起点一致；
	USizeBox* LabelSizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
	LabelSizeBox->SetWidthOverride(LabelColumnWidth);
	LabelSizeBox->AddChild(MakeTextBlock(Label, NAME_None, ELQAGalleryTextRole::Secondary));

	if (UHorizontalBoxSlot* LabelSlot = Row->AddChildToHorizontalBox(LabelSizeBox))
	{
		LabelSlot->SetPadding(FMargin(0.f, 4.f, 16.f, 4.f));
		LabelSlot->SetVerticalAlignment(VAlign_Center);
	}

	if (!Content)
	{
		return Row;
	}

	// 内容列：用 MinDesired 约束（不用 Override，避免 EditableText / MultiLine 被裁剪）
	USizeBox* SizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
	SizeBox->SetMinDesiredWidth(static_cast<float>(Size.X));
	SizeBox->SetMinDesiredHeight(static_cast<float>(Size.Y));
	SizeBox->AddChild(Content);

	if (UHorizontalBoxSlot* ContentSlot = Row->AddChildToHorizontalBox(SizeBox))
	{
		ContentSlot->SetPadding(FMargin(0.f, 4.f));
		ContentSlot->SetVerticalAlignment(VAlign_Center);
	}

	return Row;
}

UWidget* ULQAGalleryWidget_UE4::MakeFixedText(
	const FText& Text, FName WidgetName, const FVector2D& Size, bool bWrap, float FontSize, UTextBlock** OutTextBlock)
{
	UTextBlock* TextBlock = MakeTextBlock(Text, WidgetName);
	TextBlock->SetAutoWrapText(bWrap);

	if (FontSize > 0.f)
	{
#if ENGINE_MAJOR_VERSION >= 5
		TextBlock->SetFontSize(FontSize);
#else
		// UE4.27 无 SetFontSize，通过改写 FontInfo 达到同样字号效果
		FSlateFontInfo FontInfo = TextBlock->Font;
		FontInfo.Size = static_cast<int32>(FontSize);
		TextBlock->SetFont(FontInfo);
#endif
	}
	if (OutTextBlock)
	{
		*OutTextBlock = TextBlock;
	}

	USizeBox* SizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
	SizeBox->SetWidthOverride(Size.X);
	SizeBox->SetHeightOverride(Size.Y);
	SizeBox->AddChild(TextBlock);
	return SizeBox;
}

UWidget* ULQAGalleryWidget_UE4::MakeBugRow(const FText& Label, UWidget* StageContent, const FVector2D& StageSize,
	bool bBottomReference, FLinearColor StageColor)
{
	UHorizontalBox* Row = WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass());

	USizeBox* LabelBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
	LabelBox->SetWidthOverride(400.f);
	LabelBox->AddChild(MakeTextBlock(Label, NAME_None, ELQAGalleryTextRole::Secondary));
	if (UHorizontalBoxSlot* LabelSlot = Row->AddChildToHorizontalBox(LabelBox))
	{
		LabelSlot->SetPadding(FMargin(0.f, 4.f, 32.f, 4.f));
		LabelSlot->SetVerticalAlignment(VAlign_Center);
	}

	USizeBox* StageBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
	StageBox->SetWidthOverride(StageSize.X);
	StageBox->SetHeightOverride(StageSize.Y);

	UBorder* Stage = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
	Stage->SetPadding(FMargin(0.f));

	FSlateBrush StageBrush;
	StageBrush.DrawAs = ESlateBrushDrawType::Box;
	Stage->SetBrush(StageBrush);
	Stage->SetBrushColor(StageColor.A > 0.f ? StageColor : Theme.BarBackground);

	UOverlay* StageOverlay = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass());
	if (StageContent)
	{
		if (UOverlaySlot* ContentSlot = StageOverlay->AddChildToOverlay(StageContent))
		{
			ContentSlot->SetHorizontalAlignment(HAlign_Left);
			ContentSlot->SetVerticalAlignment(VAlign_Top);
			ContentSlot->SetPadding(FMargin(4.f));
		}
	}

	auto CreateBottomReference = [this]()
	{
		UTextBlock* BottomReference =
			WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("Gallery_Bug_BottomReference"));
		BottomReference->SetText(LQAGalleryWidgetText::BugReferenceBottom());
		BottomReference->SetColorAndOpacity(FSlateColor(FLinearColor(0.62f, 0.64f, 0.69f, 1.f)));
		return BottomReference;
	};

	Stage->SetContent(StageOverlay);
	StageBox->AddChild(Stage);

	UWidget* StageColumn = StageBox;
	if (bBottomReference)
	{
		UVerticalBox* Column = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());
		Column->AddChildToVerticalBox(StageBox);

		if (UVerticalBoxSlot* ReferenceSlot = Column->AddChildToVerticalBox(CreateBottomReference()))
		{
			ReferenceSlot->SetHorizontalAlignment(HAlign_Left);
			ReferenceSlot->SetPadding(FMargin(4.f, 6.f, 0.f, 0.f));
		}

		StageColumn = Column;
	}

	if (UHorizontalBoxSlot* StageSlot = Row->AddChildToHorizontalBox(StageColumn))
	{
		StageSlot->SetPadding(FMargin(0.f, 4.f));
		StageSlot->SetVerticalAlignment(VAlign_Center);
	}

	return Row;
}

UButton* ULQAGalleryWidget_UE4::MakeControlButton(UPanelWidget* Parent, const FText& Label, FName WidgetName)
{
	UButton* Button = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), WidgetName);
	Button->AddChild(MakeTextBlock(Label, NAME_None, ELQAGalleryTextRole::Primary));

	if (Parent)
	{
		if (UHorizontalBoxSlot* ButtonSlot = Cast<UHorizontalBoxSlot>(Parent->AddChild(Button)))
		{
			ButtonSlot->SetPadding(FMargin(0.f, 0.f, 6.f, 0.f));
		}
	}

	return Button;
}

UTexture2D* ULQAGalleryWidget_UE4::CreateSolidTexture(int32 Size, const FColor& Color)
{
	UTexture2D* Texture = UTexture2D::CreateTransient(Size, Size, PF_B8G8R8A8);
	if (!Texture)
	{
		return nullptr;
	}

	// UE5 中 PlatformData 已私有化，必须用 GetPlatformData()；UE4 保留字段访问
#if ENGINE_MAJOR_VERSION >= 5
	FTexturePlatformData* PlatformData = Texture->GetPlatformData();
#else
	FTexturePlatformData* PlatformData = Texture->PlatformData;
#endif
	if (!PlatformData)
	{
		return nullptr;
	}

	void* Data = PlatformData->Mips[0].BulkData.Lock(LOCK_READ_WRITE);
	FColor* Pixels = static_cast<FColor*>(Data);
	for (int32 i = 0; i < Size * Size; ++i)
	{
		Pixels[i] = Color;
	}
	PlatformData->Mips[0].BulkData.Unlock();
	Texture->UpdateResource();
	return Texture;
}

// ===========================================================================
// 交互控制条
// ===========================================================================

UPanelWidget* ULQAGalleryWidget_UE4::BuildControlBar()
{
	UBorder* Bar = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("Gallery_ControlBar"));
	Bar->SetPadding(FMargin(8.f, 6.f));
	ControlBarBorder = Bar;

	UHorizontalBox* Row =
		WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("Gallery_ControlBar_Row"));

	// 新增按钮时调用 MakeControlButton() 创建，再 AddDynamic 绑定到本类任一回调中；
	// 按钮文本取自 LQAGalleryWidgetText 并需在 LQALocalization 登记。
	MakeControlButton(Row, LQAGalleryWidgetText::CtrlScrollTop(), TEXT("Gallery_Ctrl_ScrollTop"))
		->OnClicked.AddDynamic(this, &ULQAGalleryWidget_UE4::OnScrollTopClicked);
	MakeControlButton(Row, LQAGalleryWidgetText::CtrlScrollBottom(), TEXT("Gallery_Ctrl_ScrollBottom"))
		->OnClicked.AddDynamic(this, &ULQAGalleryWidget_UE4::OnScrollBottomClicked);
	MakeControlButton(Row, LQAGalleryWidgetText::CtrlToggleTheme(), TEXT("Gallery_Ctrl_ToggleTheme"))
		->OnClicked.AddDynamic(this, &ULQAGalleryWidget_UE4::OnToggleThemeClicked);

	Bar->SetContent(Row);
	return Bar;
}

void ULQAGalleryWidget_UE4::OnSwitchPageClicked()
{
	if (GallerySwitcher)
	{
		const int32 CurrentIndex = GallerySwitcher->GetActiveWidgetIndex();
		GallerySwitcher->SetActiveWidgetIndex(CurrentIndex == 0 ? 1 : 0);
	}
}

void ULQAGalleryWidget_UE4::OnToggleExpandClicked()
{
	if (GalleryExpandableArea)
	{
		GalleryExpandableArea->SetIsExpanded(!GalleryExpandableArea->GetIsExpanded());
	}
}

void ULQAGalleryWidget_UE4::OnSwitchOptionClicked()
{
	const FString FirstOption = LQAGalleryWidgetText::ContentComboBoxString().ToString();
	const FString SecondOption = LQAGalleryWidgetText::ContentButton().ToString();

	if (GalleryComboBoxString)
	{
		const FString Current = GalleryComboBoxString->GetSelectedOption();
		GalleryComboBoxString->SetSelectedOption(Current == FirstOption ? SecondOption : FirstOption);
	}
	
	if (UComboBoxString* ComboBoxKeyFallback = Cast<UComboBoxString>(GalleryComboBoxKey))
	{
		const FString CurrentKey = ComboBoxKeyFallback->GetSelectedOption();
		ComboBoxKeyFallback->SetSelectedOption(CurrentKey == FirstOption ? SecondOption : FirstOption);
	}
}

void ULQAGalleryWidget_UE4::OnToggleMenuClicked()
{
	if (GalleryMenuAnchor)
	{
		GalleryMenuAnchor->ToggleOpen(true);
	}
}

void ULQAGalleryWidget_UE4::OnToggleCheckClicked()
{
	if (GalleryCheckBox)
	{
		GalleryCheckBox->SetIsChecked(!GalleryCheckBox->IsChecked());
	}
}

void ULQAGalleryWidget_UE4::OnScrollTopClicked()
{
	if (GalleryScroll)
	{
		GalleryScroll->ScrollToStart();
	}
}

void ULQAGalleryWidget_UE4::OnScrollBottomClicked()
{
	if (GalleryScroll)
	{
		GalleryScroll->ScrollToEnd();
	}
}

void ULQAGalleryWidget_UE4::OnToggleThemeClicked()
{
	bDarkTheme = !bDarkTheme;
	Theme = bDarkTheme ? FLQAGalleryTheme::Dark() : FLQAGalleryTheme::Light();
	ApplyTheme();
}

void ULQAGalleryWidget_UE4::ApplyTheme()
{
	if (BackgroundBorder)
	{
		BackgroundBorder->SetBrushColor(Theme.PageBackground);
	}

	if (ControlBarBorder)
	{
		ControlBarBorder->SetBrushColor(Theme.BarBackground);
	}

	for (UBorder* Header : HeaderBorders)
	{
		if (Header)
		{
			Header->SetBrushColor(Theme.HeaderBackground);
		}
	}

	for (UTextBlock* Text : PrimaryTexts)
	{
		if (Text)
		{
			Text->SetColorAndOpacity(FSlateColor(Theme.TextPrimary));
		}
	}

	for (UTextBlock* Text : SecondaryTexts)
	{
		if (Text)
		{
			Text->SetColorAndOpacity(FSlateColor(Theme.TextSecondary));
		}
	}

	for (UTextBlock* Text : OnAccentTexts)
	{
		if (Text)
		{
			Text->SetColorAndOpacity(FSlateColor(Theme.TextOnAccent));
		}
	}

	for (UTextBlock* Text : OnPanelTexts)
	{
		if (Text)
		{
			Text->SetColorAndOpacity(FSlateColor(Theme.TextOnPanel));
		}
	}

	for (UTextBlock* Text : OnControlTexts)
	{
		if (Text)
		{
			Text->SetColorAndOpacity(FSlateColor(FLQAGalleryTheme::ControlText()));
		}
	}

	if (GalleryRichText)
	{
		GalleryRichText->SetDefaultColorAndOpacity(FSlateColor(Theme.TextPrimary));
		GalleryRichText->SetTextStyleSet(GetRichTextStyleSet());
	}

	if (GalleryEditableText)
	{
#if ENGINE_MAJOR_VERSION >= 5
		FEditableTextStyle Style = GalleryEditableText->WidgetStyle;
		Style.ColorAndOpacity = FSlateColor(Theme.TextPrimary);
		GalleryEditableText->SetWidgetStyle(Style);
#else
		GalleryEditableText->WidgetStyle.ColorAndOpacity = FSlateColor(Theme.TextPrimary);
#endif
	}

	if (GalleryMultiLineEditableText)
	{
#if ENGINE_MAJOR_VERSION >= 5
		FTextBlockStyle Style = GalleryMultiLineEditableText->WidgetStyle;
		Style.ColorAndOpacity = FSlateColor(Theme.TextPrimary);
		GalleryMultiLineEditableText->SetWidgetStyle(Style);
#else
		GalleryMultiLineEditableText->WidgetStyle.ColorAndOpacity = FSlateColor(Theme.TextPrimary);
#endif
	}

	if (GalleryEditableTextBox)
	{
#if ENGINE_MAJOR_VERSION >= 5
		GalleryEditableTextBox->SetForegroundColor(FLQAGalleryTheme::ControlText());
#else
		GalleryEditableTextBox->WidgetStyle.ForegroundColor = FSlateColor(FLQAGalleryTheme::ControlText());
#endif
	}

	if (GalleryMultiLineEditableTextBox)
	{
#if ENGINE_MAJOR_VERSION >= 5
		GalleryMultiLineEditableTextBox->SetForegroundColor(FLQAGalleryTheme::ControlText());
#else
		const FSlateColor MultiLineTextColor(FLQAGalleryTheme::ControlText());
		GalleryMultiLineEditableTextBox->WidgetStyle.SetForegroundColor(MultiLineTextColor);
		GalleryMultiLineEditableTextBox->WidgetStyle.SetReadOnlyForegroundColor(MultiLineTextColor);
		GalleryMultiLineEditableTextBox->TextStyle.SetColorAndOpacity(FSlateColor::UseForeground());
#endif
	}

	if (GallerySpinBox)
	{
		GallerySpinBox->SetForegroundColor(FSlateColor(FLQAGalleryTheme::ControlText()));
	}

	if (GallerySlider)
	{
		GallerySlider->SetSliderBarColor(Theme.Divider);
		GallerySlider->SetSliderHandleColor(Theme.Accent);
	}

	if (GalleryProgressBar)
	{
		GalleryProgressBar->SetFillColorAndOpacity(Theme.Accent);
	}

	for (UCheckBox* CheckBox : GalleryCheckBoxes)
	{
		if (!CheckBox)
		{
			continue;
		}

#if ENGINE_MAJOR_VERSION >= 5
		FCheckBoxStyle Style = CheckBox->GetWidgetStyle();
		Style.CheckedImage.TintColor = FSlateColor(Theme.TextPrimary);
		Style.UncheckedImage.TintColor = FSlateColor(Theme.TextPrimary);
		Style.UndeterminedImage.TintColor = FSlateColor(Theme.TextPrimary);
		CheckBox->SetWidgetStyle(Style);
#else
		CheckBox->WidgetStyle.CheckedImage.TintColor = FSlateColor(Theme.TextPrimary);
		CheckBox->WidgetStyle.UncheckedImage.TintColor = FSlateColor(Theme.TextPrimary);
		CheckBox->WidgetStyle.UndeterminedImage.TintColor = FSlateColor(Theme.TextPrimary);
#endif
	}

	if (GalleryThrobber)
	{
#if ENGINE_MAJOR_VERSION >= 5
		FSlateBrush Brush = GalleryThrobber->GetImage();
		Brush.TintColor = FSlateColor(Theme.TextPrimary);
		GalleryThrobber->SetImage(Brush);
#else
		GalleryThrobber->Image.TintColor = FSlateColor(Theme.TextPrimary);
#endif
	}

	if (GalleryCircularThrobber)
	{
#if ENGINE_MAJOR_VERSION >= 5
		FSlateBrush Brush = GalleryCircularThrobber->GetImage();
		Brush.TintColor = FSlateColor(Theme.TextPrimary);
		GalleryCircularThrobber->SetImage(Brush);
#else
		GalleryCircularThrobber->Image.TintColor = FSlateColor(Theme.TextPrimary);
#endif
	}

	for (UListView* View : GalleryListViews)
	{
		if (!View)
		{
			continue;
		}

		for (UObject* Item : View->GetListItems())
		{
			if (ULQAGalleryListItem* ListItem = Cast<ULQAGalleryListItem>(Item))
			{
				ListItem->TextColor = Theme.TextPrimary;
			}
		}

		View->RegenerateAllEntries();
	}

	if (GalleryChildWidget)
	{
		GalleryChildWidget->SetThemeColors(Theme.TextPrimary, Theme.Accent);
	}
}

UDataTable* ULQAGalleryWidget_UE4::GetRichTextStyleSet()
{
	UDataTable*& CachedTable = bDarkTheme ? RichTextStyleDark : RichTextStyleLight;
	if (CachedTable)
	{
		return CachedTable;
	}

	UDataTable* Table = NewObject<UDataTable>(this);
	Table->RowStruct = FRichTextStyleRow::StaticStruct();

	UE4AddRichTextStyleRow(Table, TEXT("Default"), UE4GetRichTextFont(TEXT("Regular")), Theme.TextPrimary);
	UE4AddRichTextStyleRow(Table, TEXT("Name"), UE4GetRichTextFont(TEXT("Bold")), Theme.Highlight);
	UE4AddRichTextStyleRow(Table, TEXT("Accent"), UE4GetRichTextFont(TEXT("Bold")), Theme.Accent);

	CachedTable = Table;
	return Table;
}

// ===========================================================================
// 一、文本类控件
// ===========================================================================

UPanelWidget* ULQAGalleryWidget_UE4::BuildTextSection()
{
	UVerticalBox* Box = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());

	UTextBlock* TextBlock = MakeTextBlock(LQAGalleryWidgetText::TextBlockSample(), TEXT("Gallery_TextBlock"));
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelTextBlock(), TextBlock, FVector2D(360.f, 24.f)));

	URichTextBlock* RichText =
		WidgetTree->ConstructWidget<URichTextBlock>(URichTextBlock::StaticClass(), TEXT("Gallery_RichTextBlock"));
	RichText->SetText(LQAGalleryWidgetText::RichTextBlockSample());
	RichText->SetDefaultFont(UE4GetRichTextFont(TEXT("Regular")));
	GalleryRichText = RichText;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelRichTextBlock(), RichText, FVector2D(360.f, 32.f)));

	UEditableText* Editable =
		WidgetTree->ConstructWidget<UEditableText>(UEditableText::StaticClass(), TEXT("Gallery_EditableText"));
	Editable->SetHintText(LQAGalleryWidgetText::HintEditableText());
	Editable->WidgetStyle.SetFont(UE4GetEditableTextFont(Editable->WidgetStyle.Font));
	GalleryEditableText = Editable;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelEditableText(), Editable, FVector2D(240.f, 28.f)));

	UEditableTextBox* EditableBox =
		WidgetTree->ConstructWidget<UEditableTextBox>(UEditableTextBox::StaticClass(), TEXT("Gallery_EditableTextBox"));
	EditableBox->SetHintText(LQAGalleryWidgetText::HintEditableTextBox());
#if ENGINE_MAJOR_VERSION < 5
	EditableBox->WidgetStyle.SetFont(UE4GetEditableTextFont(EditableBox->WidgetStyle.Font));
#endif
	GalleryEditableTextBox = EditableBox;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelEditableTextBox(), EditableBox, FVector2D(240.f, 28.f)));

	UMultiLineEditableText* MultiText = WidgetTree->ConstructWidget<UMultiLineEditableText>(
		UMultiLineEditableText::StaticClass(), TEXT("Gallery_MultiLineEditableText"));
	MultiText->SetText(LQAGalleryWidgetText::MultiLineText());
	GalleryMultiLineEditableText = MultiText;
	Box->AddChildToVerticalBox(
		MakeSizedRow(LQAGalleryWidgetText::LabelMultiLineEditableText(), MultiText, FVector2D(260.f, 64.f)));

	UMultiLineEditableTextBox* MultiBox = WidgetTree->ConstructWidget<UMultiLineEditableTextBox>(
		UMultiLineEditableTextBox::StaticClass(), TEXT("Gallery_MultiLineEditableTextBox"));
	MultiBox->SetText(LQAGalleryWidgetText::MultiLineTextBox());
	GalleryMultiLineEditableTextBox = MultiBox;
	Box->AddChildToVerticalBox(
		MakeSizedRow(LQAGalleryWidgetText::LabelMultiLineEditableTextBox(), MultiBox, FVector2D(260.f, 64.f)));

	return Box;
}

// ===========================================================================
// 二、交互 / 输入类控件
// ===========================================================================

UPanelWidget* ULQAGalleryWidget_UE4::BuildInputSection()
{
	UVerticalBox* Box = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());

	// Button
	UButton* Button = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("Gallery_Button"));
	Button->AddChild(MakeTextBlock(LQAGalleryWidgetText::ContentButton(), NAME_None, ELQAGalleryTextRole::OnControl));
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelButton(), Button, FVector2D(120.f, 28.f)));

	// CheckBox（选中态，供控制条切换）
	UCheckBox* CheckBox = WidgetTree->ConstructWidget<UCheckBox>(UCheckBox::StaticClass(), TEXT("Gallery_CheckBox"));
	CheckBox->SetIsChecked(true);
	GalleryCheckBox = CheckBox;
	GalleryCheckBoxes.Add(CheckBox);
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelCheckBox(), CheckBox, FVector2D(32.f, 32.f)));

	// CheckBox（未选中 + 禁用态）
	UCheckBox* DisabledCheckBox =
		WidgetTree->ConstructWidget<UCheckBox>(UCheckBox::StaticClass(), TEXT("Gallery_CheckBox_Disabled"));
	DisabledCheckBox->SetIsChecked(false);
	DisabledCheckBox->SetIsEnabled(false);
	GalleryCheckBoxes.Add(DisabledCheckBox);
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelCheckBox(), DisabledCheckBox, FVector2D(32.f, 32.f)));

	// Slider
	USlider* Slider = WidgetTree->ConstructWidget<USlider>(USlider::StaticClass(), TEXT("Gallery_Slider"));
	Slider->SetValue(0.5f);
	GallerySlider = Slider;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelSlider(), Slider, FVector2D(240.f, 20.f)));

	// ProgressBar
	UProgressBar* Progress =
		WidgetTree->ConstructWidget<UProgressBar>(UProgressBar::StaticClass(), TEXT("Gallery_ProgressBar"));
	Progress->SetPercent(0.6f);
	GalleryProgressBar = Progress;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelProgressBar(), Progress, FVector2D(240.f, 18.f)));

	// ComboBoxString
	UComboBoxString* ComboBox = WidgetTree->ConstructWidget<UComboBoxString>(
		UComboBoxString::StaticClass(), TEXT("Gallery_ComboBoxString"));
	ComboBox->AddOption(LQAGalleryWidgetText::ContentComboBoxString().ToString());
	ComboBox->AddOption(LQAGalleryWidgetText::ContentButton().ToString());
	ComboBox->SetSelectedOption(LQAGalleryWidgetText::ContentComboBoxString().ToString());
	GalleryComboBoxString = ComboBox;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelComboBoxString(), ComboBox, FVector2D(240.f, 28.f)));

	// UE4.27 无 UComboBoxKey，用 UComboBoxString 作为 ComboBoxKey 行的等价占位
	UComboBoxString* ComboBoxKeyFallback = WidgetTree->ConstructWidget<UComboBoxString>(
		UComboBoxString::StaticClass(), TEXT("Gallery_ComboBoxKey"));
	ComboBoxKeyFallback->AddOption(LQAGalleryWidgetText::ContentComboBoxString().ToString());
	ComboBoxKeyFallback->AddOption(LQAGalleryWidgetText::ContentButton().ToString());
	ComboBoxKeyFallback->SetSelectedOption(LQAGalleryWidgetText::ContentComboBoxString().ToString());
	GalleryComboBoxKey = ComboBoxKeyFallback;
	Box->AddChildToVerticalBox(
		MakeSizedRow(LQAGalleryWidgetText::LabelComboBoxKey(), ComboBoxKeyFallback, FVector2D(240.f, 28.f)));

	// SpinBox
	USpinBox* SpinBox = WidgetTree->ConstructWidget<USpinBox>(USpinBox::StaticClass(), TEXT("Gallery_SpinBox"));
	SpinBox->SetValue(42.f);
	GallerySpinBox = SpinBox;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelSpinBox(), SpinBox, FVector2D(140.f, 28.f)));

	// InputKeySelector
	UInputKeySelector* KeySelector = WidgetTree->ConstructWidget<UInputKeySelector>(
		UInputKeySelector::StaticClass(), TEXT("Gallery_InputKeySelector"));
	KeySelector->SetKeySelectionText(LQAGalleryWidgetText::ContentKeySelection());
	KeySelector->SetNoKeySpecifiedText(LQAGalleryWidgetText::ContentNoKeySpecified());
	{
		// UE5 起 TextStyle / WidgetStyle 的直接访问被弃用, 改用 getter/setter;
		// UE4 仍只有公开成员, 这里按引擎版本分支, 保证两边都能编译且观感一致。
#if ENGINE_MAJOR_VERSION >= 5
		// TextStyle 的类型是 FTextBlockStyle (不是 FSlateFontInfo);
		// WidgetStyle 的 getter/setter 为 GetButtonStyle / SetButtonStyle。
		FTextBlockStyle KeyTextStyle = KeySelector->GetTextStyle();
		FSlateFontInfo KeyFont = UE4GetRichTextFont(TEXT("Bold"));
		KeyFont.CompositeFont = KeyTextStyle.Font.CompositeFont;
		KeyTextStyle.SetFont(KeyFont);
		KeyTextStyle.SetColorAndOpacity(FSlateColor(FLinearColor(0.f, 1.f, 1.f)));
		KeySelector->SetTextStyle(KeyTextStyle);

		FButtonStyle KeyStyle = KeySelector->GetButtonStyle();
		KeyStyle.SetNormalPadding(FMargin(12.f, 1.5f));
		KeyStyle.SetPressedPadding(FMargin(12.f, 1.5f));
		KeySelector->SetButtonStyle(KeyStyle);
#else
		FSlateFontInfo KeyFont = UE4GetRichTextFont(TEXT("Bold"));
		KeyFont.CompositeFont = KeySelector->TextStyle.Font.CompositeFont;
		KeySelector->TextStyle.SetFont(KeyFont);

		FButtonStyle KeyStyle = KeySelector->WidgetStyle;
		KeyStyle.SetNormalPadding(FMargin(12.f, 1.5f));
		KeyStyle.SetPressedPadding(FMargin(12.f, 1.5f));
		KeySelector->WidgetStyle = KeyStyle;
		KeySelector->TextStyle.SetColorAndOpacity(FSlateColor(FLinearColor(0.f, 1.f, 1.f)));
#endif
	}
	Box->AddChildToVerticalBox(
		MakeSizedRow(LQAGalleryWidgetText::LabelInputKeySelector(), KeySelector, FVector2D(240.f, 28.f)));

	// MenuAnchor（菜单内容取自 ULQAGalleryMenuWidget）
	UMenuAnchor* MenuAnchor =
		WidgetTree->ConstructWidget<UMenuAnchor>(UMenuAnchor::StaticClass(), TEXT("Gallery_MenuAnchor"));
	MenuAnchor->SetContent(MakeTextBlock(LQAGalleryWidgetText::ContentMenuAnchorAnchor()));
	MenuAnchor->MenuClass = ULQAGalleryMenuWidget::StaticClass();
	MenuAnchor->SetPlacement(MenuPlacement_BelowAnchor);
	GalleryMenuAnchor = MenuAnchor;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelMenuAnchor(), MenuAnchor, FVector2D(240.f, 28.f)));

	// ScrollBar（UMG 层不可指定方向，使用默认水平方向）
	UScrollBar* ScrollBar = WidgetTree->ConstructWidget<UScrollBar>(UScrollBar::StaticClass(), TEXT("Gallery_ScrollBar"));
	ScrollBar->SetState(0.3f, 0.4f);
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelScrollBar(), ScrollBar, FVector2D(120.f, 16.f)));

	return Box;
}

// ===========================================================================
// 三、展示类控件
// ===========================================================================

UPanelWidget* ULQAGalleryWidget_UE4::BuildDisplaySection()
{
	UVerticalBox* Box = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());

	// Image
	UImage* Image = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("Gallery_Image"));
	if (UTexture2D* Texture = CreateSolidTexture(64, FColor(80, 160, 220, 255)))
	{
		FSlateBrush Brush;
		Brush.SetResourceObject(Texture);
		Brush.ImageSize = FVector2D(64.f, 64.f);
		Image->SetBrush(Brush);
	}
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelImage(), Image, FVector2D(64.f, 64.f)));

	// Throbber / CircularThrobber
	UThrobber* Throbber = WidgetTree->ConstructWidget<UThrobber>(UThrobber::StaticClass(), TEXT("Gallery_Throbber"));
	GalleryThrobber = Throbber;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelThrobber(), Throbber, FVector2D(48.f, 48.f)));

	UCircularThrobber* Circular = WidgetTree->ConstructWidget<UCircularThrobber>(
		UCircularThrobber::StaticClass(), TEXT("Gallery_CircularThrobber"));
	GalleryCircularThrobber = Circular;
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelCircularThrobber(), Circular, FVector2D(48.f, 48.f)));

	// Spacer（无视觉表现，仅占位）
	USpacer* Spacer = WidgetTree->ConstructWidget<USpacer>(USpacer::StaticClass(), TEXT("Gallery_Spacer"));
	Spacer->SetSize(FVector2D(40.f, 20.f));
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelSpacer(), Spacer, FVector2D(40.f, 20.f)));

	// Border
	UBorder* Border = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass(), TEXT("Gallery_Border"));
	Border->SetBrushColor(FLinearColor(0.2f, 0.2f, 0.2f, 1.f));
	Border->SetPadding(FMargin(10.f));
	Border->SetContent(MakeTextBlock(LQAGalleryWidgetText::BorderContent(), NAME_None, ELQAGalleryTextRole::OnPanel));
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelBorder(), Border, FVector2D(240.f, 40.f)));

	// BackgroundBlur
	UBackgroundBlur* BackgroundBlur = WidgetTree->ConstructWidget<UBackgroundBlur>(
		UBackgroundBlur::StaticClass(), TEXT("Gallery_BackgroundBlur"));
	{
		UBorder* BlurContent = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
		BlurContent->SetBrushColor(FLinearColor(0.3f, 0.3f, 0.3f, 1.f));
		BlurContent->SetContent(
			MakeTextBlock(LQAGalleryWidgetText::ContentBorder(), NAME_None, ELQAGalleryTextRole::OnPanel));
		BackgroundBlur->SetContent(BlurContent);
	}
	Box->AddChildToVerticalBox(
		MakeSizedRow(LQAGalleryWidgetText::LabelBackgroundBlur(), BackgroundBlur, FVector2D(240.f, 80.f)));

	// RetainerBox
	URetainerBox* RetainerBox = WidgetTree->ConstructWidget<URetainerBox>(
		URetainerBox::StaticClass(), TEXT("Gallery_RetainerBox"));
	{
		UBorder* RetainerContent = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
		RetainerContent->SetBrushColor(FLinearColor(0.25f, 0.25f, 0.35f, 1.f));
		RetainerContent->SetContent(
			MakeTextBlock(LQAGalleryWidgetText::ContentBorder(), NAME_None, ELQAGalleryTextRole::OnPanel));
		RetainerBox->SetContent(RetainerContent);
	}
	Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelRetainerBox(), RetainerBox, FVector2D(240.f, 80.f)));

	// ListView：3 条
	{
		ULQAGalleryListView* ListView = WidgetTree->ConstructWidget<ULQAGalleryListView>(
			ULQAGalleryListView::StaticClass(), TEXT("Gallery_ListView"));
		GalleryListViews.Add(ListView);
		for (int32 Index = 1; Index <= 3; ++Index)
		{
			ULQAGalleryListItem* Item = NewObject<ULQAGalleryListItem>(this);
			Item->Label = LQAGalleryWidgetText::ListViewText(Index);
			ListView->AddItem(Item);
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelListView(), ListView, FVector2D(240.f, 120.f)));
	}

	// TileView：2 条（tile 宽度已加大，条目过多会导致内容溢出重叠）
	{
		ULQAGalleryTileView* TileView = WidgetTree->ConstructWidget<ULQAGalleryTileView>(
			ULQAGalleryTileView::StaticClass(), TEXT("Gallery_TileView"));
		GalleryListViews.Add(TileView);
		for (int32 Index = 1; Index <= 2; ++Index)
		{
			ULQAGalleryListItem* Item = NewObject<ULQAGalleryListItem>(this);
			Item->Label = LQAGalleryWidgetText::TileViewText(Index);
			TileView->AddItem(Item);
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelTileView(), TileView, FVector2D(240.f, 80.f)));
	}

	// TreeView：3 条
	{
		ULQAGalleryTreeView* TreeView = WidgetTree->ConstructWidget<ULQAGalleryTreeView>(
			ULQAGalleryTreeView::StaticClass(), TEXT("Gallery_TreeView"));
		GalleryListViews.Add(TreeView);
		for (int32 Index = 1; Index <= 3; ++Index)
		{
			ULQAGalleryListItem* Item = NewObject<ULQAGalleryListItem>(this);
			Item->Label = LQAGalleryWidgetText::TreeViewText(Index);
			TreeView->AddItem(Item);
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelTreeView(), TreeView, FVector2D(240.f, 120.f)));
	}

	// DynamicEntryBox：3 条（条目为 C++ UserWidget，文本取自 LQAGalleryWidgetText）
	{
		ULQAGalleryDynamicEntryWidget::StaticClass()->bCooked = true;

		UDynamicEntryBox* DynamicEntryBox = WidgetTree->ConstructWidget<UDynamicEntryBox>(
			UDynamicEntryBox::StaticClass(), TEXT("Gallery_DynamicEntryBox"));
		for (int32 Index = 1; Index <= 3; ++Index)
		{
			if (ULQAGalleryDynamicEntryWidget* Entry =
					DynamicEntryBox->CreateEntry<ULQAGalleryDynamicEntryWidget>(ULQAGalleryDynamicEntryWidget::StaticClass()))
			{
				Entry->SetEntryText(LQAGalleryWidgetText::DynamicEntryBoxText(Index));
			}
		}
		Box->AddChildToVerticalBox(MakeSizedRow(
			LQAGalleryWidgetText::LabelDynamicEntryBox(), DynamicEntryBox, FVector2D(240.f, 90.f)));
	}

	// 嵌套子 UserWidget（SObjectWidget）
	{
		USizeBox* ChildSizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		ChildSizeBox->SetMinDesiredWidth(240.f);
		ChildSizeBox->SetMinDesiredHeight(60.f);

		if (UWorld* World = GetWorld())
		{
			if (ULQAGalleryChildWidget* Child = CreateWidget<ULQAGalleryChildWidget>(
					World, ULQAGalleryChildWidget::StaticClass(), TEXT("Gallery_ChildWidget")))
			{
				GalleryChildWidget = Child;
				ChildSizeBox->AddChild(Child);
			}
		}

		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelUserWidget(), ChildSizeBox, FVector2D(240.f, 60.f)));
	}

	return Box;
}

// ===========================================================================
// 四、布局容器
// ===========================================================================

UPanelWidget* ULQAGalleryWidget_UE4::BuildLayoutSection()
{
	UVerticalBox* Box = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());

	// CanvasPanel（独立示例行）
	{
		UCanvasPanel* Canvas = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("Gallery_CanvasPanel"));
		UTextBlock* CanvasText = MakeTextBlock(LQAGalleryWidgetText::ContentTextBlock());
		Canvas->AddChild(CanvasText);
		if (UCanvasPanelSlot* CanvasItemSlot = Cast<UCanvasPanelSlot>(CanvasText->Slot))
		{
			CanvasItemSlot->SetAnchors(FAnchors(0.f, 0.f));
			CanvasItemSlot->SetOffsets(FMargin(0.f, 0.f, 120.f, 24.f));
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelCanvasPanel(), Canvas, FVector2D(240.f, 60.f)));
	}

	// ScrollBox（独立示例行）
	{
		UScrollBox* InnerScroll =
			WidgetTree->ConstructWidget<UScrollBox>(UScrollBox::StaticClass(), TEXT("Gallery_ScrollBox"));
		for (int32 Index = 0; Index < 3; ++Index)
		{
			InnerScroll->AddChild(MakeTextBlock(LQAGalleryWidgetText::ContentHorizontal(Index)));
		}
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelScrollBox(), InnerScroll, FVector2D(240.f, 60.f)));
	}

	// VerticalBox（独立示例行）
	{
		UVerticalBox* InnerVertical =
			WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass(), TEXT("Gallery_VerticalBox"));
		InnerVertical->AddChildToVerticalBox(MakeTextBlock(LQAGalleryWidgetText::ContentTextBlock()));
		InnerVertical->AddChildToVerticalBox(MakeTextBlock(LQAGalleryWidgetText::ContentBorder()));
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelVerticalBox(), InnerVertical, FVector2D(240.f, 60.f)));
	}

	// HorizontalBox
	{
		UHorizontalBox* HBox =
			WidgetTree->ConstructWidget<UHorizontalBox>(UHorizontalBox::StaticClass(), TEXT("Gallery_HorizontalBox"));
		for (int32 Index = 0; Index < 3; ++Index)
		{
			UTextBlock* Item = MakeTextBlock(LQAGalleryWidgetText::ContentHorizontal(Index));
			if (UHorizontalBoxSlot* ItemSlot = HBox->AddChildToHorizontalBox(Item))
			{
				ItemSlot->SetPadding(FMargin(6.f, 0.f));
			}
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelHorizontalBox(), HBox, FVector2D(240.f, 60.f)));
	}

	// GridPanel（补子项间距）
	{
		UGridPanel* Grid = WidgetTree->ConstructWidget<UGridPanel>(UGridPanel::StaticClass(), TEXT("Gallery_GridPanel"));
		for (int32 RowIndex = 0; RowIndex < 2; ++RowIndex)
		{
			for (int32 ColumnIndex = 0; ColumnIndex < 2; ++ColumnIndex)
			{
				UTextBlock* Item = MakeTextBlock(LQAGalleryWidgetText::ContentGrid(RowIndex, ColumnIndex));
				if (UGridSlot* GridItemSlot = Grid->AddChildToGrid(Item, RowIndex, ColumnIndex))
				{
					GridItemSlot->SetPadding(FMargin(4.f));
				}
			}
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelGridPanel(), Grid, FVector2D(240.f, 60.f)));
	}

	// UniformGridPanel（补槽位间距）
	{
		UUniformGridPanel* UniformGrid = WidgetTree->ConstructWidget<UUniformGridPanel>(
			UUniformGridPanel::StaticClass(), TEXT("Gallery_UniformGridPanel"));
		UniformGrid->SetSlotPadding(FMargin(4.f));
		for (int32 Index = 0; Index < 4; ++Index)
		{
			UniformGrid->AddChildToUniformGrid(
				MakeTextBlock(LQAGalleryWidgetText::ContentUniform(Index)), Index / 2, Index % 2);
		}
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelUniformGridPanel(), UniformGrid, FVector2D(240.f, 60.f)));
	}

	// Overlay
	{
		UOverlay* Overlay = WidgetTree->ConstructWidget<UOverlay>(UOverlay::StaticClass(), TEXT("Gallery_Overlay"));
		UBorder* OverlayBackground = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
		OverlayBackground->SetBrushColor(FLinearColor(0.3f, 0.3f, 0.3f, 1.f));
		if (UOverlaySlot* BackgroundSlot = Overlay->AddChildToOverlay(OverlayBackground))
		{
			BackgroundSlot->SetPadding(FMargin(0.f));
		}
		if (UOverlaySlot* ForegroundSlot = Overlay->AddChildToOverlay(
				MakeTextBlock(LQAGalleryWidgetText::OverlayStack(), NAME_None, ELQAGalleryTextRole::OnPanel)))
		{
			ForegroundSlot->SetPadding(FMargin(6.f));
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelOverlay(), Overlay, FVector2D(240.f, 60.f)));
	}

	// WrapBox（补内部间距）
	{
		UWrapBox* WrapBox = WidgetTree->ConstructWidget<UWrapBox>(UWrapBox::StaticClass(), TEXT("Gallery_WrapBox"));
		WrapBox->SetInnerSlotPadding(FVector2D(6.f, 4.f));
		for (int32 Index = 0; Index < 6; ++Index)
		{
			WrapBox->AddChildToWrapBox(MakeTextBlock(LQAGalleryWidgetText::ContentWrap(Index)));
		}
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelWrapBox(), WrapBox, FVector2D(240.f, 60.f)));
	}

	// SizeBox
	{
		USizeBox* SizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass(), TEXT("Gallery_SizeBox"));
		SizeBox->SetWidthOverride(120.f);
		SizeBox->SetHeightOverride(40.f);
		UBorder* Inner = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
		Inner->SetBrushColor(FLinearColor(0.4f, 0.2f, 0.2f, 1.f));
		SizeBox->AddChild(Inner);
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelSizeBox(), SizeBox, FVector2D(120.f, 40.f)));
	}

	// NamedSlot（Slate 层为 SBox，采集侧以 WidgetClass 细分）
	{
		USizeBox* NamedSlotSizeBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		NamedSlotSizeBox->SetMinDesiredWidth(120.f);
		NamedSlotSizeBox->SetMinDesiredHeight(40.f);
		UNamedSlot* NamedSlot =
			WidgetTree->ConstructWidget<UNamedSlot>(UNamedSlot::StaticClass(), TEXT("Gallery_NamedSlot"));
		NamedSlot->AddChild(MakeTextBlock(LQAGalleryWidgetText::LabelNamedSlot()));
		NamedSlotSizeBox->AddChild(NamedSlot);
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelNamedSlot(), NamedSlotSizeBox, FVector2D(120.f, 40.f)));
	}

	// ScaleBox
	{
		UScaleBox* ScaleBox = WidgetTree->ConstructWidget<UScaleBox>(UScaleBox::StaticClass(), TEXT("Gallery_ScaleBox"));
		ScaleBox->SetStretch(EStretch::ScaleToFit);
		ScaleBox->AddChild(MakeTextBlock(LQAGalleryWidgetText::ScaleBoxContent()));
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelScaleBox(), ScaleBox, FVector2D(240.f, 90.f)));
	}

	// SafeZone
	{
		USafeZone* SafeZone = WidgetTree->ConstructWidget<USafeZone>(USafeZone::StaticClass(), TEXT("Gallery_SafeZone"));
		SafeZone->AddChild(MakeTextBlock(LQAGalleryWidgetText::SafeZoneContent()));
		Box->AddChildToVerticalBox(MakeSizedRow(LQAGalleryWidgetText::LabelSafeZone(), SafeZone, FVector2D(240.f, 60.f)));
	}

	// WidgetSwitcher（两页等高，供控制条切页）
	{
		UWidgetSwitcher* Switcher = WidgetTree->ConstructWidget<UWidgetSwitcher>(
			UWidgetSwitcher::StaticClass(), TEXT("Gallery_WidgetSwitcher"));
		Switcher->AddChild(MakeTextBlock(LQAGalleryWidgetText::ContentPage0()));
		Switcher->AddChild(MakeTextBlock(LQAGalleryWidgetText::ContentPage1()));
		Switcher->SetActiveWidgetIndex(0);
		GallerySwitcher = Switcher;
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelWidgetSwitcher(), Switcher, FVector2D(240.f, 60.f)));
	}

	// InvalidationBox
	{
		UInvalidationBox* InvalidationBox = WidgetTree->ConstructWidget<UInvalidationBox>(
			UInvalidationBox::StaticClass(), TEXT("Gallery_InvalidationBox"));
		UBorder* InvalidationContent = WidgetTree->ConstructWidget<UBorder>(UBorder::StaticClass());
		InvalidationContent->SetBrushColor(FLinearColor(0.25f, 0.3f, 0.25f, 1.f));
		InvalidationContent->SetContent(
			MakeTextBlock(LQAGalleryWidgetText::ContentInvalidationBox(), NAME_None, ELQAGalleryTextRole::OnPanel));
		InvalidationBox->SetContent(InvalidationContent);
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelInvalidationBox(), InvalidationBox, FVector2D(240.f, 60.f)));
	}

	// WindowTitleBarArea
	{
		UWindowTitleBarArea* TitleBarArea = WidgetTree->ConstructWidget<UWindowTitleBarArea>(
			UWindowTitleBarArea::StaticClass(), TEXT("Gallery_WindowTitleBarArea"));
		TitleBarArea->SetContent(MakeTextBlock(LQAGalleryWidgetText::ContentWindowTitleBarArea()));
		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelWindowTitleBarArea(), TitleBarArea, FVector2D(240.f, 40.f)));
	}

	// ExpandableArea（Header / Body 均用 C++ 构造；初始展开便于采集内容）
	{
		UExpandableArea* ExpandableArea = WidgetTree->ConstructWidget<UExpandableArea>(
			UExpandableArea::StaticClass(), TEXT("Gallery_ExpandableArea"));
		ExpandableArea->SetContentForSlot(
			FName(TEXT("Header")), MakeTextBlock(LQAGalleryWidgetText::ContentBorder(), NAME_None, ELQAGalleryTextRole::OnControl));

		UVerticalBox* BodyBox = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());
		BodyBox->AddChildToVerticalBox(MakeTextBlock(LQAGalleryWidgetText::ContentTextBlock()));
		BodyBox->AddChildToVerticalBox(MakeTextBlock(LQAGalleryWidgetText::ContentBorder()));
		ExpandableArea->SetContentForSlot(FName(TEXT("Body")), BodyBox);
		ExpandableArea->SetIsExpanded(true);
		GalleryExpandableArea = ExpandableArea;

		Box->AddChildToVerticalBox(
			MakeSizedRow(LQAGalleryWidgetText::LabelExpandableArea(), ExpandableArea, FVector2D(280.f, 120.f)));
	}

	return Box;
}

// ===========================================================================
// 五、显示性质 BUG 示例
// ===========================================================================

UPanelWidget* ULQAGalleryWidget_UE4::BuildBugSection()
{
	UVerticalBox* Box = WidgetTree->ConstructWidget<UVerticalBox>(UVerticalBox::StaticClass());

	auto AddBugRow = [Box](UWidget* Row, float ExtraSpacing = 0.f)
	{
		if (UVerticalBoxSlot* RowSlot = Box->AddChildToVerticalBox(Row))
		{
			RowSlot->SetPadding(FMargin(0.f, 24.f + ExtraSpacing, 0.f, 24.f + ExtraSpacing));
		}
	};

	// BUG-01：不换行文本超出固定宽度
	{
		UWidget* Stage = MakeFixedText(LQAGalleryWidgetText::BugOverflowSingleLine(),
			TEXT("Gallery_Bug_01_Text"), FVector2D(160.f, 24.f), false, 0.f);
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug01(), Stage, FVector2D(240.f, 32.f)));
	}

	// BUG-02：自动换行后行数超出固定高度
	{
		UWidget* Stage = MakeFixedText(LQAGalleryWidgetText::BugOverflowMultiLine(),
			TEXT("Gallery_Bug_02_Text"), FVector2D(200.f, 40.f), true, 0.f);
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug02(), Stage, FVector2D(240.f, 64.f)), 16.f);
	}

	// BUG-03：字号超过固定高度
	{
		UWidget* Stage = MakeFixedText(LQAGalleryWidgetText::BugFontSize(),
			TEXT("Gallery_Bug_03_Text"), FVector2D(120.f, 24.f), false, 36.f);
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug03(), Stage, FVector2D(240.f, 40.f)), 16.f);
	}

	// BUG-04：按钮内文本超出按钮宽度
	{
		UButton* Button = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("Gallery_Bug_04_Button"));
		UTextBlock* ButtonText = MakeTextBlock(
			LQAGalleryWidgetText::BugButtonOverflow(), TEXT("Gallery_Bug_04_Text"), ELQAGalleryTextRole::OnControl);
		ButtonText->SetAutoWrapText(false);
		Button->AddChild(ButtonText);

		USizeBox* ButtonBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		ButtonBox->SetWidthOverride(120.f);
		ButtonBox->SetHeightOverride(28.f);
		ButtonBox->AddChild(Button);

		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug04(), ButtonBox, FVector2D(160.f, 32.f)));
	}

	// BUG-05：行高压缩导致同一文本节点内行间重叠
	{
		UTextBlock* TextBlock = nullptr;
		UWidget* Stage = MakeFixedText(LQAGalleryWidgetText::BugLineHeight(),
			TEXT("Gallery_Bug_05_Text"), FVector2D(200.f, 40.f), true, 0.f, &TextBlock);
		if (TextBlock)
		{
			if (FFloatProperty* LineHeightProperty = CastField<FFloatProperty>(
					UTextBlock::StaticClass()->FindPropertyByName(TEXT("LineHeightPercentage"))))
			{
				LineHeightProperty->SetPropertyValue_InContainer(TextBlock, 0.3f);
			}
		}
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug05(), Stage, FVector2D(240.f, 64.f)));
	}

	// BUG-06：文本颜色与舞台底色相同
	{
		const FLinearColor HiddenColor = FLQAGalleryTheme::Dark().BarBackground;
		UTextBlock* HiddenText =
			WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("Gallery_Bug_06_Text"));
		HiddenText->SetText(LQAGalleryWidgetText::BugInvisible());
		HiddenText->SetAutoWrapText(false);
		HiddenText->SetColorAndOpacity(FSlateColor(HiddenColor));

		USizeBox* HiddenBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		HiddenBox->SetWidthOverride(200.f);
		HiddenBox->SetHeightOverride(24.f);
		HiddenBox->AddChild(HiddenText);

		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug06(), HiddenBox, FVector2D(240.f, 48.f), true, HiddenColor));
	}

	// BUG-07：文本超出控件边界后被硬截断
	{
		UTextBlock* ClipText = nullptr;
		UWidget* Stage = MakeFixedText(LQAGalleryWidgetText::BugTruncate(),
			TEXT("Gallery_Bug_07_Text"), FVector2D(200.f, 24.f), false, 0.f, &ClipText);
		if (ClipText)
		{
			ClipText->SetClipping(EWidgetClipping::ClipToBounds);
		}
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug07(), Stage, FVector2D(240.f, 28.f)));
	}

	// BUG-08：TileView 条目高度小于文本行高，相邻条目重叠
	{
		ULQAGalleryTileView* TileView = WidgetTree->ConstructWidget<ULQAGalleryTileView>(
			ULQAGalleryTileView::StaticClass(), TEXT("Gallery_Bug_08_TileView"));
		TileView->SetEntryHeight(8.f);
		for (int32 Index = 1; Index <= 2; ++Index)
		{
			ULQAGalleryListItem* Item = NewObject<ULQAGalleryListItem>(this);
			Item->Label = LQAGalleryWidgetText::BugTileViewItem(Index);
			TileView->AddItem(Item);
		}

		USizeBox* TileViewBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		TileViewBox->SetWidthOverride(240.f);
		TileViewBox->SetHeightOverride(80.f);
		TileViewBox->AddChild(TileView);

		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug08(), TileViewBox, FVector2D(240.f, 80.f)));
	}

	// BUG-09：TileView 条目文本不换行，跨条目溢出
	{
		ULQAGalleryTileView* TileView = WidgetTree->ConstructWidget<ULQAGalleryTileView>(
			ULQAGalleryTileView::StaticClass(), TEXT("Gallery_Bug_09_TileView"));
		TileView->SetEntryWidth(120.f);
		for (int32 Index = 1; Index <= 2; ++Index)
		{
			ULQAGalleryListItem* Item = NewObject<ULQAGalleryListItem>(this);
			Item->Label = Index == 1 ? LQAGalleryWidgetText::BugTileViewOverflow()
									 : LQAGalleryWidgetText::BugTileViewItem(2);
			Item->bAutoWrapText = false;
			TileView->AddItem(Item);
		}

		USizeBox* TileViewBox = WidgetTree->ConstructWidget<USizeBox>(USizeBox::StaticClass());
		TileViewBox->SetWidthOverride(240.f);
		TileViewBox->SetHeightOverride(80.f);
		TileViewBox->AddChild(TileView);

		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug09(), TileViewBox, FVector2D(240.f, 80.f)));
	}

	// BUG-10：无 Key 文本直接显示原始 Key
	{
		UWidget* Stage = MakeFixedText(
			LQAGalleryWidgetText::BugNoKey(), TEXT("Gallery_Bug_10_Text"), FVector2D(400.f, 24.f), false, 0.f);
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug10(), Stage, FVector2D(460.f, 40.f)));
	}

	// BUG-11：文本有 Key 但没有译文
	{
		UWidget* Stage = MakeFixedText(
			LQAGalleryWidgetText::BugMissingTranslation(), TEXT("Gallery_Bug_11_Text"), FVector2D(300.f, 24.f), false, 0.f);
		AddBugRow(MakeBugRow(LQAGalleryWidgetText::LabelBug11(), Stage, FVector2D(380.f, 40.f)));
	}

	return Box;
}



