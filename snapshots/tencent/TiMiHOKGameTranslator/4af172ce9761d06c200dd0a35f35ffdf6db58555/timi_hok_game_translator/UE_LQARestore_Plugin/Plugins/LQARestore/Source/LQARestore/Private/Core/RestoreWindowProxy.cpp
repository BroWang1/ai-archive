#include "Core/RestoreWindowProxy.h"

#include "LQABase.h"
#include "Blueprint/SlateBlueprintLibrary.h"
#include "Components/Image.h"
#include "Components/NamedSlotInterface.h"
#include "Core/LQARestoreManager.h"
#include "Core/RestoreWindowUtils.h"
#include "Core/RootObjWidget.h"
#include "Engine/Engine.h"
#include "Framework/Application/SlateApplication.h"
#include "TimerManager.h"
#include "Types/ReflectionMetadata.h"
#include "Utils/GeometryUtils.h"
#include "Utils/TranslationUtils/LoaderUtils.h"
#include "WidgetSlots/Core/WidgetDefines.h"
#include "Widgets/SWidget.h"
#include "Widgets/SWindow.h"

// ============================================================================
// 匿名命名空间 —— 常量定义 (Anonymous Namespace - Constants)
// 这些常量仅在本编译单元内可见, 用于避免污染全局命名空间
// ============================================================================

namespace
{
// 控件初始化延迟时间 (单位: 秒)
constexpr float WidgetReadyDelayTime = 0.5f;

// UserWidget 可见性校验的重叠比例阈值 (低于该值则忽略)
constexpr float OverlapRatioThreshold = 0.6f;

// 控件类型名称常量
namespace WidgetTypeNames
{
constexpr const TCHAR* Undefined = TEXT("UNDEFINE");           // 未定义占位类型
constexpr const TCHAR* FigmaScrollBox = TEXT("SFigmaScrollBox");       // Figma 滚动框
constexpr const TCHAR* FigmaObjectWidget = TEXT("SFigmaObjectWidget"); // Figma 对象控件
}

// 无效文本键常量 (当节点缺少 TextKey 时使用)
constexpr const TCHAR* InvalidTextKey = TEXT(",INVALIDKEY");

// JSON 字段名常量集合
namespace JsonFieldNames
{
constexpr const TCHAR* WidgetTypeField = TEXT("WidgetType");            // 控件类型
constexpr const TCHAR* WidgetNameField = TEXT("WidgetName");            // 控件名称
constexpr const TCHAR* ChildNodesField = TEXT("ChildNodes");           // 子节点数组
constexpr const TCHAR* SlotTypeField = TEXT("SlotType");               // 插槽类型
constexpr const TCHAR* SlotField = TEXT("Slot");                       // 插槽数据
constexpr const TCHAR* SlotNameField = TEXT("SlotName");               // 命名插槽名 (如 Header/Body)
constexpr const TCHAR* CornersField = TEXT("corners");                 // 四角坐标 (小写)
constexpr const TCHAR* ObjectDataField = TEXT("ObjectData");           // 对象数据 (大写)
constexpr const TCHAR* PageWidthField = TEXT("PageWidth");             // 页面宽度
constexpr const TCHAR* PageHeightField = TEXT("PageHeight");           // 页面高度
constexpr const TCHAR* LocalSizeField = TEXT("LocalSize");             // 本地尺寸
constexpr const TCHAR* ParentCornersField = TEXT("ParentCorners");     // 父节点四角坐标
constexpr const TCHAR* SourceStringField = TEXT("SourceString");       // 源字符串 (原文)
constexpr const TCHAR* TextKeyField = TEXT("TextKey");                 // 文本键
constexpr const TCHAR* TranslateStringField = TEXT("TranslateString"); // 翻译后字符串
constexpr const TCHAR* HintTextField = TEXT("HintText");               // 提示文本
constexpr const TCHAR* TextField = TEXT("Text");                       // 文本 (大写)
constexpr const TCHAR* TextLowerField = TEXT("text");                  // 文本 (小写)
constexpr const TCHAR* HintTextStrField = TEXT("hinttextStr");         // 提示文本字符串
constexpr const TCHAR* HintTextSourceStrField = TEXT("HintTextSourceStr"); // 提示文本原文
constexpr const TCHAR* HintTextKeyField = TEXT("HintTextKey");         // 提示文本键
constexpr const TCHAR* TextStrField = TEXT("textStr");                 // 文本字符串
constexpr const TCHAR* UpperCornersField = TEXT("Corners");            // 四角坐标 (大写)
constexpr const TCHAR* LowerObjectDataField = TEXT("objectData");      // 对象数据 (小写)
constexpr const TCHAR* XField = TEXT("x");                             // X 坐标字段
constexpr const TCHAR* YField = TEXT("y");                             // Y 坐标字段
}
}

// ============================================================================
// 生命周期管理 (Lifecycle Management)
// ============================================================================

// 关闭编译器优化 (通常用于调试, 方便断点与变量查看)
LQA_DISABLE_OPTIMIZATION

