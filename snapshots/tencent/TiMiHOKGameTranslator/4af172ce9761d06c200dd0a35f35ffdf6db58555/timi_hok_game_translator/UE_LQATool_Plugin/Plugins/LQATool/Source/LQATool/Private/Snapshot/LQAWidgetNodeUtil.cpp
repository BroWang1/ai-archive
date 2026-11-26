#include "Snapshot/LQAWidgetNodeUtil.h"

#include "Components/ExpandableArea.h"   // UExpandableArea: 命名插槽 (Header/Body) 容器
#include "Components/Widget.h"           // UWidget: 获取命名插槽内容的 CachedWidget
#include "Debugging/SlateDebugging.h"
#include "Layout/ArrangedChildren.h"     // FArrangedChildren: 子控件排布结果容器
#include "Layout/Children.h"             // FChildren: Slate 控件子节点容器的抽象接口
#include "Misc/Optional.h"               // TOptional: 表示可能存在的排布节点
#include "Snapshot/LQAWidgetNode.h"      // 控件节点类型 FLQAWidgetNode
#include "Types/ReflectionMetadata.h"    // Slate 反射元数据 (用于获取控件调试/标识信息)

// 关闭当前编译单元的代码优化
// 常用于调试: 便于在该文件内逐行断点调试递归逻辑, 避免优化导致变量被折叠或无法观察
#if ENGINE_MAJOR_VERSION >= 5
UE_DISABLE_OPTIMIZATION
#else
PRAGMA_DISABLE_OPTIMIZATION
#endif

namespace
{
/**
 * 为从未参与绘制的控件补一次 Tick。
 * 绘制期几何为 0 表示该控件从未被绘制与 Tick, 其按需构建的子内容尚未生成。
 */
void TickIfNeverPainted(const TSharedRef<SWidget>& Widget, const FGeometry& InGeometry)
{
	if (!Widget->GetTickSpaceGeometry().GetLocalSize().IsNearlyZero() || InGeometry.GetLocalSize().IsNearlyZero())
	{
		return;
	}

	Widget->Tick(InGeometry, FPlatformTime::Seconds(), 0.0f);
}

/**
 * 在排布结果中递归查找指定 Slate 控件, 返回其携带正确几何的排布节点。
 * 用于穿透命名插槽容器 (如 SExpandableArea) 内部的 Slate 包装层 (SBorder/SButton 等),
 * 定位真正的命名插槽内容控件, 从而拿到其正确坐标与尺寸。
 */
TOptional<FArrangedWidget> FindArrangedWidget(
	const TSharedRef<SWidget>& Target, const FArrangedChildren& InChildren)
{
	for (int32 ChildIndex = 0; ChildIndex < InChildren.Num(); ++ChildIndex)
	{
		const FArrangedWidget& Child = InChildren[ChildIndex];
		if (Child.Widget == Target)
		{
			return TOptional<FArrangedWidget>(Child);
		}

		// 递归子层级继续查找
		FArrangedChildren GrandChildren(EVisibility::Visible);
#if ENGINE_MAJOR_VERSION >= 5
		Child.Widget->ArrangeChildren(Child.Geometry, GrandChildren, true);
#else
		Child.Widget->ArrangeChildren(Child.Geometry, GrandChildren);
#endif
		TOptional<FArrangedWidget> Found = FindArrangedWidget(Target, GrandChildren);
		if (Found.IsSet())
		{
			return Found;
		}
	}
	return TOptional<FArrangedWidget>();
}
}  // namespace

/**
 * 根据已排布的控件几何信息, 递归构建控件节点树。
 * 子控件几何取自当前控件的排布结果, 不依赖控件是否被绘制。
 */
