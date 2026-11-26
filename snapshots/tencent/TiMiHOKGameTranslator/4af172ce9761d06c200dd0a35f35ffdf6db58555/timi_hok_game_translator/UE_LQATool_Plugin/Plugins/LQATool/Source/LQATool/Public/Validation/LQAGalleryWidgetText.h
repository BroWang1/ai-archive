#pragma once

#include "CoreMinimal.h"
#include "Internationalization/Text.h"
#include "Runtime/Launch/Resources/Version.h"

/**
 * 画廊控件文本定义：为画廊示例 UI 提供显示文本（画廊唯一文本出口）。
 *
 * 使用规范：
 *   1. 示例文本只允许在本文件定义，控件侧不得硬编码；
 *   2. 新增文本必须同步登记到 LQALocalization 两个 JSON，否则还原侧取不到译文。
 */
namespace LQAGalleryWidgetText
{
/** 统一 Namespace，与 GameLocalizationExport_en.json 的键前缀保持一致 */
#define LQA_GALLERY_TEXT(Key, SourceStr) NSLOCTEXT("ST_Gallery", Key, SourceStr)
/** 画廊行标签 / 编号等次级文本（源文在 Text_Translations_en.json 中登记） */
#define LQA_GALLERY_LABEL(Name, SourceStr) NSLOCTEXT("ST_Gallery", "ST_Gallery_Label_" #Name, SourceStr)

// ===========================================================================
// L1：内容文本（Key 与源文对齐 GameLocalizationExport_en.json）
// ===========================================================================

#if ENGINE_MAJOR_VERSION >= 5
inline FText Title() { return LQA_GALLERY_TEXT("ST_Gallery_Title", "LQA 验证画廊 (UE5)"); }
#else
inline FText Title() { return LQA_GALLERY_TEXT("ST_Gallery_Title_UE4", "LQA 验证画廊 (UE4)"); }
#endif
inline FText SectionText() { return LQA_GALLERY_TEXT("ST_Gallery_Section_Text", "一、文本类控件"); }
inline FText SectionInput() { return LQA_GALLERY_TEXT("ST_Gallery_Section_Input", "二、交互/输入类控件"); }
inline FText SectionPresent() { return LQA_GALLERY_TEXT("ST_Gallery_Section_Present", "三、展示类控件"); }
inline FText SectionLayout() { return LQA_GALLERY_TEXT("ST_Gallery_Section_Layout", "四、布局容器"); }

inline FText TextBlockSample() { return LQA_GALLERY_TEXT("ST_Gallery_TextBlockSample", "这是 TextBlock 示例"); }
inline FText RichTextBlockSample()
{
	return LQA_GALLERY_TEXT("ST_Gallery_RichTextBlockSample", "这是 <Name>RichTextBlock</> <Accent>富文本</> 示例");
}
inline FText MultiLineText() { return LQA_GALLERY_TEXT("ST_Gallery_MultiLineText", "MultiLineEditableText\n多行文本"); }
inline FText MultiLineTextBox()
{
	return LQA_GALLERY_TEXT("ST_Gallery_MultiLineTextBox", "MultiLineEditableTextBox\n多行文本框");
}
inline FText HintEditableText() { return LQA_GALLERY_TEXT("ST_Gallery_Hint_EditableText", "EditableText 单行输入"); }
inline FText HintEditableTextBox()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Hint_EditableTextBox", "EditableTextBox 单行输入框");
}
inline FText BorderContent() { return LQA_GALLERY_TEXT("ST_Gallery_BorderContent", "Border 内容"); }
inline FText OverlayStack() { return LQA_GALLERY_TEXT("ST_Gallery_OverlayStack", "Overlay 叠加"); }
inline FText ScaleBoxContent() { return LQA_GALLERY_TEXT("ST_Gallery_ScaleBoxContent", "ScaleBox 缩放内容"); }
inline FText SafeZoneContent() { return LQA_GALLERY_TEXT("ST_Gallery_SafeZoneContent", "SafeZone 内容"); }