void URestoreWindowProxy::Initialize(int32 InWindowId, UGameInstance* InGameInstance)
{
	// 保存窗口 ID
	WindowId = InWindowId;
	// 创建主画布面板对象
	WindowPanel = NewObject<UCanvasPanel>(this);
	// 缓存游戏实例引用
	CachedGameInstance = InGameInstance;

	// 纯 C++ 方式创建 LQA 还原根控件 (不依赖蓝图资源)
	RootObj = CreateWidget<URootObjWidget>(GetWorld(), URootObjWidget::StaticClass());
	if (!RootObj)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to create RootObjWidget"));
	}

	// 设置延迟定时器: 延迟 WidgetReadyDelayTime 秒后回调 OnWidgetSystemReady
	// 目的是等待控件系统完成初始化后再进行后续绘制
	if (CachedGameInstance)
	{
		CachedGameInstance->GetTimerManager().SetTimer(TimerHandle,
			FTimerDelegate::CreateUObject(this, &URestoreWindowProxy::OnWidgetSystemReady), WidgetReadyDelayTime,
			false);
	}
}

void URestoreWindowProxy::CreateWindow(const FVector2D& Size)
{
	// 将根控件添加到视口, 使用 WindowId 作为 ZOrder
	if (RootObj)
	{
		RootObj->AddToViewport(WindowId);
	}
}

void URestoreWindowProxy::DestroyWindow()
{
	// 将根控件从父级移除并置空
	if (RootObj)
	{
		RootObj->RemoveFromParent();
		RootObj = nullptr;
	}

	// 清空共享纹理缓存, 释放对象引用
	SharedTextureMap.Empty();
	WindowPanel = nullptr;
	CachedGameInstance = nullptr;
}

void URestoreWindowProxy::OnWidgetSystemReady()
{
	// 控件系统就绪后初始化根控件的缩放
	if (RootObj)
	{
		RootObj->InitScale();
	}
	// 标记为可以绘制
	bIsReadyToDraw = true;
}

// ============================================================================
// 控件与面板管理 (Widget & Panel Management)
// ============================================================================

void URestoreWindowProxy::DetermineScrollContext(const FString& PanelType,
	const TSharedPtr<FJsonObject>& PanelJsonObject, bool ParentScroll,
	const TArray<TSharedPtr<FJsonValue>>& ParentScrollCorners, bool& OutIsScroll,
	TArray<TSharedPtr<FJsonValue>>& OutScrollCorners)
{
	using namespace JsonFieldNames;

	// 若当前面板本身即为 Figma 滚动框, 则以自身的四角坐标作为滚动区域
	if (PanelType == WidgetTypeNames::FigmaScrollBox)
	{
		OutIsScroll = true;
		OutScrollCorners = PanelJsonObject->GetArrayField(CornersField);
	}
	else
	{
		// 否则继承父节点的滚动状态与滚动区域
		OutIsScroll = ParentScroll;
		OutScrollCorners = ParentScrollCorners;
	}
}

void URestoreWindowProxy::HandleUserWidget(UWidget* UserWidgetAsWidget,
	const TSharedPtr<FJsonObject>& UserWidgetJsonObject, UPanelWidget* UserWidgetParentPanel,
	const TArray<TSharedPtr<FJsonValue>>& ParentCorners, const FRestoreWidgetMeta& UserWidgetMetaData,
	UUserWidget*& OutUserWidget, UPanelWidget*& OutUserWidgetParentPanel,
	TSharedPtr<FJsonObject>& OutUserWidgetAdditionalData, FRestoreWidgetMeta& OutUserWidgetMetaData)
{
	using namespace JsonFieldNames;

	// 将传入控件转换为 UserWidget 类型
	OutUserWidget = Cast<UUserWidget>(UserWidgetAsWidget);
	OutUserWidgetParentPanel = UserWidgetParentPanel;

	// 拷贝插槽布局相关数据
	CopyJsonField(UserWidgetJsonObject, OutUserWidgetAdditionalData, SlotField);
	CopyJsonField(UserWidgetJsonObject, OutUserWidgetAdditionalData, SlotTypeField);

	// 从 ObjectData 中提取尺寸信息
	if (UserWidgetJsonObject->HasField(ObjectDataField))
	{
		const TSharedPtr<FJsonObject> ObjectData = UserWidgetJsonObject->GetObjectField(ObjectDataField);

		// 设置页面尺寸 (优先取 ObjectData, 缺失时回退到 LocalSize)
		if (ObjectData->HasField(PageWidthField))
		{
			OutUserWidgetAdditionalData->SetNumberField(PageWidthField, ObjectData->GetNumberField(PageWidthField));
			OutUserWidgetAdditionalData->SetNumberField(PageHeightField, ObjectData->GetNumberField(PageHeightField));
		}
		else if (UserWidgetJsonObject->HasField(LocalSizeField))
		{
			const TSharedPtr<FJsonObject> LocalSize = UserWidgetJsonObject->GetObjectField(LocalSizeField);
			OutUserWidgetAdditionalData->SetNumberField(PageWidthField, LocalSize->GetNumberField(XField));
			OutUserWidgetAdditionalData->SetNumberField(PageHeightField, LocalSize->GetNumberField(YField));
		}
	}

	// 设置附加属性: 父节点四角坐标与控件元数据
	OutUserWidgetAdditionalData->SetArrayField(ParentCornersField, ParentCorners);
	OutUserWidgetMetaData = UserWidgetMetaData;
}

