#include "WidgetSlots/Widget2JsonFactory.h"

#include "Snapshot/LQAWidgetNode.h"            // 控件节点定义
#include "WidgetSlots/Widget2JsonInterface.h"  // 控件转 JSON 的通用接口
#include "WidgetSlots/WidgetDefines.h"         // 控件类型枚举、日志分类等公共定义

// ========== 控件转换器头文件: 各具体控件类型对应的 JSON 转换实现 ==========
// 基础控件
#include "WidgetSlots/Widget/LQA_BackgroundBlur2Json.h"
#include "WidgetSlots/Widget/LQA_Border2Json.h"
#include "WidgetSlots/Widget/LQA_Button2Json.h"
#include "WidgetSlots/Widget/LQA_CanvasPanel2Json.h"
#include "WidgetSlots/Widget/LQA_CheckBox2Json.h"
#include "WidgetSlots/Widget/LQA_CircularThrobber2Json.h"
#include "WidgetSlots/Widget/LQA_ComboBox2Json.h"
#include "WidgetSlots/Widget/LQA_DynamicEntryBox2Json.h"
#include "WidgetSlots/Widget/LQA_EditableTextBlock2Json.h"
#include "WidgetSlots/Widget/LQA_EditableTextBox2Json.h"
#include "WidgetSlots/Widget/LQA_GridPanel2Json.h"
#include "WidgetSlots/Widget/LQA_HorizontalBox2Json.h"
#include "WidgetSlots/Widget/LQA_Image2Json.h"
#include "WidgetSlots/Widget/LQA_InvalidationBox2Json.h"
#include "WidgetSlots/Widget/LQA_InputKeySelector2Json.h"
#include "WidgetSlots/Widget/LQA_MenuAnchor2Json.h"
#include "WidgetSlots/Widget/LQA_MultilineEditableTextBlock2Json.h"
#include "WidgetSlots/Widget/LQA_MultilineEditableTextBox2Json.h"
#include "WidgetSlots/Widget/LQA_NamedSlot2Json.h"
#include "WidgetSlots/Widget/LQA_NativeWidgetHost2Json.h"
#include "WidgetSlots/Widget/LQA_TextScroller2Json.h"
#include "WidgetSlots/Widget/LQA_Overlay2Json.h"
#include "WidgetSlots/Widget/LQA_PostBufferUpdate2Json.h"
#include "WidgetSlots/Widget/LQA_ProgressBar2Json.h"
#include "WidgetSlots/Widget/LQA_RetainerBox2Json.h"
#include "WidgetSlots/Widget/LQA_RichTextBlock2Json.h"
#include "WidgetSlots/Widget/LQA_SafeZone2Json.h"
#include "WidgetSlots/Widget/LQA_ScaleBox2Json.h"
#include "WidgetSlots/Widget/LQA_ScrollBar2Json.h"
#include "WidgetSlots/Widget/LQA_ScrollBox2Json.h"
#include "WidgetSlots/Widget/LQA_SizeBox2Json.h"
#include "WidgetSlots/Widget/LQA_Slider2Json.h"
#include "WidgetSlots/Widget/LQA_Spacer2Json.h"
#include "WidgetSlots/Widget/LQA_SpinBox2Json.h"
#include "WidgetSlots/Widget/LQA_StackBox2Json.h"
#include "WidgetSlots/Widget/LQA_TextBlock2Json.h"
#include "WidgetSlots/Widget/LQA_Throbber2Json.h"
#include "WidgetSlots/Widget/LQA_UniformGridPanel2Json.h"
#include "WidgetSlots/Widget/LQA_UserWidget2Json.h"
#include "WidgetSlots/Widget/LQA_VerticalBox2Json.h"
#include "WidgetSlots/Widget/LQA_WidgetSwitcher2Json.h"
#include "WidgetSlots/Widget/LQA_WindowTitleBarArea2Json.h"
#include "WidgetSlots/Widget/LQA_WrapBox2Json.h"
#include "WidgetSlots/Widget/LQA_ExpandableArea2Json.h"
#include "WidgetSlots/Widget/LQA_ListView2Json.h"
#include "WidgetSlots/Widget/LQA_TileView2Json.h"
#include "WidgetSlots/Widget/LQA_TreeView2Json.h"

/**
 * 根据控件节点的类型, 创建并返回对应的「控件 -> JSON」转换器
 * 采用工厂模式 + switch 分发: 每种控件类型映射到一个具体的转换器实现
 */