// ===========================================================================
// L2：行标签（源文在 Text_Translations_en.json 中登记，译文与源文一致）
// ===========================================================================

inline FText LabelTextBlock() { return LQA_GALLERY_LABEL(TextBlock, "TextBlock"); }
inline FText LabelRichTextBlock() { return LQA_GALLERY_LABEL(RichTextBlock, "RichTextBlock"); }
inline FText LabelEditableText() { return LQA_GALLERY_LABEL(EditableText, "EditableText"); }
inline FText LabelEditableTextBox() { return LQA_GALLERY_LABEL(EditableTextBox, "EditableTextBox"); }
inline FText LabelMultiLineEditableText()
{
	return LQA_GALLERY_LABEL(MultiLineEditableText, "MultiLineEditableText");
}
inline FText LabelMultiLineEditableTextBox()
{
	return LQA_GALLERY_LABEL(MultiLineEditableTextBox, "MultiLineEditableTextBox");
}
inline FText LabelButton() { return LQA_GALLERY_LABEL(Button, "Button"); }
inline FText LabelCheckBox() { return LQA_GALLERY_LABEL(CheckBox, "CheckBox"); }
inline FText LabelSlider() { return LQA_GALLERY_LABEL(Slider, "Slider"); }
inline FText LabelProgressBar() { return LQA_GALLERY_LABEL(ProgressBar, "ProgressBar"); }
inline FText LabelComboBoxString() { return LQA_GALLERY_LABEL(ComboBoxString, "ComboBoxString"); }
inline FText LabelComboBoxKey() { return LQA_GALLERY_LABEL(ComboBoxKey, "ComboBoxKey"); }
inline FText LabelSpinBox() { return LQA_GALLERY_LABEL(SpinBox, "SpinBox"); }
inline FText LabelInputKeySelector() { return LQA_GALLERY_LABEL(InputKeySelector, "InputKeySelector"); }
inline FText LabelImage() { return LQA_GALLERY_LABEL(Image, "Image"); }
inline FText LabelThrobber() { return LQA_GALLERY_LABEL(Throbber, "Throbber"); }
inline FText LabelCircularThrobber() { return LQA_GALLERY_LABEL(CircularThrobber, "CircularThrobber"); }
inline FText LabelSpacer() { return LQA_GALLERY_LABEL(Spacer, "Spacer (40x20)"); }
inline FText LabelBorder() { return LQA_GALLERY_LABEL(Border, "Border"); }
inline FText LabelBackgroundBlur() { return LQA_GALLERY_LABEL(BackgroundBlur, "BackgroundBlur"); }
inline FText LabelRetainerBox() { return LQA_GALLERY_LABEL(RetainerBox, "RetainerBox"); }
inline FText LabelPostBufferUpdate() { return LQA_GALLERY_LABEL(PostBufferUpdate, "PostBufferUpdate"); }
inline FText LabelUserWidget() { return LQA_GALLERY_LABEL(UserWidget, "UserWidget"); }
inline FText LabelCanvasPanel() { return LQA_GALLERY_LABEL(CanvasPanel, "CanvasPanel"); }
inline FText LabelScrollBox() { return LQA_GALLERY_LABEL(ScrollBox, "ScrollBox"); }
inline FText LabelVerticalBox() { return LQA_GALLERY_LABEL(VerticalBox, "VerticalBox"); }
inline FText LabelHorizontalBox() { return LQA_GALLERY_LABEL(HorizontalBox, "HorizontalBox"); }
inline FText LabelScaleBox() { return LQA_GALLERY_LABEL(ScaleBox, "ScaleBox"); }
inline FText LabelSafeZone() { return LQA_GALLERY_LABEL(SafeZone, "SafeZone"); }
inline FText LabelWrapBox() { return LQA_GALLERY_LABEL(WrapBox, "WrapBox"); }
inline FText LabelSizeBox() { return LQA_GALLERY_LABEL(SizeBox, "SizeBox (120x40)"); }
inline FText LabelNamedSlot() { return LQA_GALLERY_LABEL(NamedSlot, "NamedSlot"); }
inline FText LabelGridPanel() { return LQA_GALLERY_LABEL(GridPanel, "GridPanel"); }
inline FText LabelUniformGridPanel() { return LQA_GALLERY_LABEL(UniformGridPanel, "UniformGridPanel"); }
inline FText LabelOverlay() { return LQA_GALLERY_LABEL(Overlay, "Overlay"); }
inline FText LabelWidgetSwitcher() { return LQA_GALLERY_LABEL(WidgetSwitcher, "WidgetSwitcher"); }
inline FText LabelStackBox() { return LQA_GALLERY_LABEL(StackBox, "StackBox"); }
inline FText LabelInvalidationBox() { return LQA_GALLERY_LABEL(InvalidationBox, "InvalidationBox"); }
inline FText LabelWindowTitleBarArea()
{
	return LQA_GALLERY_LABEL(WindowTitleBarArea, "WindowTitleBarArea");
}
inline FText LabelScrollBar() { return LQA_GALLERY_LABEL(ScrollBar, "ScrollBar"); }
inline FText LabelMenuAnchor() { return LQA_GALLERY_LABEL(MenuAnchor, "MenuAnchor"); }
inline FText LabelExpandableArea() { return LQA_GALLERY_LABEL(ExpandableArea, "ExpandableArea"); }
inline FText LabelDynamicEntryBox() { return LQA_GALLERY_LABEL(DynamicEntryBox, "DynamicEntryBox"); }
inline FText LabelListView() { return LQA_GALLERY_LABEL(ListView, "ListView"); }
inline FText LabelTileView() { return LQA_GALLERY_LABEL(TileView, "TileView"); }
inline FText LabelTreeView() { return LQA_GALLERY_LABEL(TreeView, "TreeView"); }