void URestoreWindowProxy::AddUserWidget(UUserWidget* ParentUserWidget, UPanelWidget* CurrentPanel,
	UPanelWidget* ParentPanel, const TSharedPtr<FJsonObject>& UserWidgetAdditionalInfo,
	const TSharedPtr<FJsonObject>& CurrentPanelAdditionalInfo, const FRestoreWidgetMeta& UserWidgetMetaData)
{
	using namespace JsonFieldNames;

	// 校验该 UserWidget 是否应被忽略 (基于与父容器的重叠比例)
	const bool bShouldIgnore = ShouldIgnoreUserWidget(UserWidgetAdditionalInfo, CurrentPanelAdditionalInfo);

	// 提取 UserWidget 的尺寸
	FVector2D UserWidgetSize;
	UserWidgetSize.X = UserWidgetAdditionalInfo->GetNumberField(PageWidthField);
	UserWidgetSize.Y = UserWidgetAdditionalInfo->GetNumberField(PageHeightField);

	// 将 UserWidget 添加到根对象, 传入位置、尺寸、ZOrder 等信息
	RootObj->AddUserWidget(ParentUserWidget, CurrentPanel, ParentPanel, UserWidgetAdditionalInfo, FVector2D(0, 0),
		UserWidgetMetaData.WidgetPosition, UserWidgetMetaData.WidgetSize, UserWidgetSize, UserWidgetMetaData.ZOrder,
		RootObj->GetPositionScale(), bShouldIgnore);
}