TSharedRef<FLQAWidgetNode> FLQAWidgetNodeUtil::GetNodeFromTree(const FArrangedWidget& InWidgetGeometry, int32& Index)
{
	// 取出当前要处理的控件引用
	const TSharedRef<SWidget> CurrentWidget = InWidgetGeometry.Widget;

	// 为当前控件创建一个新的节点实例 (携带其排布几何信息)
	TSharedRef<FLQAWidgetNode> NewNodeInstance = MakeShared<FLQAWidgetNode>(InWidgetGeometry);

	// 索引自增, 并作为该节点的唯一 NodeId (引用传入, 整棵树范围内持续累加)
	++Index;
	NewNodeInstance->SetNodeId(Index);

	// 视口外的子树不会进入绘制流程, 先按排布几何补一次 Tick, 使其按需构建的子内容就位
	TickIfNeverPainted(CurrentWidget, InWidgetGeometry.Geometry);

	// 特殊处理 UExpandableArea: 其 Header/Body 是命名插槽内容, 直接采集对应的 UWidget,
	// 避免递归进入 SExpandableArea 内部的 Slate 包装层 (SBorder/SButton/SHorizontalBox 等)。
	// 这些内部包装层没有 UMG 反射元数据, 会被识别为 UNDEFINE, 导致内容丢失。
	if (UExpandableArea* ExpandableArea = Cast<UExpandableArea>(NewNodeInstance->SourceObject.Get()))
	{
		// 主动排布一次, 让命名插槽内容获得正确几何 (滚出视口的控件可能从未被 Tick)
		FArrangedChildren ArrangedChildren(EVisibility::Visible);
#if ENGINE_MAJOR_VERSION >= 5
		CurrentWidget->ArrangeChildren(InWidgetGeometry.Geometry, ArrangedChildren, true);
#else
		CurrentWidget->ArrangeChildren(InWidgetGeometry.Geometry, ArrangedChildren);
#endif

		TArray<FName> SlotNames;
		ExpandableArea->GetSlotNames(SlotNames);

		for (const FName& SlotName : SlotNames)
		{
			UWidget* Content = ExpandableArea->GetContentForSlot(SlotName);
			if (!IsValid(Content))
			{
				continue;
			}

			TSharedPtr<SWidget> ContentWidget = Content->GetCachedWidget();
			if (!ContentWidget.IsValid())
			{
				continue;
			}

			// 从排布结果中穿透包装层, 找到内容控件对应的排布节点 (携带正确几何)
			TOptional<FArrangedWidget> ArrangedContent =
				FindArrangedWidget(ContentWidget.ToSharedRef(), ArrangedChildren);
			if (ArrangedContent.IsSet())
			{
				TSharedRef<FLQAWidgetNode> ChildNode = GetNodeFromTree(ArrangedContent.GetValue(), Index);
				ChildNode->SlotName = SlotName;  // 记录命名插槽名, 供还原侧区分 Header/Body
				NewNodeInstance->AddChildNode(ChildNode);
			}
		}

		return NewNodeInstance;
	}

	// 无子控件容器或容器为空时, 当前节点即为叶子节点。
	FChildren* ChildrenContainer = nullptr;
#if WITH_SLATE_DEBUGGING && ENGINE_MAJOR_VERSION >= 5
	ChildrenContainer = CurrentWidget->Debug_GetChildrenForReflector();
#else
	ChildrenContainer = CurrentWidget->GetChildren();
#endif

	if (!ChildrenContainer || ChildrenContainer->Num() == 0)
	{
		return NewNodeInstance;
	}

	// 取当前控件的排布结果: 可见性过滤由容器完成, Collapsed / Hidden 子控件不会进入结果
	FArrangedChildren ArrangedChildren(EVisibility::Visible);
#if ENGINE_MAJOR_VERSION >= 5
	CurrentWidget->ArrangeChildren(InWidgetGeometry.Geometry, ArrangedChildren, true);
#else
	CurrentWidget->ArrangeChildren(InWidgetGeometry.Geometry, ArrangedChildren);
#endif

	// 遍历所有已完成排布的子控件
	for (int32 ChildIndex = 0; ChildIndex < ArrangedChildren.Num(); ++ChildIndex)
	{
		const FArrangedWidget& ArrangedChild = ArrangedChildren[ChildIndex];

		// 完全透明的控件在界面上不可见, 跳过
		if (ArrangedChild.Widget->GetRenderOpacity() == 0.0f)
		{
			continue;
		}

		// 过滤条件 3: 检查排布后的尺寸
		// 绝对尺寸与期望尺寸分开判定, 两者都无效才跳过
		const FVector2D ChildAbsoluteSize = ArrangedChild.Geometry.GetAbsoluteSize();
		const FVector2D ChildDesiredSize = ArrangedChild.Widget->GetDesiredSize();
		const bool bAbsoluteSizeInvalid =
			FMath::IsNearlyZero(ChildAbsoluteSize.X) || FMath::IsNearlyZero(ChildAbsoluteSize.Y);
		const bool bDesiredSizeInvalid =
			FMath::IsNearlyZero(ChildDesiredSize.X) || FMath::IsNearlyZero(ChildDesiredSize.Y);
		if (bAbsoluteSizeInvalid && bDesiredSizeInvalid)
		{
			continue;  // 跳过没有可见面积的控件
		}

		// 递归为该子控件构建子节点, 并挂接到当前节点下
		NewNodeInstance->AddChildNode(GetNodeFromTree(ArrangedChild, Index));
	}

	// 返回构建好的 (含所有合格子节点的) 当前节点
	return NewNodeInstance;
}

// 重新开启代码优化, 恢复后续编译单元的默认优化行为
#if ENGINE_MAJOR_VERSION >= 5
UE_ENABLE_OPTIMIZATION
#else
PRAGMA_ENABLE_OPTIMIZATION
#endif