// ===========================================================================
// L2：示例内容 / 辅助文本
// ===========================================================================

inline FText ContentTextBlock() { return LQA_GALLERY_LABEL(ContentTextBlock, "TextBlock"); }
inline FText ContentBorder() { return LQA_GALLERY_LABEL(ContentBorder, "Border"); }
inline FText ContentButton() { return LQA_GALLERY_LABEL(ContentButton, "Button"); }
inline FText ContentComboBoxString() { return LQA_GALLERY_LABEL(ContentComboBoxString, "ComboBoxString"); }
inline FText ContentEditableText() { return LQA_GALLERY_LABEL(ContentEditableText, "EditableText"); }
inline FText ContentScrollBox() { return LQA_GALLERY_LABEL(ContentScrollBox, "ScrollBox"); }
inline FText ContentPage0() { return LQA_GALLERY_LABEL(Page0, "Page 0"); }
inline FText ContentPage1() { return LQA_GALLERY_LABEL(Page1, "Page 1"); }
inline FText ContentKeySelection() { return LQA_GALLERY_LABEL(KeySelection, "KeySelection"); }
inline FText ContentNoKeySpecified() { return LQA_GALLERY_LABEL(NoKeySpecified, "NoKeySpecified"); }
inline FText ContentMenuAnchorAnchor() { return LQA_GALLERY_LABEL(MenuAnchorAnchor, "MenuAnchor Anchor"); }
inline FText ContentInvalidationBox() { return LQA_GALLERY_LABEL(InvalidationBoxContent, "InvalidationBox Content"); }
inline FText ContentWindowTitleBarArea()
{
	return LQA_GALLERY_LABEL(WindowTitleBarAreaContent, "WindowTitleBarArea Content");
}
inline FText ContentHorizontal(int32 Index)
{
	switch (Index)
	{
	case 0: return LQA_GALLERY_LABEL(H0, "[H0]");
	case 1: return LQA_GALLERY_LABEL(H1, "[H1]");
	default: return LQA_GALLERY_LABEL(H2, "[H2]");
	}
}
inline FText ContentGrid(int32 Row, int32 Column)
{
	if (Row == 0 && Column == 0) { return LQA_GALLERY_LABEL(R0C0, "(0,0)"); }
	if (Row == 0 && Column == 1) { return LQA_GALLERY_LABEL(R0C1, "(0,1)"); }
	if (Row == 1 && Column == 0) { return LQA_GALLERY_LABEL(R1C0, "(1,0)"); }
	return LQA_GALLERY_LABEL(R1C1, "(1,1)");
}
inline FText ContentUniform(int32 Index)
{
	switch (Index)
	{
	case 0: return LQA_GALLERY_LABEL(U0, "U0");
	case 1: return LQA_GALLERY_LABEL(U1, "U1");
	case 2: return LQA_GALLERY_LABEL(U2, "U2");
	default: return LQA_GALLERY_LABEL(U3, "U3");
	}
}
inline FText ContentWrap(int32 Index)
{
	switch (Index)
	{
	case 0: return LQA_GALLERY_LABEL(W0, "Wrap0");
	case 1: return LQA_GALLERY_LABEL(W1, "Wrap1");
	case 2: return LQA_GALLERY_LABEL(W2, "Wrap2");
	case 3: return LQA_GALLERY_LABEL(W3, "Wrap3");
	case 4: return LQA_GALLERY_LABEL(W4, "Wrap4");
	default: return LQA_GALLERY_LABEL(W5, "Wrap5");
	}
}