TSharedPtr<FWidget2JsonInterface> FWidget2JsonFactory::MakeWidgetData(const TSharedPtr<FLQAWidgetNode> InWidgetNode)
{
	// 入参有效性校验: 空指针直接告警并返回
	if (!InWidgetNode.IsValid())
	{
		UE_LOG(LogLQAToolWidget, Warning, TEXT("MakeWidgetData: Invalid WidgetNode pointer."));
		return nullptr;
	}

	// 取出控件的 LQA 类型枚举
	const ELQAWidgetType WidgetType = InWidgetNode->GetNodeType();

	// 根据控件类型创建相应的转换器
	switch (WidgetType)
	{
		// ========== 基础文本类控件 ==========
		case ELQAWidgetType::LQA_TextBlock:
			return MakeShareable(new FLQA_TextBlock2Json());
		case ELQAWidgetType::LQA_RichText:
			return MakeShareable(new FLQA_RichTextBlock2Json());
		case ELQAWidgetType::LQA_EditableText:
			return MakeShareable(new FLQA_EditableTextBlock2Json());
		case ELQAWidgetType::LQA_EditableTextBox:
			return MakeShareable(new FLQA_EditableTextBox2Json());
		case ELQAWidgetType::LQA_MultilineEditableText:
			return MakeShareable(new FLQA_MultilineEditableTextBlock2Json());
		case ELQAWidgetType::LQA_MultilineEditableTextBox:
			return MakeShareable(new FLQA_MultilineEditableTextBox());
		case ELQAWidgetType::LQA_TextScroller:
			return MakeShareable(new FLQA_TextScroller2Json());

		// ========== 输入类控件 ==========
		case ELQAWidgetType::LQA_ComboBoxStringText:
			return MakeShareable(new FLQA_ComboBox2Json());
		case ELQAWidgetType::LQA_InputKeySelector:
			return MakeShareable(new FLQA_InputKeySelector2Json());
		case ELQAWidgetType::LQA_CheckBox:
			return MakeShareable(new FLQA_CheckBox2Json());
		case ELQAWidgetType::LQA_Button:
			return MakeShareable(new FLQA_Button2Json());
		case ELQAWidgetType::LQA_ProgressBar:
			return MakeShareable(new FLQA_ProgressBar2Json());
		case ELQAWidgetType::LQA_Slider:
			return MakeShareable(new FLQA_Slider2Json());
		case ELQAWidgetType::LQA_SpinBox:
			return MakeShareable(new FLQA_SpinBox2Json());

		// ========== 展示类控件 ==========
		case ELQAWidgetType::LQA_Image:
			return MakeShareable(new FLQA_Image2Json());
		case ELQAWidgetType::LQA_Throbber:
			return MakeShareable(new FLQA_Throbber2Json());
		case ELQAWidgetType::LQA_CircularThrobber:
			return MakeShareable(new FLQA_CircularThrobber2Json());
		case ELQAWidgetType::LQA_Spacer:
			return MakeShareable(new FLQA_Spacer2Json());
		case ELQAWidgetType::LQA_BackgroundBlur:
			return MakeShareable(new FLQA_BackgroundBlur2Json());
		case ELQAWidgetType::LQA_Border:
			return MakeShareable(new FLQA_Border2Json());

		// ========== 容器类控件 ==========
		case ELQAWidgetType::LQA_UserWidget:
			return MakeShareable(new FLQA_UserWidget2Json());
		case ELQAWidgetType::LQA_Canvas:
			return MakeShareable(new FLQA_CanvasPanel2Json());
		case ELQAWidgetType::LQA_RetainerBox:
			return MakeShareable(new FLQA_RetainerBox2Json());
		case ELQAWidgetType::LQA_Overlay:
			return MakeShareable(new FLQA_Overlay2Json());
		case ELQAWidgetType::LQA_WidgetSwitcher:
			return MakeShareable(new FLQA_WidgetSwitcher2Json());
		case ELQAWidgetType::LQA_StackBox:
			return MakeShareable(new FLQA_StackBox2Json());
		case ELQAWidgetType::LQA_WindowTitleBarArea:
			return MakeShareable(new FLQA_WindowTitleBarArea2Json());
		case ELQAWidgetType::LQA_MenuAnchor:
			return MakeShareable(new FLQA_MenuAnchor2Json());
		case ELQAWidgetType::LQA_InvalidationBox:
			return MakeShareable(new FLQA_InvalidationBox2Json());
		case ELQAWidgetType::LQA_ScrollBar:
			return MakeShareable(new FLQA_ScrollBar2Json());
		case ELQAWidgetType::LQA_PostBufferUpdate:
			return MakeShareable(new FLQA_PostBufferUpdate2Json());
		case ELQAWidgetType::LQA_DynamicEntryBox:
			return MakeShareable(new FLQA_DynamicEntryBox2Json());
		case ELQAWidgetType::LQA_ListView:
			return MakeShareable(new FLQA_ListView2Json());
		case ELQAWidgetType::LQA_TileView:
			return MakeShareable(new FLQA_TileView2Json());
		case ELQAWidgetType::LQA_TreeView:
			return MakeShareable(new FLQA_TreeView2Json());
		case ELQAWidgetType::LQA_ExpandableArea:
			return MakeShareable(new FLQA_ExpandableArea2Json());

		// ========== 布局类控件 ==========
		case ELQAWidgetType::LQA_VerticalBox:
			return MakeShareable(new FLQA_VerticalBox2Json());
		case ELQAWidgetType::LQA_HorizontalBox:
			return MakeShareable(new FLQA_HorizontalBox2Json());
		case ELQAWidgetType::LQA_GridPanel:
			return MakeShareable(new FLQA_GridPanel2Json());
		case ELQAWidgetType::LQA_UniformGridPanel:
			return MakeShareable(new FLQA_UniformGridPanel2Json());
		case ELQAWidgetType::LQA_WrapBox:
			return MakeShareable(new FLQA_WrapBox2Json());

		// ========== 滚动类控件 ==========
		case ELQAWidgetType::LQA_ScrollBox:
			return MakeShareable(new FLQA_ScrollBox2Json());

		// ========== 尺寸约束类控件 ==========
		case ELQAWidgetType::LQA_ScaleBox:
			return MakeShareable(new FLQA_ScaleBox2Json());
		case ELQAWidgetType::LQA_SafeZone:
			return MakeShareable(new FLQA_SafeZone2Json());
		// Slate 根类型复用: Slate 根均为 SBox, 具体类型由注册表按 UMG 类区分
		case ELQAWidgetType::LQA_SizeBox:
			return MakeShareable(new FLQA_SizeBox2Json());
		case ELQAWidgetType::LQA_NamedSlot:
			return MakeShareable(new FLQA_NamedSlot2Json());
		case ELQAWidgetType::LQA_NativeWidgetHost:
			return MakeShareable(new FLQA_NativeWidgetHost2Json());

		// ========== 未支持的控件类型 ==========
		default:
			// 记录告警并输出具体的类型枚举值, 便于后续排查/扩展
			UE_LOG(LogLQAToolWidget, Warning, TEXT("MakeWidgetData: Unsupported widget type: %d"),
				static_cast<int32>(WidgetType));
			break;
	}

	return nullptr;
}

