#include "WidgetSlots/LQAWidgetTypeRegistry.h"

// 以下 UMG 控件头文件用于 StaticClass() 取类指针, 填入登记表的 WidgetClass 约束
#include "Components/ComboBox.h"
#if ENGINE_MAJOR_VERSION >= 5
#include "Components/ComboBoxKey.h"
#endif
#include "Components/ComboBoxString.h"
#include "Components/DynamicEntryBox.h"
#include "Components/EditableText.h"
#include "Components/EditableTextBox.h"
#include "Components/Image.h"
#include "Components/MultiLineEditableText.h"
#include "Components/MultiLineEditableTextBox.h"
#include "Components/NamedSlot.h"
#include "Components/NativeWidgetHost.h"
#include "Components/RichTextBlock.h"
#include "Components/SizeBox.h"
#include "Components/Button.h"
#include "Components/TextBlock.h"
#include "Components/Widget.h"
#include "WidgetSlots/WidgetDefines.h"   // LQAWidgetNames 命名空间下的 Slate 名常量

// ================== 内部辅助函数 ==================

// 匿名命名空间: 将辅助函数限定在本编译单元内, 不对外暴露符号
namespace
{
/**
 * 判断某条登记项的 Slate 名是否与运行时 Slate 名命中
 * 支持两种模式: 精确同名, 或 (bPrefixMatch 为真时) 前缀匹配
 *
 * @param Entry         待比对的登记项
 * @param SlateTypeName 运行时取得的 Slate 类型名
 * @return 命中返回 true, 否则 false
 */
bool IsSlateNameMatched(const FLQAWidgetTypeDesc& Entry, const FName& SlateTypeName)
{
	// 优先尝试完全同名: 这是最常见也最廉价的判断
	if (Entry.SlateTypeName == SlateTypeName)
	{
		return true;
	}

	// 不要求前缀匹配时, 同名未命中即判定失败
	if (!Entry.bPrefixMatch)
	{
		return false;
	}

	// 前缀匹配 (大小写敏感): 覆盖 SComboBox<FName>、SSpinBox<float> 等
	// 运行时携带模板实参、名字不固定的 Slate 类型
	return SlateTypeName.ToString().StartsWith(Entry.SlateTypeName.ToString(), ESearchCase::CaseSensitive);
}
}

// ================== 控件类型登记表 ==================