// ===========================================================================
// L2：交互控制条按钮文本
// ===========================================================================

inline FText CtrlScrollTop() { return LQA_GALLERY_LABEL(CtrlScrollTop, "滚动到顶"); }
inline FText CtrlScrollBottom() { return LQA_GALLERY_LABEL(CtrlScrollBottom, "滚动到底"); }
inline FText CtrlToggleTheme() { return LQA_GALLERY_LABEL(CtrlToggleTheme, "切换背景"); }

// ===========================================================================
// L2：列表示例条目文本（<View 名>Text<序号>，便于采集时核对条目来源）
// ===========================================================================

inline FText DynamicEntryBoxText(int32 Index)
{
	switch (Index)
	{
	case 1: return LQA_GALLERY_LABEL(DynamicEntryBoxText1, "DynamicEntryBoxText1");
	case 2: return LQA_GALLERY_LABEL(DynamicEntryBoxText2, "DynamicEntryBoxText2");
	default: return LQA_GALLERY_LABEL(DynamicEntryBoxText3, "DynamicEntryBoxText3");
	}
}

inline FText ListViewText(int32 Index)
{
	switch (Index)
	{
	case 1: return LQA_GALLERY_LABEL(ListViewText1, "ListViewText1");
	case 2: return LQA_GALLERY_LABEL(ListViewText2, "ListViewText2");
	default: return LQA_GALLERY_LABEL(ListViewText3, "ListViewText3");
	}
}

inline FText TileViewText(int32 Index)
{
	return Index == 1 ? LQA_GALLERY_LABEL(TileViewText1, "TileViewText1")
					  : LQA_GALLERY_LABEL(TileViewText2, "TileViewText2");
}

inline FText TreeViewText(int32 Index)
{
	switch (Index)
	{
	case 1: return LQA_GALLERY_LABEL(TreeViewText1, "TreeViewText1");
	case 2: return LQA_GALLERY_LABEL(TreeViewText2, "TreeViewText2");
	default: return LQA_GALLERY_LABEL(TreeViewText3, "TreeViewText3");
	}
}

// ===========================================================================
// L1：显示性质 BUG 示例文本（故意缺陷，供插件识别能力验证；文本需登记本地化）
// ===========================================================================

