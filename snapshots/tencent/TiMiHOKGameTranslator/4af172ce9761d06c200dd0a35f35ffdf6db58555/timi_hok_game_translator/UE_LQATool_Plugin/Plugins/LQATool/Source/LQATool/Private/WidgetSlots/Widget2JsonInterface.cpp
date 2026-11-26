#include "WidgetSlots/Widget2JsonInterface.h"

#include "Components/EditableText.h"              // 单行可编辑文本
#include "Components/EditableTextBox.h"           // 单行可编辑文本框
#include "Components/MultiLineEditableText.h"     // 多行可编辑文本
#include "Components/MultiLineEditableTextBox.h"  // 多行可编辑文本框
#include "Components/RichTextBlock.h"             // 富文本块
#include "Components/TextBlock.h"                 // 普通文本块
#include "Slate/SObjectTableRow.h"                // 列表条目 Slate 根 (GetIndentLevel 层级深度)
#include "Snapshot/LQAWidgetNode.h"               // 控件节点定义
#include "Styling/SlateColor.h"                   // Slate 颜色类型
#include "WidgetSlots/WidgetDefines.h"            // 公共字段名/常量定义

// 定义 (实现) 头文件中声明的日志分类
DEFINE_LOG_CATEGORY(LogLQAToolWidget2Json);

// 将文本及其本地化信息写入 JSON 对象
void FWidget2JsonInterface::WriteTextEntry_ToJson(const TSharedPtr<FJsonObject>& JsonObj, const FText& Text,
	const FString& TextEntryName, const FString& TextKeyName, const FString& SourceStringKeyName)
{
	// 校验入参: JSON 对象无效则记录警告并提前返回
	if (!JsonObj.IsValid())
	{
		UE_LOG(LogLQAToolWidget2Json, Warning, TEXT("WriteTextEntry_ToJson: Invalid JsonObj pointer"));
		return;
	}

	// 写入显示文本 (当前语言下实际呈现的字符串)
	JsonObj->SetStringField(*TextEntryName, *Text.ToString());

	// 如果文本非空, 则尝试写入其源字符串 (本地化前的原始文本)
	if (!Text.IsEmpty())
	{
		const FString* SourceString = FTextInspector::GetSourceString(Text);
		if (SourceString && !SourceString->IsEmpty())
		{
			JsonObj->SetStringField(SourceStringKeyName, *SourceString);
		}
	}

	// 写入本地化键信息 (命名空间 + 键)
	if (!Text.IsEmpty())
	{
		FString Namespace, Key;
		GetTextNamespaceAndKey(Text, Namespace, Key);

		// 命名空间与键都有效时, 以 "Namespace,Key" 的格式写入
		if (!Namespace.IsEmpty() && !Key.IsEmpty())
		{
			JsonObj->SetStringField(*TextKeyName, FString::Printf(TEXT("%s,%s"), *Namespace, *Key));
		}
		else
		{
			// 否则写入预定义的无效键标记
			JsonObj->SetStringField(*TextKeyName, InvalidTextKey);
		}
	}
}

// 从本地化文本中提取命名空间与键
void FWidget2JsonInterface::GetTextNamespaceAndKey(const FText& Text, FString& OutNamespace, FString& OutKey)
{
	// 通过文本检查器获取命名空间, 取不到时默认为空字符串
	OutNamespace = FTextInspector::GetNamespace(Text).Get(TEXT(""));

#if WITH_EDITOR
	// 仅在编辑器构建下执行:
	// 编辑器中命名空间可能带有尾部附加信息 (如 " <包路径>"),
	// 这里从末尾按空格切分, 仅保留前半段作为 “干净” 的命名空间
	FString NamespaceLeft, NamespaceRight;
	if (OutNamespace.Split(TEXT(" "), &NamespaceLeft, &NamespaceRight, ESearchCase::IgnoreCase, ESearchDir::FromEnd))
	{
		if (!NamespaceLeft.IsEmpty())
		{
			OutNamespace = NamespaceLeft;
		}
	}
#endif

	// 通过文本检查器获取键, 取不到时默认为 "INVALIDKEY"
	OutKey = FTextInspector::GetKey(Text).Get(TEXT("INVALIDKEY"));
}

// ============================================================================
// 列表条目文本收集 (ListView / TileView / TreeView 通用)
// ============================================================================