/**
 * 将「未定义(不支持的)」控件转换为 JSON
 * 仅写入 WidgetType="UNDEFINE" 标记, 并填充未定义控件所需的通用数据
 */
TSharedPtr<FJsonObject> FWidget2JsonFactory::UndefineWidget2Json(const TSharedPtr<FLQAWidgetNode>& InWidget)
{
	// 新建一个空的 JSON 对象
	TSharedPtr<FJsonObject> NewObject = MakeShareable(new FJsonObject());
	// 标记该控件类型为未定义
	NewObject->SetStringField(TEXT("WidgetType"), TEXT("UNDEFINE"));

	// 节点有效时, 填充未定义控件的通用数据
	if (InWidget.IsValid())
	{
		InWidget->FillCommonDataForUndefinedWidget(NewObject);
	}

	return NewObject;
}

/**
 * 将控件转换为 JSON 的核心入口
 * 流程: 填充通用数据 -> 按类型做差异化序列化 -> 写入 Slate 根类型复用标识
 */
TSharedPtr<FJsonObject> FWidget2JsonFactory::Widget2Json(
	const TSharedPtr<FLQAWidgetNode>& InWidget, TMap<FString, UTexture*>& SharedTextureMap, const bool bNeedObjectData)
{
	// 新建承载结果的 JSON 对象
	TSharedPtr<FJsonObject> NewObject = MakeShareable(new FJsonObject());

	// 先填充控件的通用数据 (名称、坐标、尺寸、图层、插槽类型等)
	if (InWidget.IsValid())
	{
		InWidget->FillCommonData(NewObject, bNeedObjectData);
	}

	// 按控件类型选取对应转换器并执行类型差异化序列化
	const TSharedPtr<FWidget2JsonInterface> Interface = MakeWidgetData(InWidget);
	if (Interface.IsValid())
	{
		// 调用具体转换器的 ToJson, 将该类型特有的字段写入 NewObject
		Interface->ToJson(InWidget, NewObject, SharedTextureMap);
	}
	else
	{
		// 未能创建转换器 (类型不支持或节点无效), 记录告警
		UE_LOG(LogLQAToolWidget, Warning, TEXT("Widget2Json: Failed to create interface for widget conversion"));
	}

	// Slate 根类型复用: 由注册表判定的 UMG 侧标识统一写入 WidgetClass 字段 (1:1 类型不写)
	if (InWidget.IsValid() && InWidget->WidgetClassTag != NAME_None)
	{
		NewObject->SetStringField(TEXT("WidgetClass"), InWidget->WidgetClassTag.ToString());
	}

	return NewObject;
}