// 获取控件类型登记表
// 采用 "函数内 static" 惯用法: 首次调用时构建数组并常驻内存,
// 之后每次调用都返回同一份只读数据, 线程安全且无重复构建开销
const TArray<FLQAWidgetTypeDesc>& FLQAWidgetTypeRegistry::GetEntries()
{
	// 引入 Slate 名常量所在命名空间, 下方可直接写 LQA_SizeBox 等短名
	using namespace LQAWidgetNames;

	// 登记项字段顺序: {Slate 类型名, UMG 类约束, LQA 类型枚举, WidgetClass 标签, 是否前缀匹配}
	static const TArray<FLQAWidgetTypeDesc> Entries = {
		// ===== Slate 根类型复用组: 同一 Slate 名对应多个 UMG 控件, 必须带 WidgetClass =====

		// SizeBox 组: 这些控件的 Slate 根都是 SBox, 仅靠 Slate 名无法区分, 故各带 UMG 类约束
		{LQA_SizeBox, USizeBox::StaticClass(), ELQAWidgetType::LQA_SizeBox, TEXT("SizeBox")},
		{LQA_NamedSlot, UNamedSlot::StaticClass(), ELQAWidgetType::LQA_NamedSlot, TEXT("NamedSlot")},
		{LQA_NativeWidgetHost, UNativeWidgetHost::StaticClass(), ELQAWidgetType::LQA_NativeWidgetHost,
			TEXT("NativeWidgetHost")},
		// CommonUI 按钮内部根容器 InternalRootButtonBase: Slate 根为 SBox, UMG 侧 UCommonButtonInternalBase
		// 继承 UButton (非 USizeBox), 故补一条以 UButton 作类约束的 SBox 映射, 使其归入 SizeBox。
		{LQA_SizeBox, UButton::StaticClass(), ELQAWidgetType::LQA_SizeBox},

		// ComboBox 组: Slate 名带模板实参 (SComboBox<...>) 故按前缀匹配;
		// 三者归为同一 LQA 类型, 仅 WidgetClass 标签不同以便在 JSON 中区分
		{LQA_ComboBox, UComboBox::StaticClass(), ELQAWidgetType::LQA_ComboBoxStringText, TEXT("ComboBox"), true},
		{LQA_ComboBox, UComboBoxString::StaticClass(), ELQAWidgetType::LQA_ComboBoxStringText, TEXT("ComboBoxString"),
			true},
#if ENGINE_MAJOR_VERSION >= 5
		{LQA_ComboBox, UComboBoxKey::StaticClass(), ELQAWidgetType::LQA_ComboBoxStringText, TEXT("ComboBoxKey"), true},
#endif

		// 动态条目框组: Slate 根按 EntryBoxType 为 SHorizontalBox / SVerticalBox / SWrapBox,
		{LQA_HorizontalBox, UDynamicEntryBox::StaticClass(), ELQAWidgetType::LQA_DynamicEntryBox,
			TEXT("DynamicEntryBox")},
		{LQA_VerticalBox, UDynamicEntryBox::StaticClass(), ELQAWidgetType::LQA_DynamicEntryBox,
			TEXT("DynamicEntryBox")},
		{LQA_WrapBox, UDynamicEntryBox::StaticClass(), ELQAWidgetType::LQA_DynamicEntryBox,
			TEXT("DynamicEntryBox")},

		// ===== 1:1 类型: Slate 名与 LQA 类型一一对应, WidgetClass 留空, 仅按 Slate 名匹配 =====

		// 文本类
		{LQA_TextBlock, nullptr, ELQAWidgetType::LQA_TextBlock},
		{LQA_RichTextBlock, nullptr, ELQAWidgetType::LQA_RichText},
		{LQA_EditableText, nullptr, ELQAWidgetType::LQA_EditableText},
		{LQA_EditableTextBox, nullptr, ELQAWidgetType::LQA_EditableTextBox},
		{LQA_MultilineEditableText, nullptr, ELQAWidgetType::LQA_MultilineEditableText},
		{LQA_MultilineEditableTextBox, nullptr, ELQAWidgetType::LQA_MultilineEditableTextBox},
		{LQA_TextScroller, nullptr, ELQAWidgetType::LQA_TextScroller},
		{LQA_LEDRichTextBlock, nullptr, ELQAWidgetType::LQA_LEDRichText},
		{LQA_InputKeySelector, nullptr, ELQAWidgetType::LQA_InputKeySelector},

		// 可视化类
		{LQA_Image, nullptr, ELQAWidgetType::LQA_Image},
		{LQA_Button, nullptr, ELQAWidgetType::LQA_Button},
		{LQA_CheckBox, nullptr, ELQAWidgetType::LQA_CheckBox},

		// 容器类
		{LQA_UserWidget, nullptr, ELQAWidgetType::LQA_UserWidget},
		{LQA_Canvas, nullptr, ELQAWidgetType::LQA_Canvas},
		{LQA_RetainerBox, nullptr, ELQAWidgetType::LQA_RetainerBox},
		{LQA_ScrollBox, nullptr, ELQAWidgetType::LQA_ScrollBox},
		// CommonUI 分层滚动框: Slate 根 SCommonHierarchicalScrollBox 继承 SScrollBox, 归入 ScrollBox 采集/还原
		{LQA_CommonHierarchicalScrollBox, nullptr, ELQAWidgetType::LQA_ScrollBox},
		{LQA_VerticalBox, nullptr, ELQAWidgetType::LQA_VerticalBox},
		{LQA_HorizontalBox, nullptr, ELQAWidgetType::LQA_HorizontalBox},
		{LQA_ScaleBox, nullptr, ELQAWidgetType::LQA_ScaleBox},
		{LQA_SafeZone, nullptr, ELQAWidgetType::LQA_SafeZone},
		{LQA_WrapBox, nullptr, ELQAWidgetType::LQA_WrapBox},
		{LQA_GridPanel, nullptr, ELQAWidgetType::LQA_GridPanel},
		{LQA_UniformGridPanel, nullptr, ELQAWidgetType::LQA_UniformGridPanel},
		{LQA_Overlay, nullptr, ELQAWidgetType::LQA_Overlay},
		{LQA_Border, nullptr, ELQAWidgetType::LQA_Border},
		{LQA_BackgroundBlur, nullptr, ELQAWidgetType::LQA_BackgroundBlur},
		{LQA_WidgetSwitcher, nullptr, ELQAWidgetType::LQA_WidgetSwitcher},
		{LQA_StackBox, nullptr, ELQAWidgetType::LQA_StackBox},
		{LQA_WindowTitleBarArea, nullptr, ELQAWidgetType::LQA_WindowTitleBarArea},
		{LQA_MenuAnchor, nullptr, ELQAWidgetType::LQA_MenuAnchor},
		{LQA_InvalidationBox, nullptr, ELQAWidgetType::LQA_InvalidationBox},
		{LQA_ScrollBar, nullptr, ELQAWidgetType::LQA_ScrollBar},
		{LQA_PostBufferUpdate, nullptr, ELQAWidgetType::LQA_PostBufferUpdate},
		{LQA_ObjectTableRow, nullptr, ELQAWidgetType::LQA_UserWidget}, // 列表行控件: Slate 根为 ObjectTableRowT, 按 UserWidget 采集以保留类型与子树
		{LQA_ListView, nullptr, ELQAWidgetType::LQA_ListView},
		{LQA_TileView, nullptr, ELQAWidgetType::LQA_TileView},
		{LQA_TreeView, nullptr, ELQAWidgetType::LQA_TreeView},
		{LQA_ExpandableArea, nullptr, ELQAWidgetType::LQA_ExpandableArea},

		// 输入类
		{LQA_ProgressBar, nullptr, ELQAWidgetType::LQA_ProgressBar},
		{LQA_Slider, nullptr, ELQAWidgetType::LQA_Slider},
		// Slider 的 Slate 名固定; 而 SpinBox 运行时名为 SSpinBox<float>, 故需前缀匹配
		{LQA_SpinBox, nullptr, ELQAWidgetType::LQA_SpinBox, NAME_None, true},

		// 展示类
		{LQA_Throbber, nullptr, ELQAWidgetType::LQA_Throbber},
		{LQA_CircularThrobber, nullptr, ELQAWidgetType::LQA_CircularThrobber},
		{LQA_Spacer, nullptr, ELQAWidgetType::LQA_Spacer},

		// 项目自定义控件类型可在此处追加新条目
	};

	return Entries;
}

