#pragma once

#include "Blueprint/UserWidget.h"
#include "CoreMinimal.h"
#include "Validation/LQAGalleryWidget_UE5.h"

#include "LQAGalleryWidget_UE4.generated.h"

class UBorder;
class UButton;
class UCheckBox;
class UCircularThrobber;
class UComboBoxKey;
class UComboBoxString;
class UDataTable;
class UEditableText;
class UEditableTextBox;
class UExpandableArea;
class UListView;
class UMenuAnchor;
class UMultiLineEditableText;
class UMultiLineEditableTextBox;
class UPanelWidget;
class UProgressBar;
class URichTextBlock;
class UScrollBox;
class USlider;
class USpinBox;
class UTextBlock;
class UTexture2D;
class UThrobber;
class UVerticalBox;
class UWidget;
class UWidgetSwitcher;
class ULQAGalleryChildWidget;


/**
 * LQA 快速验证画廊（UE4 版本）：一次性构造全部示例控件与布局容器。
 *
 * 使用方式：运行 `LQA.BuildGallery [Widgets|Layout|Composite|All]` 自动挂载到视口；
 * 顶部控制条“切换背景”按钮在深色 / 浅色主题间切换。
 * 约束：纯 C++ 构建，不新增任何资产；示例文本只能取自 LQAGalleryText；
 *       新增文本控件须经 MakeTextBlock 登记配色角色；
 *       RichText 字体固定取引擎字体，不读项目默认字体配置。
 */
UCLASS()
class ULQAGalleryWidget_UE4 : public UUserWidget
{
	GENERATED_BODY()

public:
	virtual TSharedRef<SWidget> RebuildWidget() override;

	/**
	 * 构建画廊
	 * @param bIncludeWidgets  文本 / 输入 / 展示 / 动态 四区
	 * @param bIncludeLayouts  布局容器区
	 * @param bIncludeBugs     显示性质 BUG 示例区
	 */
	void BuildAll(bool bIncludeWidgets = true, bool bIncludeLayouts = true, bool bIncludeBugs = false);

	/** 按当前主题刷新背景、标题条、控制条与全部已登记控件 */
	void ApplyTheme();

private:
	// =======================================================================
	// 分区构造
	// =======================================================================
	UPanelWidget* BuildTextSection();
	UPanelWidget* BuildInputSection();
	UPanelWidget* BuildDisplaySection();
	UPanelWidget* BuildLayoutSection();
	UPanelWidget* BuildBugSection();

	/** 顶部固定交互控制条（滚动定位 / 主题切换） */
	UPanelWidget* BuildControlBar();

	// =======================================================================
	// 行 / 文本 / 纹理辅助
	// =======================================================================

	/** 分区标题（蓝底白字） */
	UWidget* MakeSectionHeader(const FText& Title);

	/** 统一示例行：左标签（统一列宽）+ 右内容（SizeBox 约束最小尺寸） */
	UWidget* MakeSizedRow(const FText& Label, UWidget* Content, const FVector2D& Size);

	/**
	 * BUG 示例用固定尺寸文本（SizeBox 强制宽高，允许内容绘制越界）
	 * @param OutTextBlock 非空时返回内部 TextBlock
	 */
	UWidget* MakeFixedText(const FText& Text, FName WidgetName, const FVector2D& Size, bool bWrap, float FontSize,
		UTextBlock** OutTextBlock = nullptr);

	/**
	 * BUG 示例行：左标签 + 固定尺寸舞台（1px 描边）
	 * @param bBottomReference 是否在舞台下方显示参照行
	 * @param StageColor       舞台底色，透明时取当前主题控制条底色
	 */
	UWidget* MakeBugRow(const FText& Label, UWidget* StageContent, const FVector2D& StageSize,
		bool bBottomReference = false, FLinearColor StageColor = FLinearColor::Transparent);

	/** 使用已登记文本构造 TextBlock，并按角色登记主题配色 */
	UTextBlock* MakeTextBlock(const FText& Text, FName WidgetName = NAME_None,
		ELQAGalleryTextRole Role = ELQAGalleryTextRole::Primary);

	/** 按角色登记文本控件，供 ApplyTheme 统一改色 */
	void RegisterThemedText(UTextBlock* TextBlock, ELQAGalleryTextRole Role);

	/** 取当前主题的 RichText 样式表（缺失时按主题构建并缓存） */
	UDataTable* GetRichTextStyleSet();

	/** 构造控制条按钮（对象名需唯一，避免同名对象被复用） */
	UButton* MakeControlButton(UPanelWidget* Parent, const FText& Label, FName WidgetName);

	/** 构造纯色 texture（供 Image 示例使用） */
	UTexture2D* CreateSolidTexture(int32 Size, const FColor& Color);

	// =======================================================================
	// 交互回调（供控制条按钮 AddDynamic 绑定；默认仅 SwitchPage 被使用，其余供扩展）
	// =======================================================================
	UFUNCTION()
	void OnSwitchPageClicked();

	UFUNCTION()
	void OnToggleExpandClicked();

	UFUNCTION()
	void OnSwitchOptionClicked();