/**
 * 从控件 JSON 数据中解析控件的位置
 * 优先使用 corners (四角点) 数组的左上角点; 若无则回退到 ViewportPos 字段
 */
FVector2D FWidget2JsonFactory::GetWidgetPos(const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize)
{
	// 优先尝试从 corners 四角点数组中获取位置
	if (InWidgetData->HasField(TEXT("corners")))
	{
		const TArray<TSharedPtr<FJsonValue>> SizePoint = InWidgetData->GetArrayField(TEXT("corners"));
		// 四角点结构应恰好包含 4 个点, 索引 [1] 约定为左上角点
		if (SizePoint.Num() == 4)
		{
			return DeserializePoint(SizePoint[1]->AsObject(), InWindowSize);
		}
	}

	// 回退方案: 使用 ViewportPos 字段 (视口坐标)
	if (InWidgetData->HasField(TEXT("ViewportPos")))
	{
		const TSharedPtr<FJsonObject> ViewportPosObj = InWidgetData->GetObjectField(TEXT("ViewportPos"));
		FVector2D Point = FVector2D::ZeroVector;

		// 分别读取 x、y 分量 (字段可能缺失, 故逐个判断)
		if (ViewportPosObj->HasField(TEXT("x")))
		{
			Point.X = ViewportPosObj->GetNumberField(TEXT("x"));
		}

		if (ViewportPosObj->HasField(TEXT("y")))
		{
			Point.Y = ViewportPosObj->GetNumberField(TEXT("y"));
		}

		return Point;
	}

	// 两种来源都没有时, 返回零向量
	return FVector2D::ZeroVector;
}

/**
 * 从控件 JSON 数据中解析控件的尺寸
 * @param bUseAbsoluteSize 为 true 时由四角点计算绝对尺寸; 为 false 时使用 LocalSize 本地尺寸
 */
FVector2D FWidget2JsonFactory::GetWidgetSize(
	const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize, bool bUseAbsoluteSize)
{
	if (bUseAbsoluteSize)
	{
		// 由 corners 四角点计算尺寸: 右下角 - 左上角
		if (InWidgetData->HasField(TEXT("corners")))
		{
			const TArray<TSharedPtr<FJsonValue>> SizePoint = InWidgetData->GetArrayField(TEXT("corners"));
			if (SizePoint.Num() == 4)
			{
				// 索引 [1] 为左上角, [3] 为右下角
				const FVector2D LeftUpper = DeserializePoint(SizePoint[1]->AsObject(), InWindowSize);
				const FVector2D RightBottom = DeserializePoint(SizePoint[3]->AsObject(), InWindowSize);
				return RightBottom - LeftUpper;
			}
		}

		return FVector2D::ZeroVector;
	}

	// 非绝对尺寸: 若存在 LocalSize 则使用本地尺寸
	if (InWidgetData->HasField(TEXT("LocalSize")))
	{
		const TSharedPtr<FJsonObject> LocalSizeObj = InWidgetData->GetObjectField(TEXT("LocalSize"));
		FVector2D Point = FVector2D::ZeroVector;

		// 逐个读取宽(x)、高(y)
		if (LocalSizeObj->HasField(TEXT("x")))
		{
			Point.X = LocalSizeObj->GetNumberField(TEXT("x"));
		}

		if (LocalSizeObj->HasField(TEXT("y")))
		{
			Point.Y = LocalSizeObj->GetNumberField(TEXT("y"));
		}

		return Point;
	}

	return FVector2D::ZeroVector;
}

/**
 * 从 JSON 数据反序列化出一个二维坐标点, 并进行坐标系换算
 * 注意: 原始坐标系与目标坐标系的 Y 轴方向相反, 这里会以窗口高度为基准翻转 Y
 */
FVector2D FWidget2JsonFactory::DeserializePoint(const TSharedPtr<FJsonObject> InPosData, const FVector2D& InWindowSize)
{
	FVector2D Point = FVector2D::ZeroVector;

	// 读取 x 分量
	if (InPosData->HasField(TEXT("x")))
	{
		Point.X = InPosData->GetNumberField(TEXT("x"));
	}

	// 读取 y 分量
	if (InPosData->HasField(TEXT("y")))
	{
		Point.Y = InPosData->GetNumberField(TEXT("y"));
	}

	// 坐标系换算 (翻转 Y 轴): 以窗口高度减去原始 Y 值
	// 仅当点非零时执行, 避免对零向量做无意义的翻转
	if (!Point.IsZero())
	{
		Point.Y = InWindowSize.Y - Point.Y;
	}

	return Point;
}