UPanelWidget* URestoreWindowProxy::AddPanel(UUserWidget* OwningUserWidget, UPanelWidget* OwningUserWidgetParentPanel,
	const TSharedPtr<FJsonObject>& OwningUserWidgetAdditionalInfo, FRestoreWidgetMeta OwningUserWidgetMetaData,
	UPanelWidget* ParentPanel, FString ParentPanelType, TArray<TSharedPtr<FJsonValue>> ParentCorners, bool ParentScroll,
	TArray<TSharedPtr<FJsonValue>> ParentScrollCorners, const TSharedPtr<FJsonObject>& CurrentPanelJsonObject,
	const FVector2D& WindowSize, FVector2D RootPos)
{
	using namespace JsonFieldNames;

	// 根对象无效则直接返回
	if (!RootObj)
	{
		return nullptr;
	}

	// 获取 World 实例 (供子控件挂载与文本/图片检查使用)
	UWorld* WorldInstance = GetWorldInstance();

	// 解包 UNDEFINE 占位节点, 获取真正有效的面板 JSON
	TSharedPtr<FJsonObject> PanelJsonObject = UnwrapUndefinedNode(CurrentPanelJsonObject);
	if (!PanelJsonObject.IsValid())
	{
		return nullptr;
	}

	// 获取子节点数组, 若无子节点则返回
	const TArray<TSharedPtr<FJsonValue>>* ChildNodes;
	if (!PanelJsonObject->TryGetArrayField(ChildNodesField, ChildNodes))
	{
		return nullptr;
	}

	// 读取当前面板的类型与名称
	FString MyPanelType = PanelJsonObject->GetStringField(WidgetTypeField);
	const FString PanelWidgetName = PanelJsonObject->GetStringField(WidgetNameField);

	// 判定滚动上下文 (是否可滚动及滚动区域坐标)
	bool bIsScroll = false;
	TArray<TSharedPtr<FJsonValue>> ScrollCorners;
	DetermineScrollContext(MyPanelType, PanelJsonObject, ParentScroll, ParentScrollCorners, bIsScroll, ScrollCorners);

	// 当前面板相关变量
	FRestoreWidgetMeta PanelMetaData;
	UPanelWidget* MyPanel = nullptr;
	TSharedPtr<FJsonObject> PanelSlotJsonObject = MakeShared<FJsonObject>();

	// 嵌套 UserWidget 的输出变量 (当面板实际为 UserWidget 时, 由 HandleUserWidget 填充)
	UUserWidget* OutOwningUserWidget = nullptr;
	UPanelWidget* OutOwningUserWidgetParentPanel = nullptr;
	TSharedPtr<FJsonObject> OutOwningUserWidgetAdditionalInfo = MakeShared<FJsonObject>();
	FRestoreWidgetMeta OutOwningUserWidgetMetaData;

	// 当前面板为 UserWidget 且其根控件是叶子 (而非面板容器) 时, 用于承载这些叶子的临时根容器
	UPanelWidget* LocalRootPanel = nullptr;

	// 处理 UNDEFINE 类型: 直接继承父节点的属性
	if (MyPanelType == WidgetTypeNames::Undefined)
	{
		MyPanelType = ParentPanelType;
		MyPanel = ParentPanel;
		bIsScroll = ParentScroll;
		ScrollCorners = ParentScrollCorners;
	}
	else
	{
		UE_LOG(LogLQARestoreManager, Log, TEXT("URestoreWindowProxy AddPanel WidgetName: %s, PanelType: %s"), *PanelWidgetName,
			*MyPanelType);

		// 通过工厂从 JSON 创建面板控件及其元数据
		PanelMetaData = FWidget2JsonFactory::WidgetFromJsonForPanel(PanelJsonObject, WindowSize, this);
		UWidget* PanelWidget = PanelMetaData.WidgetIns;
		if (!PanelWidget)
		{
			UE_LOG(LogLQARestoreManager, Error, TEXT("URestoreWindowProxy WidgetFromJsonForPanel: %s"), *PanelWidgetName);
			return nullptr;
		}

		// 若存在插槽数据则进行拷贝
		CopyJsonField(PanelJsonObject, PanelSlotJsonObject, SlotField);
		CopyJsonField(PanelJsonObject, PanelSlotJsonObject, SlotTypeField);

		// 尝试将控件转换为 PanelWidget (容器类型)
		MyPanel = Cast<UPanelWidget>(PanelWidget);
		if (!MyPanel)
		{
			// 控件为 UserWidget (叶子类型, 而非容器)
			// 填充嵌套 UserWidget 的输出变量, 供递归处理使用
			HandleUserWidget(PanelWidget, PanelJsonObject, ParentPanel, ParentCorners, PanelMetaData,
				OutOwningUserWidget, OutOwningUserWidgetParentPanel, OutOwningUserWidgetAdditionalInfo,
				OutOwningUserWidgetMetaData);
		}

		// 命名插槽容器 (INamedSlotInterface, 如 UExpandableArea): 不是 UPanelWidget,
		// 其内容需通过 SetContentForSlot 挂载。
		// 注意: UUserWidget 也实现 INamedSlotInterface, 但它已由 HandleUserWidget 识别
		// (OutOwningUserWidget 非空); 此处用 !MyPanel && !OutOwningUserWidget 排除
		// 普通面板与 UserWidget, 避免误伤。
		if (!MyPanel && !OutOwningUserWidget)
		{
			if (INamedSlotInterface* NamedSlotContainer = Cast<INamedSlotInterface>(PanelWidget))
			{
				// 先把容器本身挂载到父面板
				if (ParentPanel)
				{
					RootObj->AddWidgetInPanel(ParentPanel, RootPos, ParentPanelType, PanelWidget,
						MakeShared<FJsonValueObject>(PanelSlotJsonObject), PanelMetaData.WidgetPosition,
						PanelMetaData.WidgetSize, PanelMetaData.ZOrder, PanelMetaData.Property, WorldInstance);
				}

				// 还原各命名插槽内容 (如 Header/Body)
				RestoreNamedSlotChildren(NamedSlotContainer, *ChildNodes, WindowSize, WorldInstance);

				return nullptr;
			}
		}

		// 能容纳 UMG 子控件
		if (!MyPanel && !OutOwningUserWidget)
		{
			if (ParentPanel)
			{
				RootObj->AddWidgetInPanel(ParentPanel, RootPos, ParentPanelType, PanelWidget,
					MakeShared<FJsonValueObject>(PanelSlotJsonObject), PanelMetaData.WidgetPosition,
					PanelMetaData.WidgetSize, PanelMetaData.ZOrder, PanelMetaData.Property, WorldInstance);
			}
			return nullptr;
		}

		// 仅当为顶层面板 (未嵌套于其他 UserWidget) 时, 才将面板加入根对象
		// OwningUserWidget == nullptr 表示这是独立面板, 而非某个父 UserWidget 的一部分
		if (!OwningUserWidget)
		{
			RootObj->AddPanel(ParentPanel,	   // 父面板
				ParentPanelType,			   // 父面板类型
				FVector2D(0, 0),			   // 父节点根位置
				MyPanel,					   // 当前面板
				MyPanelType,				   // 当前面板类型
				PanelMetaData.WidgetPosition,  // 面板位置
				PanelMetaData.WidgetSize,	   // 面板尺寸
				OutOwningUserWidget,		   // UserWidget 实例
				PanelSlotJsonObject,		   // 面板插槽信息
				PanelMetaData.ZOrder,		   // ZOrder 层级
				RootObj->GetPositionScale());  // 位置缩放
		}
	}

	// 是否需要计算滚动相关逻辑 (取决于父节点是否可滚动)
	const bool bNeedCalScroll = ParentScroll;

	// 遍历并处理所有子节点
	for (const TSharedPtr<FJsonValue>& ChildNode : *ChildNodes)
	{
		TSharedPtr<FJsonObject> ChildJsonObject = ChildNode->AsObject();
		if (!ChildJsonObject.IsValid())
		{
			continue;
		}

		// 读取子控件的名称与类型
		FString ChildWidgetName, ChildWidgetType;
		ChildJsonObject->TryGetStringField(WidgetNameField, ChildWidgetName);
		ChildJsonObject->TryGetStringField(WidgetTypeField, ChildWidgetType);

		// 确定子控件的四角坐标 (UNDEFINE 类型继承父节点坐标)
		TArray<TSharedPtr<FJsonValue>> ChildPanelCorners = ChildJsonObject->GetArrayField(CornersField);
		if (ChildWidgetType == WidgetTypeNames::Undefined)
		{
			ChildPanelCorners = ParentCorners;
		}

		// 针对 FigmaObjectWidget 校验其与滚动框的重叠; 若无重叠则跳过
		if (bNeedCalScroll && ChildWidgetType == WidgetTypeNames::FigmaObjectWidget)
		{
			if (!ValidateScrollBoxOverlap(ChildPanelCorners, ParentScrollCorners, ChildWidgetName))
			{
				continue;
			}
		}

		// 若子节点仍含有子节点, 则递归处理 (即容器类控件)
		if (HasChildNodes(ChildJsonObject))
		{
			AddPanel(OutOwningUserWidget, OutOwningUserWidgetParentPanel, OutOwningUserWidgetAdditionalInfo,
				OutOwningUserWidgetMetaData, MyPanel, MyPanelType, ChildPanelCorners, bIsScroll, ScrollCorners,
				ChildJsonObject, WindowSize, PanelMetaData.WidgetPosition);
		}
		else  // 处理叶子节点 (不含子节点的最终控件)
		{
			// 当前面板是 UserWidget (非面板容器) 时, 叶子节点应挂载到该 UserWidget 的根容器上。
			// 某些 UserWidget 的根控件直接是叶子 (如 TextBlock), 若直接跳过会导致整个条目内容丢失,
			// 因此这里为其创建一个临时根容器承载这些叶子。
			if (OutOwningUserWidget)
			{
				if (!LocalRootPanel)
				{
					LocalRootPanel = NewObject<UCanvasPanel>(this);
				}

				const FRestoreWidgetMeta ChildMetaData =
					FWidget2JsonFactory::WidgetFromJson(ChildJsonObject, WindowSize, this);
				if (!ChildMetaData.WidgetIns)
				{
					continue;
				}

				// 处理叶子节点的文本字段与翻译
				ProcessLeafNodeTextData(ChildJsonObject);

				// 将叶子控件挂载到临时根容器
				AddChildToPanel(
					LocalRootPanel, PanelMetaData.WidgetPosition, MyPanelType, ChildJsonObject, ChildMetaData, WorldInstance);
				continue;
			}

			// 从 JSON 创建控件元数据
			const FRestoreWidgetMeta ChildMetaData = FWidget2JsonFactory::WidgetFromJson(ChildJsonObject, WindowSize, this);
			if (!ChildMetaData.WidgetIns)
			{
				continue;
			}

			// 处理叶子节点的文本字段与翻译
			ProcessLeafNodeTextData(ChildJsonObject);

			// 将叶子控件添加到当前面板中
			AddChildToPanel(MyPanel, RootPos, MyPanelType, ChildJsonObject, ChildMetaData, WorldInstance);
		}
	}

	// 若存在拥有者 UserWidget, 则在处理完子节点后将其添加
	if (OwningUserWidget)
	{
		AddUserWidget(OwningUserWidget, MyPanel, OwningUserWidgetParentPanel, OwningUserWidgetAdditionalInfo,
			PanelJsonObject, OwningUserWidgetMetaData);
	}
	else if (OutOwningUserWidget && LocalRootPanel)
	{
		// 当前面板自身是 UserWidget, 且其根控件是叶子 (而非面板容器) 时的兜底挂载:
		// 把临时根容器设为该 UserWidget 的根控件并挂载到父面板, 避免条目内容丢失。
		AddUserWidget(OutOwningUserWidget, LocalRootPanel, OutOwningUserWidgetParentPanel,
			OutOwningUserWidgetAdditionalInfo, PanelJsonObject, OutOwningUserWidgetMetaData);
	}

	// 返回当前创建的面板
	return MyPanel;
}