namespace
{
/**
 * 从文本类控件节点读取显示文本
 * 覆盖常见的文本控件类型 (条目文本不仅限于 TextBlock)
 */
FText GetNodeText(const TSharedRef<FLQAWidgetNode>& Node)
{
	UObject* Source = Node->SourceObject.Get();
	if (!Source)
	{
		return FText::GetEmpty();
	}

	switch (Node->GetNodeType())
	{
		case ELQAWidgetType::LQA_TextBlock:
			if (const UTextBlock* Widget = Cast<UTextBlock>(Source))
			{
				return Widget->GetText();
			}
			break;
		case ELQAWidgetType::LQA_RichText:
			if (const URichTextBlock* Widget = Cast<URichTextBlock>(Source))
			{
				return Widget->GetText();
			}
			break;
		case ELQAWidgetType::LQA_EditableText:
			if (const UEditableText* Widget = Cast<UEditableText>(Source))
			{
				return Widget->GetText();
			}
			break;
		case ELQAWidgetType::LQA_EditableTextBox:
			if (const UEditableTextBox* Widget = Cast<UEditableTextBox>(Source))
			{
				return Widget->GetText();
			}
			break;
		case ELQAWidgetType::LQA_MultilineEditableText:
			if (const UMultiLineEditableText* Widget = Cast<UMultiLineEditableText>(Source))
			{
				return Widget->GetText();
			}
			break;
		case ELQAWidgetType::LQA_MultilineEditableTextBox:
			if (const UMultiLineEditableTextBox* Widget = Cast<UMultiLineEditableTextBox>(Source))
			{
				return Widget->GetText();
			}
			break;
		default:
			break;
	}
	return FText::GetEmpty();
}

/**
 * 在节点子树中深度优先查找第一个文本节点, 并把其文本写入 OutJson
 * @return 找到并写入返回 true
 */
bool WriteFirstTextEntry(const TSharedRef<FLQAWidgetNode>& Node, const TSharedPtr<FJsonObject>& OutJson)
{
	const FText Text = GetNodeText(Node);
	if (!Text.IsEmpty())
	{
		FWidget2JsonInterface::WriteTextEntry_ToJson(OutJson, Text);
		return true;
	}

	// 递归查找子节点
	for (const TSharedRef<FLQAWidgetNode>& Child : Node->GetChildNodes())
	{
		if (WriteFirstTextEntry(Child, OutJson))
		{
			return true;
		}
	}
	return false;
}

/**
 * 读取条目的层级深度 (TreeView 使用; ListView/TileView 无嵌套, 恒为 0)
 * 条目的 Slate 根为 SObjectTableRow, 其 GetIndentLevel 返回在树中的嵌套深度。
 */
int32 GetNodeDepth(const TSharedRef<FLQAWidgetNode>& Node)
{
	if (Node->CachedWidget.IsValid())
	{
		if (const TSharedPtr<SObjectTableRow<UObject*>> Row =
				StaticCastSharedPtr<SObjectTableRow<UObject*>>(Node->CachedWidget))
		{
			return Row->GetIndentLevel();
		}
	}
	return 0;
}
}  // namespace

void FWidget2JsonInterface::CollectListEntryTexts(
	const TSharedPtr<FLQAWidgetNode>& InWidget, TArray<TSharedPtr<FJsonValue>>& OutListItems)
{
	if (!InWidget.IsValid())
	{
		return;
	}

	// 下钻 Slate 内部包装层 (UNDEFINE 且无名字), 定位条目层
	TSharedPtr<FLQAWidgetNode> Cursor = InWidget;
	while (Cursor.IsValid())
	{
		const TArray<TSharedRef<FLQAWidgetNode>>& Children = Cursor->GetChildNodes();
		if (Children.Num() == 0)
		{
			return;
		}

		// 出现多个子节点: 当前层级即条目层
		if (Children.Num() > 1)
		{
			for (const TSharedRef<FLQAWidgetNode>& Entry : Children)
			{
				TSharedPtr<FJsonObject> ItemJson = MakeShared<FJsonObject>();
				if (WriteFirstTextEntry(Entry, ItemJson))
				{
					// 附带层级深度, 供还原端重建 TreeView 父子结构
					ItemJson->SetNumberField(TEXT("Depth"), GetNodeDepth(Entry));
					OutListItems.Add(MakeShared<FJsonValueObject>(ItemJson));
				}
			}
			return;
		}

		// 单子节点: 是内部包装节点则继续下钻, 否则它就是唯一条目
		const TSharedRef<FLQAWidgetNode>& OnlyChild = Children[0];
		const bool bInternalWrapper =
			OnlyChild->GetNodeType() == ELQAWidgetType::LQA_Undefined && OnlyChild->WidgetName == NAME_None;
		if (!bInternalWrapper)
		{
			TSharedPtr<FJsonObject> ItemJson = MakeShared<FJsonObject>();
			if (WriteFirstTextEntry(OnlyChild, ItemJson))
			{
				ItemJson->SetNumberField(TEXT("Depth"), GetNodeDepth(OnlyChild));
				OutListItems.Add(MakeShared<FJsonValueObject>(ItemJson));
			}
			return;
		}

		Cursor = OnlyChild;
	}
}
