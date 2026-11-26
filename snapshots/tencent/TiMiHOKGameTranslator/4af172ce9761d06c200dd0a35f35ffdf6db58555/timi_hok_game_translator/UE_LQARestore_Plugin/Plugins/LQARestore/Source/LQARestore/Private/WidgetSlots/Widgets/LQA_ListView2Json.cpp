#include "WidgetSlots/Widgets/LQA_ListView2Json.h"

#include "Blueprint/WidgetTree.h"
#include "Components/ListView.h"
#include "Components/ListViewBase.h"
#include "Components/TileView.h"
#include "Components/TreeView.h"
#include "Core/RestoreWindowProxy.h"
#include "Core/RootObjWidget.h"
#include "JsonObjectConverter.h"
#include "UObject/UnrealType.h"
#include "Utils/JsonUtils.h"
#include "WidgetSlots/Core/WidgetDefines.h"
#include "WidgetSlots/Widgets/LQA_ListViewEntry.h"

#if ENGINE_MAJOR_VERSION < 5 && WITH_EDITOR
#include "Engine/Blueprint.h"
#endif

using namespace LQAWidgetConstants;

namespace
{
/**
 * 三种列表控件的还原逻辑完全一致: 按 ObjectData 重建控件本身。
 *
 * 列表控件必须挂到根控件的 WidgetTree 下 (Outer = WidgetTree), 否则列表生成条目控件时
 * UUserWidget::CreateWidgetInstance 会沿 Outer 链寻找 ParentUserWidget->WidgetTree,
 * 找不到会返回 nullptr 并在 GenerateTypedEntry 中触发 check(ListEntryWidget) 崩溃。
 *
 * @param JsonData           当前节点的 JSON
 * @param RestoreWindowProxy 还原上下文, 用于取根控件的 WidgetTree
 * @param InWidgetLabel      仅用于日志
 * @return 重建的控件; 失败时退化为空控件, 保证节点不被整体跳过
 */
template <typename TViewWidget>
TViewWidget* CreateViewWidget(
	const TSharedPtr<FJsonObject>& JsonData, URestoreWindowProxy* RestoreWindowProxy, const TCHAR* InWidgetLabel)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for %s"), InWidgetLabel);
		return nullptr;
	}

	UWidgetTree* WidgetTree = nullptr;
	if (RestoreWindowProxy && RestoreWindowProxy->GetRootWidget())
	{
		WidgetTree = RestoreWindowProxy->GetRootWidget()->WidgetTree;
	}

	TViewWidget* Widget = nullptr;
	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = WidgetTree ? WidgetTree->ConstructWidget<TViewWidget>(TViewWidget::StaticClass(), NAME_None)
								: NewObject<TViewWidget>();
			FJsonUtils::StandardizeCaseForImport(ObjectData, TViewWidget::StaticClass());
			// 反序列化失败时复用已创建的对象作为空控件, 保证节点仍出现在还原结果中
			FJsonObjectConverter::JsonObjectToUStruct(
				ObjectData.ToSharedRef(), TViewWidget::StaticClass(), Widget, 0, 0);
		}
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Warning,
			TEXT("Restore %s failed, fallback to an empty widget. Check EntryWidgetClass."), InWidgetLabel);
		Widget = WidgetTree ? WidgetTree->ConstructWidget<TViewWidget>(TViewWidget::StaticClass(), NAME_None)
							: NewObject<TViewWidget>();
	}

	return Widget;
}

/**
 * 把列表的 EntryWidgetClass 替换为通用条目控件, 并标记为已 cook
 *
 * EntryWidgetClass 在 UListViewBase 中是 protected 且无 setter, 通过反射替换。
 * 编辑器构建下 UListViewBase::RebuildWidget 要求 EntryWidgetClass 为蓝图类 (或已 cook 的原生类),
 * 否则整表会被替换成错误提示文本, 因此无论是否有条目都先把通用条目类标记为已 cook。
 *
 * @return 成功返回 true
 */
bool PrepareEntryWidgetClass(UListViewBase* View)
{
	FClassProperty* EntryClassProperty =
		FindFProperty<FClassProperty>(UListViewBase::StaticClass(), TEXT("EntryWidgetClass"));
	if (!EntryClassProperty)
	{
		UE_LOG(LogLQARestoreWidget2Json, Warning,
			TEXT("Cannot find EntryWidgetClass on UListViewBase, list entries will not be restored."));
		return false;
	}

	ULQARestoreListEntryWidget::StaticClass()->bCooked = true;
#if ENGINE_MAJOR_VERSION < 5 && WITH_EDITOR
	if (!ULQARestoreListEntryWidget::StaticClass()->ClassGeneratedBy)
	{
		UBlueprint* EntryWidgetShell = NewObject<UBlueprint>(GetTransientPackage(), NAME_None, RF_Transient);
		EntryWidgetShell->ParentClass = ULQARestoreListEntryWidget::StaticClass()->GetSuperClass();
		EntryWidgetShell->GeneratedClass = ULQARestoreListEntryWidget::StaticClass();
		EntryWidgetShell->SkeletonGeneratedClass = ULQARestoreListEntryWidget::StaticClass();
		EntryWidgetShell->Status = BS_UpToDate;
		EntryWidgetShell->AddToRoot();
		ULQARestoreListEntryWidget::StaticClass()->ClassGeneratedBy = EntryWidgetShell;
	}
#endif
	EntryClassProperty->SetObjectPropertyValue_InContainer(View, ULQARestoreListEntryWidget::StaticClass());
	return true;
}