// ============================================================================
// 视觉更新 (Visual Updates)
// ============================================================================

void URestoreWindowProxy::ProcessImageBackground(const FString& ImagePath)
{
	// 委托根对象处理背景图片更新
	if (RootObj)
	{
		RootObj->ProcessImageBackground(ImagePath);
	}
}

// ============================================================================
// JSON 处理工具 (JSON Processing Utilities)
// ============================================================================

TSharedPtr<FJsonObject> URestoreWindowProxy::UnwrapUndefinedNode(TSharedPtr<FJsonObject> NodeJson)
{
	using namespace JsonFieldNames;
	const FString WidgetType = NodeJson->GetStringField(WidgetTypeField);

	// 仅处理 UNDEFINE 类型节点
	if (WidgetType == WidgetTypeNames::Undefined)
	{
		const TArray<TSharedPtr<FJsonValue>> ChildNodesJson = NodeJson->GetArrayField(ChildNodesField);
		if (ChildNodesJson.Num() == 1)
		{
			// 仅有一个子节点时, 继续向下解包
			TSharedPtr<FJsonObject> ChildNode = ChildNodesJson[0]->AsObject();
			// 若当前节点含插槽信息而子节点没有, 则将插槽信息下传给子节点
			if (NodeJson->HasField(SlotTypeField) && !ChildNode->HasField(SlotTypeField))
			{
				CopyJsonField(NodeJson, ChildNode, SlotField);
				CopyJsonField(NodeJson, ChildNode, SlotTypeField);
			}
			return UnwrapUndefinedNode(ChildNode);
		}
		else if (ChildNodesJson.Num() == 0)
		{
			// 无子节点, 视为无效
			return nullptr;
		}

		// 多个子节点时无法继续解包, 返回当前节点
		return NodeJson;
	}
	// 非 UNDEFINE 节点直接返回
	return NodeJson;
}

