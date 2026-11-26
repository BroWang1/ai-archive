#include "Snapshot/LQAWidgetNode.h"

#include "Blueprint/SlateBlueprintLibrary.h"
#include "Components/PanelSlot.h"
#include "Components/Widget.h"
#include "Internationalization/TextNamespaceUtil.h"
#include "JsonObjectConverter.h"
#include "LQABase.h"
#include "Types/ReflectionMetadata.h"
#include "Utils/LQAJsonUtils.h"
#include "Widgets/SWidget.h"
#include "WidgetSlots/LQAWidgetTypeRegistry.h"
#include "WidgetSlots/WidgetDefines.h"

// 关闭本文件的编译器优化 (便于调试; 文件末尾会重新开启)
#if ENGINE_MAJOR_VERSION >= 5
UE_DISABLE_OPTIMIZATION
#else
PRAGMA_DISABLE_OPTIMIZATION
#endif

// ================== 控件 / 插槽类型名称常量 ==================

// 插槽类型名 (与 Slate/UMG 的插槽类名字符串一一对应)
namespace LQASlotNames
{
// Slot type names
const FName LQA_ButtonSlot(TEXT("ButtonSlot"));
const FName LQA_CanvasPanelSlot(TEXT("CanvasPanelSlot"));
const FName LQA_ScrollBoxSlot(TEXT("ScrollBoxSlot"));
const FName LQA_VerticalBoxSlot(TEXT("VerticalBoxSlot"));
const FName LQA_HorizontalBoxSlot(TEXT("HorizontalBoxSlot"));
const FName LQA_ScaleBoxSlot(TEXT("ScaleBoxSlot"));
const FName LQA_SafeZoneSlot(TEXT("SafeZoneSlot"));
const FName LQA_WrapBoxSlot(TEXT("WrapBoxSlot"));
const FName LQA_SizeBoxSlot(TEXT("SizeBoxSlot"));
const FName LQA_GridSlot(TEXT("GridSlot"));
const FName LQA_UniformGridSlot(TEXT("UniformGridSlot"));
const FName LQA_OverlaySlot(TEXT("OverlaySlot"));
const FName LQA_BorderSlot(TEXT("BorderSlot"));
const FName LQA_WidgetSwitcherSlot(TEXT("WidgetSwitcherSlot"));
const FName LQA_BackgroundBlurSlot(TEXT("BackgroundBlurSlot"));
const FName LQA_StackBoxSlot(TEXT("StackBoxSlot"));
const FName LQA_WindowTitleBarAreaSlot(TEXT("WindowTitleBarAreaSlot"));
const FName LQA_PanelSlot(TEXT("PanelSlot"));

// 项目自定义插槽名称可在此处追加
}