/**
 * 依据采集端导出的 ListItems 重建列表项 (ListView / TileView 平铺)
 *
 * 采集端已把每个条目的文本 (textStr/TextKey/SourceString) 抽成 ListItems 数组,
 * 这里直接读取并翻译, 用 ULQARestoreListItem 作为数据项加入列表。
 * 快照不包含列表项数据 (UListView::ListItems 为 Transient), 只能这样注入。
 *
 * @param View     刚创建出来的列表控件
 * @param JsonData 该节点的 JSON
 */
template <typename TViewWidget>
void ApplyListEntries(TViewWidget* View, const TSharedPtr<FJsonObject>& JsonData)
{
	if (!View || !JsonData.IsValid() || !PrepareEntryWidgetClass(View))
	{
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* ListItems = nullptr;
	if (!JsonData->TryGetArrayField(TEXT("ListItems"), ListItems) || !ListItems || ListItems->Num() == 0)
	{
		return;
	}

	for (const TSharedPtr<FJsonValue>& ItemValue : *ListItems)
	{
		const TSharedPtr<FJsonObject> ItemJson = ItemValue.IsValid() ? ItemValue->AsObject() : nullptr;
		const FText Label = ItemJson.IsValid() ? FWidget2JsonInterface::GetTextFromJson(ItemJson) : FText::GetEmpty();

		ULQARestoreListItem* Item = NewObject<ULQARestoreListItem>(View);
		Item->Label = Label;
		View->AddItem(Item);
	}

	UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("Restored %d list entries."), ListItems->Num());
}

/**
 * 依据采集端导出的 ListItems 重建树形条目 (TreeView, 支持层级)
 *
 * 采集端在每个条目上附带 Depth (层级深度), 这里用栈式算法由前序序列重建父子关系,
 * 并通过 SetOnGetItemChildren 让 TreeView 能递归展开子节点。
 */
void ApplyTreeEntries(UTreeView* View, const TSharedPtr<FJsonObject>& JsonData)
{
	if (!View || !JsonData.IsValid() || !PrepareEntryWidgetClass(View))
	{
		return;
	}

	const TArray<TSharedPtr<FJsonValue>>* ListItems = nullptr;
	if (!JsonData->TryGetArrayField(TEXT("ListItems"), ListItems) || !ListItems || ListItems->Num() == 0)
	{
		return;
	}

	// 先设置子节点回调, 再注入根节点数据
	ULQARestoreTreeChildrenResolver* Resolver = NewObject<ULQARestoreTreeChildrenResolver>(View);
	View->SetOnGetItemChildren(Resolver, &ULQARestoreTreeChildrenResolver::GetChildren);

	// 栈式重建: 栈保存当前路径, 弹出到与 Depth 对齐后挂到父节点
	TArray<ULQARestoreListItem*> Roots;
	TArray<ULQARestoreListItem*> Stack;
	for (const TSharedPtr<FJsonValue>& ItemValue : *ListItems)
	{
		const TSharedPtr<FJsonObject> ItemJson = ItemValue.IsValid() ? ItemValue->AsObject() : nullptr;
		if (!ItemJson.IsValid())
		{
			continue;
		}

		const FText Label = FWidget2JsonInterface::GetTextFromJson(ItemJson);
		double DepthValue = 0.0;
		ItemJson->TryGetNumberField(TEXT("Depth"), DepthValue);
		const int32 Depth = FMath::RoundToInt(DepthValue);

		ULQARestoreListItem* Item = NewObject<ULQARestoreListItem>(View);
		Item->Label = Label;

		while (Stack.Num() > Depth)
		{
			Stack.Pop();
		}

		if (Stack.Num() == 0)
		{
			Roots.Add(Item);
		}
		else
		{
			Stack.Last()->Children.Add(Item);
		}
		Stack.Add(Item);
	}

	for (ULQARestoreListItem* Root : Roots)
	{
		View->AddItem(Root);
	}

	UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("Restored %d tree entries (%d roots)."), ListItems->Num(), Roots.Num());
}
}  // namespace

/**
 * TreeView 子节点解析器实现
 * 提供 OnGetItemChildren 回调所需的方法: 从条目数据对象的 Children 数组取出子节点。
 * 采用 UObject 实现, 因为 UE4 的 SetOnGetItemChildren 只接受 UObject 方法委托。
 */
void ULQARestoreTreeChildrenResolver::GetChildren(UObject* Item, TArray<UObject*>& OutChildren)
{
	if (const ULQARestoreListItem* ListItem = Cast<ULQARestoreListItem>(Item))
	{
		for (ULQARestoreListItem* Child : ListItem->Children)
		{
			if (Child)
			{
				OutChildren.Add(Child);
			}
		}
	}
}

UWidget* FLQA_ListView2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	UListView* Widget = CreateViewWidget<UListView>(JsonData, RestoreWindowProxy, TEXT("ListView"));
	ApplyListEntries(Widget, JsonData);
	return Widget;
}

ELQAWidgetType FLQA_ListView2Json::GetType()
{
	return ELQAWidgetType::LQA_ListView;
}

UWidget* FLQA_TileView2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	UTileView* Widget = CreateViewWidget<UTileView>(JsonData, RestoreWindowProxy, TEXT("TileView"));
	ApplyListEntries(Widget, JsonData);
	return Widget;
}

ELQAWidgetType FLQA_TileView2Json::GetType()
{
	return ELQAWidgetType::LQA_TileView;
}

UWidget* FLQA_TreeView2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	UTreeView* Widget = CreateViewWidget<UTreeView>(JsonData, RestoreWindowProxy, TEXT("TreeView"));
	ApplyTreeEntries(Widget, JsonData);
	return Widget;
}

ELQAWidgetType FLQA_TreeView2Json::GetType()
{
	return ELQAWidgetType::LQA_TreeView;
}