void URestoreWindowProxy::CopyJsonField(
	const TSharedPtr<FJsonObject>& Source, TSharedPtr<FJsonObject>& Target, const FString& FieldName)
{
	// 源或目标无效则不处理
	if (!Source.IsValid() || !Target.IsValid())
	{
		return;
	}

	// 源存在该字段时, 将其值拷贝到目标
	if (Source->HasField(FieldName))
	{
		const TSharedPtr<FJsonValue> FieldValue = Source->TryGetField(FieldName);
		if (FieldValue.IsValid())
		{
			Target->SetField(FieldName, FieldValue);
		}
	}
}

bool URestoreWindowProxy::HasChildNodes(const TSharedPtr<FJsonObject>& JsonObject) const
{
	using namespace JsonFieldNames;
	// 同时满足 “存在 ChildNodes 字段” 且 “数组非空” 才算有子节点
	return JsonObject->HasField(ChildNodesField) && JsonObject->GetArrayField(ChildNodesField).Num() > 0;
}

UWorld* URestoreWindowProxy::GetWorldInstance() const
{
	if (!RootObj)
	{
		return nullptr;
	}

	// 通过 Slate 反射元数据取得源对象的 World
	const TSharedRef<SWidget> SlateWidget = RootObj->TakeWidget();
	const TSharedPtr<FReflectionMetaData> MetaData = SlateWidget->GetMetaData<FReflectionMetaData>();
	if (MetaData.IsValid())
	{
		const TWeakObjectPtr<UObject> SourceObject = MetaData->SourceObject;
		return SourceObject->GetWorld();
	}
	return nullptr;
}

void URestoreWindowProxy::AddChildToPanel(UPanelWidget* Panel, const FVector2D& PanelPosition, const FString& PanelType,
	const TSharedPtr<FJsonObject>& ChildJsonObject, const FRestoreWidgetMeta& ChildMeta, UWorld* WorldInstance)
{
	using namespace JsonFieldNames;

	// 拷贝插槽数据
	TSharedPtr<FJsonObject> SlotObject = MakeShared<FJsonObject>();
	CopyJsonField(ChildJsonObject, SlotObject, SlotField);
	CopyJsonField(ChildJsonObject, SlotObject, SlotTypeField);

	// 将子控件挂载到面板
	RootObj->AddWidgetInPanel(Panel, PanelPosition, PanelType, ChildMeta.WidgetIns,
		MakeShared<FJsonValueObject>(SlotObject), ChildMeta.WidgetPosition, ChildMeta.WidgetSize, ChildMeta.ZOrder,
		ChildMeta.Property, WorldInstance);
}

// ============================================================================
// 命名插槽内容还原 (Named Slot Content Restoration)
// ============================================================================

void URestoreWindowProxy::RestoreNamedSlotChildren(INamedSlotInterface* NamedSlotContainer,
	const TArray<TSharedPtr<FJsonValue>>& ChildNodes, const FVector2D& WindowSize, UWorld* WorldInstance)
{
	using namespace JsonFieldNames;

	if (!NamedSlotContainer)
	{
		return;
	}

	// 遍历各命名插槽子节点 (如 Header/Body)
	for (const TSharedPtr<FJsonValue>& ChildNode : ChildNodes)
	{
		const TSharedPtr<FJsonObject> ChildJsonObject = ChildNode->AsObject();
		if (!ChildJsonObject.IsValid())
		{
			continue;
		}

		// 读取命名插槽名 (采集侧写入的 SlotName 字段)
		FString SlotName;
		ChildJsonObject->TryGetStringField(SlotNameField, SlotName);
		if (SlotName.IsEmpty())
		{
			continue;
		}

		// 递归还原该命名插槽内容子树, 并通过 SetContentForSlot 挂载
		const FRestoreWidgetMeta ContentMeta = RestoreNamedSlotContent(ChildJsonObject, WindowSize, WorldInstance);
		if (ContentMeta.WidgetIns)
		{
			NamedSlotContainer->SetContentForSlot(FName(*SlotName), ContentMeta.WidgetIns);
		}
	}
}