	UFUNCTION()
	void OnToggleMenuClicked();

	UFUNCTION()
	void OnToggleCheckClicked();

	UFUNCTION()
	void OnScrollTopClicked();

	UFUNCTION()
	void OnScrollBottomClicked();

	/** 深色 / 浅色主题切换 */
	UFUNCTION()
	void OnToggleThemeClicked();

	// =======================================================================
	// 成员（动态态回调需要访问，Transient 避免被序列化）
	// =======================================================================
	UPROPERTY(Transient)
	UPanelWidget* RootPanel = nullptr;

	UPROPERTY(Transient)
	UPanelWidget* ContentBox = nullptr;

	UPROPERTY(Transient)
	UScrollBox* GalleryScroll = nullptr;

	UPROPERTY(Transient)
	UWidgetSwitcher* GallerySwitcher = nullptr;

	UPROPERTY(Transient)
	UExpandableArea* GalleryExpandableArea = nullptr;

	UPROPERTY(Transient)
	UComboBoxString* GalleryComboBoxString = nullptr;

	UPROPERTY(Transient)
	UWidget* GalleryComboBoxKey = nullptr;

	UPROPERTY(Transient)
	UMenuAnchor* GalleryMenuAnchor = nullptr;

	UPROPERTY(Transient)
	UCheckBox* GalleryCheckBox = nullptr;

	// =======================================================================
	// 主题
	// =======================================================================

	/** 当前主题色板 */
	FLQAGalleryTheme Theme = FLQAGalleryTheme::Dark();

	/** 当前是否为深色主题 */
	bool bDarkTheme = true;

	/** 当前主题下的页面背景层 */
	UPROPERTY(Transient)
	UBorder* BackgroundBorder = nullptr;

	/** 顶部控制条底色容器 */
	UPROPERTY(Transient)
	UBorder* ControlBarBorder = nullptr;

	/** 分区标题条（随主题换底色） */
	UPROPERTY(Transient)
	TArray<UBorder*> HeaderBorders;

	/** 页面正文文本 */
	UPROPERTY(Transient)
	TArray<UTextBlock*> PrimaryTexts;

	/** 行标签文本 */
	UPROPERTY(Transient)
	TArray<UTextBlock*> SecondaryTexts;

	/** 标题条文本 */
	UPROPERTY(Transient)
	TArray<UTextBlock*> OnAccentTexts;

	/** 示例面板内文本 */
	UPROPERTY(Transient)
	TArray<UTextBlock*> OnPanelTexts;

	/** 引擎默认浅色控件上的文本 */
	UPROPERTY(Transient)
	TArray<UTextBlock*> OnControlTexts;

	/** RichTextBlock 示例 */
	UPROPERTY(Transient)
	URichTextBlock* GalleryRichText = nullptr;

	/** 深色主题的 RichText 样式表（运行时构建，不依赖资产） */
	UPROPERTY(Transient)
	UDataTable* RichTextStyleDark = nullptr;

	/** 浅色主题的 RichText 样式表（运行时构建，不依赖资产） */
	UPROPERTY(Transient)
	UDataTable* RichTextStyleLight = nullptr;

	/** EditableText 示例 */
	UPROPERTY(Transient)
	UEditableText* GalleryEditableText = nullptr;

	/** MultiLineEditableText 示例 */
	UPROPERTY(Transient)
	UMultiLineEditableText* GalleryMultiLineEditableText = nullptr;

	/** EditableTextBox 示例 */
	UPROPERTY(Transient)
	UEditableTextBox* GalleryEditableTextBox = nullptr;

	/** MultiLineEditableTextBox 示例 */
	UPROPERTY(Transient)
	UMultiLineEditableTextBox* GalleryMultiLineEditableTextBox = nullptr;

	/** SpinBox 示例 */
	UPROPERTY(Transient)
	USpinBox* GallerySpinBox = nullptr;

	/** Slider 示例 */
	UPROPERTY(Transient)
	USlider* GallerySlider = nullptr;

	/** ProgressBar 示例 */
	UPROPERTY(Transient)
	UProgressBar* GalleryProgressBar = nullptr;

	/** CheckBox 示例集合 */
	UPROPERTY(Transient)
	TArray<UCheckBox*> GalleryCheckBoxes;

	/** Throbber 示例 */
	UPROPERTY(Transient)
	UThrobber* GalleryThrobber = nullptr;

	/** CircularThrobber 示例 */
	UPROPERTY(Transient)
	UCircularThrobber* GalleryCircularThrobber = nullptr;

	/** 列表类示例（ListView / TileView / TreeView） */
	UPROPERTY(Transient)
	TArray<UListView*> GalleryListViews;

	/** 嵌套子 UserWidget 示例 */
	UPROPERTY(Transient)
	ULQAGalleryChildWidget* GalleryChildWidget = nullptr;

	/** 标签列固定宽度：以最长标签（MultiLineEditableTextBox）为准，保证各行内容起点一致 */
	float LabelColumnWidth = 350.f;

	/** 控制条高度：滚动区避让量 */
	float ControlBarHeight = 64.f;
};