inline FText SectionBug() { return LQA_GALLERY_TEXT("ST_Gallery_Section_Bug", "五、显示性质 BUG"); }

inline FText BugOverflowSingleLine()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_OverflowSingleLine",
		"这段文本故意不换行，会冲出左侧固定区域并超出舞台边界，用于检测文本溢出与重叠");
}
inline FText BugOverflowMultiLine()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_OverflowMultiLine", "换行后行数超出高度，越出舞台底部");
}
inline FText BugFontSize() { return LQA_GALLERY_TEXT("ST_Gallery_Bug_FontSize", "字号 36 的文本"); }
inline FText BugButtonOverflow()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_ButtonOverflow", "Confirm and Continue With All Changes");
}
inline FText BugLineHeight()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_LineHeight",
		"行高被压缩到 30%，两行文本会互相叠压，用于检测单个文本节点内部的重叠");
}
inline FText BugInvisible()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_Invisible", "这段文本与底色同色，应完全不可见");
}
inline FText BugTileViewOverflow()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_TileViewOverflow", "OverflowingTileViewItemTextWithoutAnySpaces");
}

inline FText BugTruncate()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_Truncate",
		"这段文本超出固定宽度后被硬截断，末尾没有省略号，用于检测截断识别");
}

/** BUG 示例：无本地化 Key 的文本（不登记 LQALocalization，采集应输出 INVALIDKEY） */
inline FText BugNoKey()
{
	return FText::FromString(TEXT("Invalid/IDC_Gameltem_30005"));
}

/** BUG 示例：有 Key 但无译文的文本（不登记 LQALocalization，英文下应显示中文源文） */
inline FText BugMissingTranslation()
{
	return LQA_GALLERY_TEXT("ST_Gallery_Bug_MissingTranslation", "漏译：有 Key 无译文");
}

// ===========================================================================
// L2：显示性质 BUG 行标签与参照文本
// ===========================================================================

inline FText LabelBug01() { return LQA_GALLERY_LABEL(Bug01, "[BUG-01] 单行超长溢出"); }
inline FText LabelBug02() { return LQA_GALLERY_LABEL(Bug02, "[BUG-02] 换行纵向溢出"); }
inline FText LabelBug03() { return LQA_GALLERY_LABEL(Bug03, "[BUG-03] 字号过大溢出"); }
inline FText LabelBug04() { return LQA_GALLERY_LABEL(Bug04, "[BUG-04] 按钮文本被截断"); }
inline FText LabelBug05() { return LQA_GALLERY_LABEL(Bug05, "[BUG-05] 行高压缩叠字"); }
inline FText LabelBug06() { return LQA_GALLERY_LABEL(Bug06, "[BUG-06] 文本同色不可见"); }
inline FText LabelBug07() { return LQA_GALLERY_LABEL(Bug07Truncate, "[BUG-07] 文本被硬截断"); }
inline FText LabelBug08() { return LQA_GALLERY_LABEL(Bug08, "[BUG-08] TileView 容器重叠"); }
inline FText LabelBug09() { return LQA_GALLERY_LABEL(Bug09, "[BUG-09] TileView 条目截断"); }
inline FText LabelBug10() { return LQA_GALLERY_LABEL(Bug10MissingKey, "[BUG-10] 漏 Key 显示原始 Key"); }
inline FText LabelBug11() { return LQA_GALLERY_LABEL(Bug11, "[BUG-11] 有 Key 但漏译"); }

inline FText BugReferenceBottom() { return LQA_GALLERY_LABEL(BugReferenceBottom, "↑ 底部参照行"); }

inline FText BugTileViewItem(int32 Index)
{
	return Index == 1 ? LQA_GALLERY_LABEL(BugTileViewItem1, "BugTile1")
					  : LQA_GALLERY_LABEL(BugTileViewItem2, "BugTile2");
}

#undef LQA_GALLERY_LABEL
#undef LQA_GALLERY_TEXT
}