namespace LQAWidgetNames
{
// 控件类型名 (与 Slate 控件的 GetType() 返回字符串一一对应)
const FName LQA_TextBlock(TEXT("STextBlock"));
const FName LQA_RichTextBlock(TEXT("SRichTextBlock"));
const FName LQA_EditableText(TEXT("SEditableText"));
const FName LQA_EditableTextBox(TEXT("SEditableTextBox"));
const FName LQA_MultilineEditableText(TEXT("SMultilineEditableText"));
const FName LQA_MultilineEditableTextBox(TEXT("SMultilineEditableTextBox"));
const FName LQA_TextScroller(TEXT("STextScroller"));
const FName LQA_InputKeySelector(TEXT("SInputKeySelector"));
const FName LQA_ComboBox(TEXT("SComboBox"));
const FName LQA_ComboBoxString(TEXT("SComboBox< TSharedPtr<FString> >"));
const FName LQA_ComboBoxKey(TEXT("SComboBox<FName>"));
const FName LQA_LEDRichTextBlock(TEXT("SLEDRichTextBlock"));
const FName LQA_Image(TEXT("SImage"));
const FName LQA_Button(TEXT("SButton"));
const FName LQA_UserWidget(TEXT("SObjectWidget"));
const FName LQA_Canvas(TEXT("SConstraintCanvas"));
const FName LQA_RetainerBox(TEXT("SRetainerWidget"));
const FName LQA_ScrollBox(TEXT("SScrollBox"));
const FName LQA_CommonHierarchicalScrollBox(TEXT("SCommonHierarchicalScrollBox"));
const FName LQA_VerticalBox(TEXT("SVerticalBox"));
const FName LQA_HorizontalBox(TEXT("SHorizontalBox"));
const FName LQA_ScaleBox(TEXT("SScaleBox"));
const FName LQA_SafeZone(TEXT("SSafeZone"));
const FName LQA_WrapBox(TEXT("SWrapBox"));
const FName LQA_SizeBox(TEXT("SBox"));
const FName LQA_NamedSlot(TEXT("SBox"));
const FName LQA_NativeWidgetHost(TEXT("SBox"));
const FName LQA_CheckBox(TEXT("SCheckBox"));
const FName LQA_GridPanel(TEXT("SGridPanel"));
const FName LQA_UniformGridPanel(TEXT("SUniformGridPanel"));
const FName LQA_Overlay(TEXT("SOverlay"));
const FName LQA_Border(TEXT("SBorder"));
const FName LQA_BackgroundBlur(TEXT("SBackgroundBlur"));
const FName LQA_ProgressBar(TEXT("SProgressBar"));
const FName LQA_Throbber(TEXT("SThrobber"));
const FName LQA_CircularThrobber(TEXT("SCircularThrobber"));
const FName LQA_Slider(TEXT("SSlider"));
const FName LQA_SpinBox(TEXT("SSpinBox"));
const FName LQA_SpinBoxFloat(TEXT("SSpinBox<float>"));
const FName LQA_Spacer(TEXT("SSpacer"));
const FName LQA_WidgetSwitcher(TEXT("SWidgetSwitcher"));
const FName LQA_StackBox(TEXT("SStackBox"));
const FName LQA_WindowTitleBarArea(TEXT("SWindowTitleBarArea"));
const FName LQA_MenuAnchor(TEXT("SMenuAnchor"));
const FName LQA_InvalidationBox(TEXT("SInvalidationPanel"));
const FName LQA_ScrollBar(TEXT("SScrollBar"));
const FName LQA_PostBufferUpdate(TEXT("SPostBufferUpdate"));
const FName LQA_ObjectTableRow(TEXT("ObjectTableRowT"));
const FName LQA_ListView(TEXT("ListViewT<ItemType>"));
const FName LQA_TileView(TEXT("TileViewT<ItemType>"));
const FName LQA_TreeView(TEXT("TreeViewT<ItemType>"));
const FName LQA_ExpandableArea(TEXT("SExpandableArea"));

// 项目自定义控件名称可在此处追加
}

namespace
{
/**
 * 将非有限数值归一为 0
 * 用于防止 NaN / Inf 写入 JSON 导致解析异常
 * @param InValue 待归一化的数值
 * @return 有限值原样返回; NaN / Inf 返回 0
 */
double SanitizeFinite(const double InValue)
{
	return FMath::IsFinite(InValue) ? InValue : 0.0;
}
}  // namespace

// 构造函数: 缓存几何信息, 并处理控件以识别类型、提取元数据
FLQAWidgetNode::FLQAWidgetNode(const FArrangedWidget& InWidgetGeometry) : CachedGeometry(InWidgetGeometry.Geometry)
{
	HandleWidget(InWidgetGeometry.Widget);
}

// 追加一个子节点到子节点数组
void FLQAWidgetNode::AddChildNode(TSharedRef<FLQAWidgetNode> InChildNode)
{
	ChildNodes.Emplace(InChildNode);
}

// 清空所有子节点
void FLQAWidgetNode::ClearChildNodes()
{
	ChildNodes.Empty();
}