FRestoreWidgetMeta URestoreWindowProxy::RestoreNamedSlotContent(
	const TSharedPtr<FJsonObject>& JsonObject, const FVector2D& WindowSize, UWorld* WorldInstance)
{
	using namespace JsonFieldNames;

	FRestoreWidgetMeta Meta;
	if (!JsonObject.IsValid())
	{
		return Meta;
	}

	// 容器节点: 还原面板并递归挂载其子节点
	if (HasChildNodes(JsonObject))
	{
		Meta = FWidget2JsonFactory::WidgetFromJsonForPanel(JsonObject, WindowSize, this);
		if (!Meta.WidgetIns)
		{
			return Meta;
		}

		if (UPanelWidget* Panel = Cast<UPanelWidget>(Meta.WidgetIns))
		{
			const FString PanelType = JsonObject->GetStringField(WidgetTypeField);
			const TArray<TSharedPtr<FJsonValue>>& ChildNodes = JsonObject->GetArrayField(ChildNodesField);

			for (const TSharedPtr<FJsonValue>& ChildNode : ChildNodes)
			{
				const TSharedPtr<FJsonObject> ChildJsonObject = ChildNode->AsObject();
				if (!ChildJsonObject.IsValid())
				{
					continue;
				}

				// 递归还原子节点
				const FRestoreWidgetMeta ChildMeta =
					RestoreNamedSlotContent(ChildJsonObject, WindowSize, WorldInstance);
				if (!ChildMeta.WidgetIns)
				{
					continue;
				}

				// 将子控件挂载到当前面板
				AddChildToPanel(Panel, Meta.WidgetPosition, PanelType, ChildJsonObject, ChildMeta, WorldInstance);
			}
		}
	}
	else
	{
		// 叶子节点: 还原控件并处理文本翻译
		Meta = FWidget2JsonFactory::WidgetFromJson(JsonObject, WindowSize, this);
		if (Meta.WidgetIns)
		{
			// ProcessLeafNodeTextData 会就地修改 JSON, 因此使用可变副本
			TSharedPtr<FJsonObject> MutableJson = JsonObject;
			ProcessLeafNodeTextData(MutableJson);
		}
	}

	return Meta;
}

// ============================================================================
// 文本与翻译处理 (Text & Translation Processing)
// ============================================================================

void URestoreWindowProxy::ProcessLeafNodeTextData(TSharedPtr<FJsonObject>& LeafNodeJsonObject)
{
	using namespace JsonFieldNames;

	// 处理文本翻译: 同时存在原文与文本键时, 获取翻译结果并写回
	if (LeafNodeJsonObject->HasField(SourceStringField) && LeafNodeJsonObject->HasField(TextKeyField))
	{
		const FString NewText = FLoaderUtils::GetTranslateString(
			LeafNodeJsonObject->GetStringField(TextKeyField), LeafNodeJsonObject->GetStringField(SourceStringField));
		LeafNodeJsonObject->SetStringField(TranslateStringField, NewText);
	}

	// 获取或准备 TextKey 值 (缺失时使用无效键常量)
	FString TextKeyValue;
	if (!LeafNodeJsonObject->TryGetStringField(TextKeyField, TextKeyValue))
	{
		TextKeyValue = InvalidTextKey;
	}

	// 处理 objectData, 提取 HintText 与 Text 字段
	const TSharedPtr<FJsonObject> ObjectDataObject = LeafNodeJsonObject->GetObjectField(LowerObjectDataField);
	if (ObjectDataObject.IsValid())
	{
		// 从 objectData 中提取提示文本 (HintText)
		if (ObjectDataObject->HasField(HintTextField))
		{
			const FString HintText = ObjectDataObject->GetStringField(HintTextField);
			// 仅当叶子节点尚无提示文本字段时才写入, 避免覆盖已有数据
			if (!LeafNodeJsonObject->HasField(HintTextStrField))
			{
				LeafNodeJsonObject->SetStringField(HintTextStrField, HintText);
				LeafNodeJsonObject->SetStringField(HintTextSourceStrField, HintText);
				LeafNodeJsonObject->SetStringField(HintTextKeyField, TextKeyValue);
			}
		}

		// 从 objectData 中提取正文文本 (Text)
		if (ObjectDataObject->HasField(TextField))
		{
			const FString Text = ObjectDataObject->GetStringField(TextLowerField);
			// 仅当叶子节点尚无文本字段时才写入
			if (!LeafNodeJsonObject->HasField(TextStrField))
			{
				LeafNodeJsonObject->SetStringField(TextStrField, Text);
				LeafNodeJsonObject->SetStringField(SourceStringField, Text);
				LeafNodeJsonObject->SetStringField(TextKeyField, TextKeyValue);
			}
		}
	}
}

// ============================================================================
// 校验工具 (Validation Utilities)
// ============================================================================