namespace
{
struct FWrappedWidgetClassDesc
{
	UClass* WidgetClass;
	ELQAWidgetType WidgetType;
};

ELQAWidgetType ResolveWrappedWidgetType(const UWidget* SourceWidget)
{
	static const TArray<FWrappedWidgetClassDesc> WrappedClasses = {
		{UTextBlock::StaticClass(), ELQAWidgetType::LQA_TextBlock},
		{URichTextBlock::StaticClass(), ELQAWidgetType::LQA_RichText},
		{UEditableText::StaticClass(), ELQAWidgetType::LQA_EditableText},
		{UEditableTextBox::StaticClass(), ELQAWidgetType::LQA_EditableTextBox},
		{UMultiLineEditableText::StaticClass(), ELQAWidgetType::LQA_MultilineEditableText},
		{UMultiLineEditableTextBox::StaticClass(), ELQAWidgetType::LQA_MultilineEditableTextBox},
		{UImage::StaticClass(), ELQAWidgetType::LQA_Image},
	};

	for (const FWrappedWidgetClassDesc& Desc : WrappedClasses)
	{
		if (SourceWidget->IsA(Desc.WidgetClass))
		{
			return Desc.WidgetType;
		}
	}
	return ELQAWidgetType::LQA_Undefined;
}
}  // namespace

// 判定控件类型: 依次按 "精确类 → IsA → 无约束" 三轮扫描登记表
// 分三轮而非一轮的原因: 保证高优先级规则先命中,
// 避免父类条目 (如 UComboBox) 抢走本应属于子类 (如 UComboBoxKey) 的匹配
const FLQAWidgetTypeDesc* FLQAWidgetTypeRegistry::TryGetWidgetTypeDesc(
	const FName& SlateTypeName, const UObject* SourceObject)
{
	const TArray<FLQAWidgetTypeDesc>& Entries = GetEntries();

	// 来源对象可能并非 UWidget (或为空), Cast 失败时 SourceWidget 为 nullptr,
	// 届时跳过前两轮类约束匹配, 仅走第 3 轮无约束匹配
	const UWidget* SourceWidget = Cast<UWidget>(SourceObject);

	// SInvalidationPanel 也用作 TextBlock 的包装层, 此时按 UMG 类判定
	if (SourceWidget && SlateTypeName == LQAWidgetNames::LQA_InvalidationBox)
	{
		const ELQAWidgetType WrappedType = ResolveWrappedWidgetType(SourceWidget);
		if (WrappedType != ELQAWidgetType::LQA_Undefined)
		{
			for (const FLQAWidgetTypeDesc& Entry : Entries)
			{
				if (Entry.WidgetType == WrappedType && Entry.WidgetClass == nullptr)
				{
					return &Entry;
				}
			}
		}
	}

	if (SourceWidget)
	{
		const UClass* SourceClass = SourceWidget->GetClass();

		// 第 1 轮: 精确类匹配 (类完全相等)
		// 优先级最高, 确保 UComboBoxKey 不会被父类 UComboBox 的条目先命中
		for (const FLQAWidgetTypeDesc& Entry : Entries)
		{
			if (Entry.WidgetClass && SourceClass == Entry.WidgetClass && IsSlateNameMatched(Entry, SlateTypeName))
			{
				return &Entry;
			}
		}

		// 第 2 轮: IsA 匹配 (是某登记类的子类)
		// 覆盖蓝图继承场景, 例如一个 WBP 继承自 USizeBox, 其精确类不在表中,
		// 但 IsA(USizeBox) 为真, 可归入 SizeBox 类型
		for (const FLQAWidgetTypeDesc& Entry : Entries)
		{
			if (Entry.WidgetClass && SourceWidget->IsA(Entry.WidgetClass) && IsSlateNameMatched(Entry, SlateTypeName))
			{
				return &Entry;
			}
		}
	}

	// 第 3 轮: 无 UMG 类约束的条目 (1:1 类型), 仅凭 Slate 名判定
	for (const FLQAWidgetTypeDesc& Entry : Entries)
	{
		if (!Entry.WidgetClass && IsSlateNameMatched(Entry, SlateTypeName))
		{
			return &Entry;
		}
	}

	// 三轮均未命中: 通常是未登记的 Slate 内部控件 (无需作为 LQA 节点处理)
	return nullptr;
}