// 返回子节点数组 (常量引用)
const TArray<TSharedRef<FLQAWidgetNode>>& FLQAWidgetNode::GetChildNodes() const
{
	return ChildNodes;
}

// 填充控件的通用 JSON 数据 (名称、角点、视口坐标、尺寸、包围盒、图层、插槽类型等)
void FLQAWidgetNode::FillCommonData(TSharedPtr<FJsonObject> InObject, bool bNeedObjectData) const
{
	// JSON 对象无效则记录警告并提前返回
	if (!InObject.IsValid())
	{
		UE_LOG(LogLQATool, Warning, TEXT("[LQA] Invalid JSON object passed to FillCommonData"));
		return;
	}

	// 写入基础字段
	InObject->SetStringField(TEXT("WidgetName"), WidgetName.ToString());
	InObject->SetArrayField(TEXT("corners"), GetCornerPosition());
	InObject->SetObjectField(TEXT("ViewportPos"), ConvertViewportPos2Json());
	InObject->SetObjectField(TEXT("LocalSize"), ConvertLocalSize2Json());
	InObject->SetArrayField(TEXT("BoxSize"), GetBoxSizePosition());
	InObject->SetNumberField(TEXT("LayerId"), LayerId);
	InObject->SetStringField(TEXT("ExcludedSlotType"), BaseSlotType);

	// 需要附加对象元数据, 且源对象有效时, 序列化源对象到 JSON
	if (bNeedObjectData && SourceObject.IsValid())
	{
		bool bGetStructJsonData = false;
		TSharedPtr<FJsonObject> JsonObject = MakeShared<FJsonObject>();

		// 仅对已识别类型的控件进行序列化
		if (NodeType != ELQAWidgetType::LQA_Undefined)
		{
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, SourceObject.Get()))
			{
				bGetStructJsonData = true;
			}
		}

		// 序列化成功且确有数据, 才写入 ObjectData 字段
		if (bGetStructJsonData && JsonObject->Values.Num() > 0)
		{
			InObject->SetField(TEXT("ObjectData"), MakeShared<FJsonValueObject>(JsonObject));
		}
	}
}

// 为 "未定义类型" 控件填充通用 JSON 数据 (额外写入排除的控件/插槽类型, 并识别蓝图 UserWidget)
void FLQAWidgetNode::FillCommonDataForUndefinedWidget(TSharedPtr<FJsonObject> InObject) const
{
	// JSON 对象无效则记录警告并提前返回
	if (!InObject.IsValid())
	{
		UE_LOG(LogLQATool, Warning, TEXT("[LQA] Invalid JSON object passed to FillCommonDataForUndefinedWidget"));
		return;
	}

	// 写入基础字段
	InObject->SetStringField(TEXT("WidgetName"), WidgetName.ToString());
	InObject->SetArrayField(TEXT("corners"), GetCornerPosition());
	InObject->SetObjectField(TEXT("ViewportPos"), ConvertViewportPos2Json());
	InObject->SetObjectField(TEXT("LocalSize"), ConvertLocalSize2Json());
	InObject->SetArrayField(TEXT("BoxSize"), GetBoxSizePosition());
	InObject->SetNumberField(TEXT("LayerId"), LayerId);
	// 未定义控件额外记录被排除的插槽类型与控件类型
	InObject->SetStringField(TEXT("ExcludedSlotType"), BaseSlotType);
	InObject->SetStringField(TEXT("ExcludedWidgetType"), BaseWidgetType);

	const FString WidgetNameString = WidgetName.ToString();
	if (SourceObject.IsValid())
	{
		bool bGetStructJsonData = false;
		TSharedPtr<FJsonObject> JsonObject = MakeShared<FJsonObject>();

		// 控件名不为 "None" 时才尝试序列化源对象
		if (WidgetNameString != TEXT("None"))
		{
			if (FLQAJsonUtils::SerializeObjectToJson(JsonObject, SourceObject.Get()))
			{
				bGetStructJsonData = true;
			}
		}

		// 序列化成功且确有数据, 才写入 ObjectData 字段
		if (bGetStructJsonData && JsonObject->Values.Num() > 0)
		{
			InObject->SetField(TEXT("ObjectData"), MakeShared<FJsonValueObject>(JsonObject));
		}
	}

	// 控件名包含 "_C_" 说明是蓝图生成类实例, 标记为 UserWidget 类型
	if (WidgetNameString.Contains(TEXT("_C_")))
	{
		InObject->SetStringField(TEXT("NewWidgetType"), LQAWidgetNames::LQA_UserWidget.ToString());
	}
}