bool URestoreWindowProxy::ValidateScrollBoxOverlap(const TArray<TSharedPtr<FJsonValue>>& ChildWidgetCorners,
	const TArray<TSharedPtr<FJsonValue>>& ScrollBoxCorners, const FString& ChildWidgetName) const
{
	// 将 JSON 坐标数组转换为 FVector2D 点集
	TArray<FVector2D> ScrollBoxPoints;
	TArray<FVector2D> ChildWidgetPoints;

	FGeometryUtils::JsonArrayToVector2DArray(ScrollBoxCorners, ScrollBoxPoints);
	FGeometryUtils::JsonArrayToVector2DArray(ChildWidgetCorners, ChildWidgetPoints);

	// 判断子控件多边形与滚动框多边形是否重叠
	const bool bOverlap = FGeometryUtils::DoPolygonsOverlap(ChildWidgetPoints, ScrollBoxPoints);

#if !UE_BUILD_SHIPPING
	// 非发行版本下, 若无重叠则打印调试信息便于排查
	if (!bOverlap)
	{
		UE_LOG(LogLQARestoreManager, Log, TEXT("No intersection, %s"), *ChildWidgetName);
		FGeometryUtils::PrintJsonArrayPoints(ScrollBoxCorners, TEXT("ParentScrollCorners"));
		FGeometryUtils::PrintJsonArrayPoints(ChildWidgetCorners, TEXT("ChildPanelCorners"));
	}
#endif

	return bOverlap;
}

bool URestoreWindowProxy::ShouldIgnoreUserWidget(
	const TSharedPtr<FJsonObject>& UserWidgetPanelJsonObject, const TSharedPtr<FJsonObject>& PanelJsonObject) const
{
	using namespace JsonFieldNames;

	// 若不存在父节点四角坐标, 则无法判断, 默认不忽略
	if (!UserWidgetPanelJsonObject->HasField(ParentCornersField))
	{
		return false;
	}

	// 从 JSON 中读取父容器与 UserWidget 的四角坐标
	const TArray<TSharedPtr<FJsonValue>> ParentContainerCornersJson =
		UserWidgetPanelJsonObject->GetArrayField(ParentCornersField);
	const TArray<TSharedPtr<FJsonValue>> UserWidgetCornersJson = PanelJsonObject->GetArrayField(UpperCornersField);

	// 将 JSON 坐标解析为 FVector2D 数组
	TArray<FVector2D> ParentContainerCorners, UserWidgetCorners;
	if (!FGeometryUtils::ParseCornersFromJsonArray(ParentContainerCornersJson, ParentContainerCorners) ||
		!FGeometryUtils::ParseCornersFromJsonArray(UserWidgetCornersJson, UserWidgetCorners))
	{
		return false;
	}

	// 计算两者的包围盒及其重叠比例
	const FBox2D ParentContainerBox = FGeometryUtils::GetBoundingBox(ParentContainerCorners);
	const FBox2D UserWidgetBox = FGeometryUtils::GetBoundingBox(UserWidgetCorners);
	const float OverlapRatio = FGeometryUtils::GetOverlapRatio(ParentContainerBox, UserWidgetBox);

	// 重叠比例低于阈值则忽略该 UserWidget
	return OverlapRatio < OverlapRatioThreshold;
}

// ============================================================================
// 校验与导出 (Validation & Export)
// ============================================================================

void URestoreWindowProxy::GenerateCheckCorners(FString CheckInfoFilePath, TArray<FString> CheckParentWidgets)
{
	if (RootObj)
	{
		// 通过 Slate 反射元数据获取 World 实例
		TSharedRef<SWidget> SlateWidget = RootObj->TakeWidget();
		const TSharedPtr<FReflectionMetaData> MetaData = SlateWidget->GetMetaData<FReflectionMetaData>();
		UWorld* WorldInstance;

		// 文本与图片的校验信息列表
		TArray<TSharedPtr<FJsonValue>> CheckTextList;
		TArray<TSharedPtr<FJsonValue>> CheckImageList;

		if (MetaData.IsValid())
		{
			TWeakObjectPtr<UObject> SourceObject = MetaData->SourceObject;
			WorldInstance = SourceObject->GetWorld();
			// 收集指定父控件下的文本与图片校验信息
			CheckTextList = RootObj->GetTextCheckInfo(WorldInstance, CheckParentWidgets);
			CheckImageList = RootObj->GetImageCheckInfo(WorldInstance, CheckParentWidgets);
		}
		else
		{
			WorldInstance = nullptr;
			UE_LOG(LogLQARestoreManager, Error, TEXT("[LQA] Get Invalid World!"));
		}

		// 组装 JSON 对象, 包含 image 与 text 两个数组字段
		TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject());

		JsonObject->SetArrayField(TEXT("image"), CheckImageList);
		JsonObject->SetArrayField(TEXT("text"), CheckTextList);

		// 将 JSON 对象序列化为字符串
		FString JsonString;
		TSharedRef<TJsonWriter<>> Writer = TJsonWriterFactory<>::Create(&JsonString);
		FJsonSerializer::Serialize(JsonObject.ToSharedRef(), Writer);

		// 转换为 UTF-8 编码并写入目标文件
		FTCHARToUTF8 Converter(*JsonString);
		const char* UTF8Data = Converter.Get();
		int32 DataSize = Converter.Length();
		IPlatformFile& PlatformFile = FPlatformFileManager::Get().GetPlatformFile();
		TUniquePtr<IFileHandle> FileHandle(PlatformFile.OpenWrite(*CheckInfoFilePath));
		if (FileHandle)
		{
			FileHandle->Write((const uint8*) UTF8Data, DataSize);
		}
	}
}

// 恢复编译器优化
LQA_ENABLE_OPTIMIZATION