// 核心处理: 识别控件类型、读取反射元数据、确定插槽类型并计算 UI 位置
void FLQAWidgetNode::HandleWidget(const TSharedRef<SWidget>& InWidget)
{
	const FName SlateTypeName = InWidget->GetType();
	BaseWidgetType = SlateTypeName.ToString();

	const TSharedPtr<FReflectionMetaData> InWidgetMetaData = InWidget->GetMetaData<FReflectionMetaData>();
	if (!InWidgetMetaData.IsValid())
	{
		NodeType = ELQAWidgetType::LQA_Undefined;
		return;
	}

	if (InWidgetMetaData->Name != NAME_None)
	{
		WidgetName = InWidgetMetaData->Name;
	}
	SourceObject = InWidgetMetaData->SourceObject;

	// 类型判定: Slate 类型名 + UMG 类 (Slate 根类型复用时靠 UMG 类区分)
	if (const FLQAWidgetTypeDesc* TypeDesc = FLQAWidgetTypeRegistry::TryGetWidgetTypeDesc(SlateTypeName, SourceObject.Get()))
	{
		NodeType = TypeDesc->WidgetType;            // 命中登记项: 取 LQA 控件类型
		WidgetClassTag = TypeDesc->WidgetClassTag;  // Slate 根类型复用组内的 UMG 侧标识 (1:1 类型为 None)
	}
	else
	{
		NodeType = ELQAWidgetType::LQA_Undefined;   // 未登记: 视为 Slate 内部控件
	}

	if (SourceObject.IsValid())
	{
		if (UWidget* SourceUWidget = Cast<UWidget>(SourceObject))
		{
			if (UPanelSlot* DefaultSlot = SourceUWidget->Slot)
			{
				const FString SlotClassNameStr = DefaultSlot->GetClass()->GetName();
				const FName SlotClassName(*SlotClassNameStr);
				BaseSlotType = SlotClassNameStr;
				SlotType = GetSlotType(SlotClassName);
			}
		}
	}

	if (NodeType == ELQAWidgetType::LQA_Undefined)
	{
		return;
	}

	LayerId = 0;
	if (!SetUIPosition())
	{
		NodeType = ELQAWidgetType::LQA_Undefined;
	}
}

ELQASlotType FLQAWidgetNode::GetSlotType(const FName& SlotTypeName)
{
	using namespace LQASlotNames;

	// 插槽类型名 -> 枚举 的静态映射表 (首次调用时构建并缓存)
	static const TMap<FName, ELQASlotType> SlotTypeMap = {
		{LQA_ButtonSlot, ELQASlotType::LQA_ButtonSlot}, {LQA_CanvasPanelSlot, ELQASlotType::LQA_CanvasPanelSlot},
		{LQA_ScrollBoxSlot, ELQASlotType::LQA_ScrollBoxSlot}, {LQA_VerticalBoxSlot, ELQASlotType::LQA_VerticalBoxSlot},
		{LQA_HorizontalBoxSlot, ELQASlotType::LQA_HorizontalBoxSlot},
		{LQA_ScaleBoxSlot, ELQASlotType::LQA_ScaleBoxSlot}, {LQA_SafeZoneSlot, ELQASlotType::LQA_SafeZoneSlot},
		{LQA_WrapBoxSlot, ELQASlotType::LQA_WrapBoxSlot}, {LQA_SizeBoxSlot, ELQASlotType::LQA_SizeBoxSlot},
		{LQA_GridSlot, ELQASlotType::LQA_GridSlot}, {LQA_UniformGridSlot, ELQASlotType::LQA_UniformGridSlot},
		{LQA_OverlaySlot, ELQASlotType::LQA_OverlaySlot}, {LQA_BorderSlot, ELQASlotType::LQA_BorderSlot},
		{LQA_WidgetSwitcherSlot, ELQASlotType::LQA_WidgetSwitcherSlot},
		{LQA_BackgroundBlurSlot, ELQASlotType::LQA_BackgroundBlurSlot},
		{LQA_StackBoxSlot, ELQASlotType::LQA_StackBoxSlot},
		{LQA_WindowTitleBarAreaSlot, ELQASlotType::LQA_WindowTitleBarAreaSlot},
		{LQA_PanelSlot, ELQASlotType::LQA_PanelSlot}

		// 项目自定义插槽映射可在此处追加
	};

	// 命中返回对应枚举, 否则返回未定义
	if (const ELQASlotType* FoundType = SlotTypeMap.Find(SlotTypeName))
	{
		return *FoundType;
	}
	return ELQASlotType::LQA_UndefinedSlot;
}

// 将四个角点坐标 (左下、左上、右上、右下) 打包为 JSON 数组
TArray<TSharedPtr<FJsonValue>> FLQAWidgetNode::GetCornerPosition() const
{
	TArray<TSharedPtr<FJsonValue>> CornerPosList;
	CornerPosList.Reserve(4);  // 预留 4 个元素, 避免扩容
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(LeftBottomPos)));
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(LeftUpperPos)));
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(RightUpperPos)));
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(RightBottomPos)));
	return CornerPosList;
}

// 将包围盒的最小点与最大点打包为 JSON 数组
TArray<TSharedPtr<FJsonValue>> FLQAWidgetNode::GetBoxSizePosition() const
{
	TArray<TSharedPtr<FJsonValue>> BoxPosList;
	BoxPosList.Reserve(2);  // 预留 2 个元素(Min / Max)
	BoxPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(BoxSize.Min)));
	BoxPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(BoxSize.Max)));
	return BoxPosList;
}

// 将视口坐标转换为 {x, y} 形式的 JSON 对象 (数值做有限化保护)
TSharedPtr<FJsonObject> FLQAWidgetNode::ConvertViewportPos2Json() const
{
	TSharedPtr<FJsonObject> PosValue = MakeShared<FJsonObject>();
	PosValue->SetNumberField(TEXT("x"), SanitizeFinite(ViewportPos.X));
	PosValue->SetNumberField(TEXT("y"), SanitizeFinite(ViewportPos.Y));
	return PosValue;
}

// 将本地尺寸转换为 {x, y} 形式的 JSON 对象 (数值做有限化保护)
TSharedPtr<FJsonObject> FLQAWidgetNode::ConvertLocalSize2Json() const
{
	TSharedPtr<FJsonObject> PosValue = MakeShared<FJsonObject>();
	PosValue->SetNumberField(TEXT("x"), SanitizeFinite(LocalSize.X));
	PosValue->SetNumberField(TEXT("y"), SanitizeFinite(LocalSize.Y));
	return PosValue;
}

// 将任意二维坐标转换为 {x, y} 形式的 JSON 对象 (数值做有限化保护)
TSharedPtr<FJsonObject> FLQAWidgetNode::ConvertPos2Json(const FVector2D& InPos) const
{
	TSharedPtr<FJsonObject> PosValue = MakeShared<FJsonObject>();

	PosValue->SetNumberField(TEXT("x"), SanitizeFinite(InPos.X));
	PosValue->SetNumberField(TEXT("y"), SanitizeFinite(InPos.Y));
	return PosValue;
}

// 计算并设置控件在屏幕上的位置数据 (四角坐标、视口坐标、本地尺寸、包围盒)
bool FLQAWidgetNode::SetUIPosition()
{
	// 获取 World; 无效则无法进行坐标换算
	UWorld* WorldInstance = SourceObject.IsValid() ? SourceObject->GetWorld() : nullptr;
	if (!WorldInstance)
	{
		UE_LOG(LogLQATool, Error, TEXT("[LQA] Get Invalid World!"));
		return false;
	}

	// 获取视口尺寸 (用于后续 Y 轴翻转)
	FVector2D ViewportSize = FVector2D::ZeroVector;
	if (const UGameViewportClient* ViewportClient = WorldInstance->GetGameViewport())
	{
		ViewportClient->GetViewportSize(ViewportSize);
	}

	// 将控件本地原点换算为视口像素坐标, 并获取绝对尺寸与本地尺寸
	FVector2D PixelPos;
	USlateBlueprintLibrary::LocalToViewport(
		WorldInstance, CachedGeometry, FVector2D(0.0f, 0.0f), PixelPos, ViewportPos);
	const FVector2D AbsoluteSize = USlateBlueprintLibrary::GetAbsoluteSize(CachedGeometry);
	LocalSize = CachedGeometry.GetLocalSize();

	// 依次计算四个角点坐标;
	// 注意：Slate 的 Y 轴向下, 这里统一翻转为 "Y 轴向上" 的屏幕坐标系 (ViewportSize.Y - Y)

	// 左下角 = 原点 + (0,1)*尺寸
	LeftBottomPos = PixelPos + FVector2D(0.0f, 1.0f) * AbsoluteSize;
	LeftBottomPos.Y = ViewportSize.Y - LeftBottomPos.Y;

	// 左上角 = 原点 + (0,0)*尺寸
	LeftUpperPos = PixelPos + FVector2D(0.0f, 0.0f) * AbsoluteSize;
	LeftUpperPos.Y = ViewportSize.Y - LeftUpperPos.Y;

	// 右上角 = 原点 + (1,0)*尺寸
	RightUpperPos = PixelPos + FVector2D(1.0f, 0.0f) * AbsoluteSize;
	RightUpperPos.Y = ViewportSize.Y - RightUpperPos.Y;

	// 右下角 = 原点 + (1,1)*尺寸
	RightBottomPos = PixelPos + FVector2D(1.0f, 1.0f) * AbsoluteSize;
	RightBottomPos.Y = ViewportSize.Y - RightBottomPos.Y;

	// 以左下、右上两点构建 2D 包围盒
	BoxSize = FBox2D(LeftBottomPos, RightUpperPos);
	return true;
}

// 设置节点唯一标识
void FLQAWidgetNode::SetNodeId(int32 Id)
{
	NodeId = Id;
}

// 判断是否为用户自定义控件 (UserWidget)
bool FLQAWidgetNode::CheckNodeIsUserWidget() const
{
	return NodeType == ELQAWidgetType::LQA_UserWidget;
}

// 递归设置包围盒: 把当前节点的包围盒下传给 "非 UserWidget" 子节点
// (UserWidget 作为独立单元, 保留自身包围盒, 不被父级覆盖)
void FLQAWidgetNode::SetBoxSize()
{
	for (const auto& Item : ChildNodes)
	{
		if (!Item->CheckNodeIsUserWidget())
		{
			Item->BoxSize = BoxSize;  // 继承父节点包围盒
			Item->SetBoxSize();       // 继续向下递归
		}
	}
}

// 重新开启本文件的编译器优化
#if ENGINE_MAJOR_VERSION >= 5
UE_ENABLE_OPTIMIZATION
#else
PRAGMA_ENABLE_OPTIMIZATION
#endif