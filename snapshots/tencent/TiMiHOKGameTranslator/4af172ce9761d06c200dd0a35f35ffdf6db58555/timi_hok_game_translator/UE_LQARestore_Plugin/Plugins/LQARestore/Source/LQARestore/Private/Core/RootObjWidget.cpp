#include "Core/RootObjWidget.h"

// ---- Slate / UMG 控件及插槽相关头文件 ----
#include "Blueprint/SlateBlueprintLibrary.h"
#include "Blueprint/WidgetTree.h"
#include "Components/Button.h"
#include "Components/ButtonSlot.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/CheckBox.h"
#include "Components/GridPanel.h"
#include "Components/GridSlot.h"
#include "Components/HorizontalBox.h"
#include "Components/HorizontalBoxSlot.h"
#include "Components/Image.h"
#include "Components/RichTextBlock.h"
#include "Components/SafeZone.h"
#include "Components/SafeZoneSlot.h"
#include "Components/ScaleBox.h"
#include "Components/ScaleBoxSlot.h"
#include "Components/ScrollBox.h"
#include "Components/ScrollBoxSlot.h"
#include "Components/SizeBox.h"
#include "Components/SizeBoxSlot.h"
#include "Components/TextBlock.h"
#include "Components/UniformGridPanel.h"
#include "Components/UniformGridSlot.h"
#include "Components/VerticalBox.h"
#include "Components/VerticalBoxSlot.h"
#include "Components/Widget.h"
#include "Components/WrapBox.h"
#include "Components/WrapBoxSlot.h"
#include "Components/Overlay.h"
#include "Components/OverlaySlot.h"
// ---- 纹理、字体、图片编解码等支持 ----
#include "Engine/Texture2D.h"
#include "Fonts/FontMeasure.h"
#include "Framework/Application/SlateApplication.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "JsonObjectConverter.h"
#include "Materials/MaterialInstanceConstant.h"
#include "PaperSprite.h"
#include "Types/ReflectionMetadata.h"
// ---- 本插件内部工具类 ----
#include "Utils/ImageRenderUtils.h"
#include "Utils/TranslationUtils/ValidatorUtils.h"
#include "WidgetSlots/Core/Slot2JsonFactory.h"
#include "WidgetSlots/Core/RestoreWidget2JsonFactory.h"
#include "WidgetSlots/Core/WidgetDefines.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/SViewport.h"
#include "Widgets/SWidget.h"

// 定义头文件中声明的日志分类
DEFINE_LOG_CATEGORY(LogLQARestoreRootObj);

//==============================================================================
// 区块: 辅助函数
//==============================================================================

namespace LQAConstants
{
// 视口与缩放基准常量: 以 2560 宽度作为参考分辨率
constexpr float ReferenceViewportWidth = 2560.0f;

// LQA 校验阈值: 行高占比最小值 (低于此值视为行高异常)
constexpr float MinLineHeightPercentage = 0.7f;
}

/**
 * 保证浮点值有效 (非 NaN、非无穷大), 否则返回 0
 */
float SafeFloat(float value)
{
	if (FMath::IsNaN(value) || !FMath::IsFinite(value))
	{
		return 0.0f;
	}
	return value;
}

/**
 * 以四个角点的中心为基准, 对角点进行缩放
 * 用于根据 Alpha 通道分析结果裁剪控件的实际可见边界
 */
void ScaleCornerPoints(FVector2D& LeftBottomPos, FVector2D& LeftUpperPos, FVector2D& RightUpperPos,
	FVector2D& RightBottomPos, float ScaleX, float ScaleY)
{
	// 计算四个角点的中心点
	float CenterX = (LeftBottomPos.X + LeftUpperPos.X + RightUpperPos.X + RightBottomPos.X) / 4.0f;
	float CenterY = (LeftBottomPos.Y + LeftUpperPos.Y + RightUpperPos.Y + RightBottomPos.Y) / 4.0f;
	FVector2D Center(CenterX, CenterY);

	// 定义缩放操作: 以中心点为原点进行缩放
	TFunction<void(FVector2D&)> ScalePoint = [&](FVector2D& Point)
	{
		Point.X = (Point.X - Center.X) * ScaleX + Center.X;
		Point.Y = (Point.Y - Center.Y) * ScaleY + Center.Y;
	};

	// 直接就地修改四个角点
	ScalePoint(LeftBottomPos);
	ScalePoint(LeftUpperPos);
	ScalePoint(RightUpperPos);
	ScalePoint(RightBottomPos);
}

//==============================================================================
// 区块: 媒体与资源管理
//==============================================================================

// 加载 PNG 并设置为全屏背景 (详见头文件说明)
void URootObjWidget::ProcessImageBackground(const FString& ImagePath)
{
	// 重置忽略列表 (每次重设背景视为新的一轮布局)
	IgnoreUniqueIds.Empty();

	// 主画布或控件树无效时无法继续
	if (!MainCanvas || !WidgetTree)
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("MainCanvas or WidgetTree is null"));
		return;
	}

	// 读取整个文件到字节数组
	TArray<uint8> FileData;
	if (!FFileHelper::LoadFileToArray(FileData, *ImagePath))
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("Failed to load file: %s"), *ImagePath);
		return;
	}

	// 加载 ImageWrapper 模块并创建 PNG 解码器
	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	TSharedPtr<IImageWrapper> ImageWrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);

	// 将压缩数据交给解码器; 失败则返回
	if (!ImageWrapper.IsValid() || !ImageWrapper->SetCompressed(FileData.GetData(), FileData.Num()))
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("Failed to parse PNG data"));
		return;
	}

	// 解码出 RGBA (每通道 8 位) 的原始像素数据
	TArray<uint8> RawData;
	if (!ImageWrapper->GetRaw(ERGBFormat::RGBA, 8, RawData))
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("Failed to get raw image data"));
		return;
	}

	// 创建一张瞬态纹理 (运行时生成, 不保存到磁盘)
	UTexture2D* Texture = UTexture2D::CreateTransient(ImageWrapper->GetWidth(), ImageWrapper->GetHeight(), PF_R8G8B8A8);

	// UE 5.0+ 中 PlatformData 已私有化, 必须通过 GetPlatformData() 访问; UE4 下保留直接字段访问
#if ENGINE_MAJOR_VERSION >= 5
	if (!Texture || !Texture->GetPlatformData())
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("Failed to create texture"));
		return;
	}

	// 锁定首个 Mip 的内存, 将原始像素拷贝进去, 再解锁
	void* TextureData = Texture->GetPlatformData()->Mips[0].BulkData.Lock(LOCK_READ_WRITE);
	FMemory::Memcpy(TextureData, RawData.GetData(), RawData.Num());
	Texture->GetPlatformData()->Mips[0].BulkData.Unlock();
#else
	if (!Texture || !Texture->PlatformData)
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("Failed to create texture"));
		return;
	}

	void* TextureData = Texture->PlatformData->Mips[0].BulkData.Lock(LOCK_READ_WRITE);
	FMemory::Memcpy(TextureData, RawData.GetData(), RawData.Num());
	Texture->PlatformData->Mips[0].BulkData.Unlock();
#endif

	// 将 CPU 端数据提交到 GPU, 使纹理生效
	Texture->UpdateResource();

	// 创建一个 UImage 控件, 并把刚才的纹理作为笔刷资源
	UImage* BGImage = WidgetTree->ConstructWidget<UImage>(UImage::StaticClass(), TEXT("BGImage"));
	FSlateBrush Brush;
	Brush.SetResourceObject(Texture);
	BGImage->SetBrush(Brush);

	// 添加到主画布, 并设置锚点为全屏拉伸 (左上 0,0 到右下 1,1 偏移全 0)
	MainCanvas->AddChild(BGImage);
	if (UCanvasPanelSlot* CanvasSlot = Cast<UCanvasPanelSlot>(BGImage->Slot))
	{
		CanvasSlot->SetAnchors(FAnchors(0.f, 0.f, 1.f, 1.f));
		CanvasSlot->SetOffsets(FMargin(0.f, 0.f, 0.f, 0.f));
	}
}

//==============================================================================
// 区块: 控件层级管理
//==============================================================================

// 递归收集某控件及其所有子控件的唯一 ID
void CollectWidgetUniqueIDs(UWidget* Widget, TArray<int32>& OutUniqueIDs)
{
	if (!Widget)
		return;

	// 记录当前控件 ID
	OutUniqueIDs.Add(Widget->GetUniqueID());

	// 如果是面板控件, 递归处理所有子控件
	if (UPanelWidget* Panel = Cast<UPanelWidget>(Widget))
	{
		for (int32 i = 0; i < Panel->GetChildrenCount(); ++i)
		{
			CollectWidgetUniqueIDs(Panel->GetChildAt(i), OutUniqueIDs);
		}
	}
}

namespace
{
// 当无法确定插槽尺寸时使用的默认回退尺寸 (基于常见的 1440p 分辨率)
const FVector2D FallbackSlotSize(2560.0f, 1440.0f);
}

// 将 UserWidget 添加到控件层级并配置插槽 (详见头文件说明)
void URootObjWidget::AddUserWidget(UUserWidget* UserWidgetInstance, UWidget* UserWidgetRootCanvas,
	UPanelWidget* ParentPanel, TSharedPtr<FJsonObject> AdditionalInfo, FVector2D ParentRootPosition,
	FVector2D AbsolutePosition, FVector2D SlotSize, FVector2D DesiredSize, int32 ZOrder, int32 InPositionScale,
	bool bShouldIgnore)
{
	// 校验必要参数：UserWidget 实例不可为空
	if (!UserWidgetInstance)
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("[AddUserWidget] UserWidgetInstance is null"));
		return;
	}
	// 校验必要参数：UserWidget 根画布不可为空
	if (!UserWidgetRootCanvas)
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("[AddUserWidget] UserWidgetRootCanvas is null"));
		return;
	}

	// 父面板为空时回退到主画布
	if (!ParentPanel)
	{
		ParentPanel = MainCanvas;
	}

	// 设置 UserWidget 的根控件
	UserWidgetInstance->WidgetTree->RootWidget = UserWidgetRootCanvas;

	// 将 UserWidget 挂载到父面板
	ParentPanel->AddChild(UserWidgetInstance);

	// 配置插槽布局 (优先 JSON, 失败则默认画布定位)
	ConfigureUserWidgetSlot(UserWidgetInstance, AdditionalInfo, ParentPanel, ParentRootPosition, AbsolutePosition,
		SlotSize, ZOrder, InPositionScale);

	// 如需忽略, 将该 UserWidget 整个层级加入 LQA 忽略列表
	if (bShouldIgnore)
	{
		CollectIgnoredWidgets(UserWidgetInstance);
	}
}

// 配置 UserWidget 插槽: 优先使用 JSON 配置, 失败则回退默认画布定位
void URootObjWidget::ConfigureUserWidgetSlot(UUserWidget* UserWidgetInstance,
	const TSharedPtr<FJsonObject>& AdditionalInfo, UPanelWidget* ParentPanel, const FVector2D& ParentRootPosition,
	const FVector2D& AbsolutePosition, const FVector2D& SlotSize, int32 ZOrder, int32 InPositionScale)
{
	UPanelSlot* PanelSlot = UserWidgetInstance->Slot;
	if (!PanelSlot)
	{
		UE_LOG(LogLQARestoreRootObj, Warning, TEXT("[ConfigureUserWidgetSlot] PanelSlot is null"));
		return;
	}

	// 尝试从 JSON 应用插槽配置
	bool bSlotConfigured = false;
	if (AdditionalInfo.IsValid())
	{
		bSlotConfigured = FSlot2JsonFactory::SlotFromJson(AdditionalInfo, PanelSlot);
	}

	// JSON 配置失败时, 回退为默认画布定位
	if (!bSlotConfigured)
	{
		ApplyDefaultCanvasSlot(PanelSlot, ParentPanel, ParentRootPosition, AbsolutePosition, SlotSize, ZOrder,
			InPositionScale);  // 使用调用方传入的缩放参数

		if (UOverlaySlot* OverlaySlot = Cast<UOverlaySlot>(PanelSlot))
		{
			OverlaySlot->SetHorizontalAlignment(HAlign_Fill);
			OverlaySlot->SetVerticalAlignment(VAlign_Fill);
		}
	}
}

// 应用默认画布插槽: 将绝对位置转换为父画布的本地坐标并设置偏移
void URootObjWidget::ApplyDefaultCanvasSlot(UPanelSlot* PanelSlot, UPanelWidget* ParentPanel,
	const FVector2D& ParentRootPosition, const FVector2D& AbsolutePosition, const FVector2D& SlotSize, int32 ZOrder,
	int32 InPositionScale)
{
	// 仅支持画布面板插槽
	UCanvasPanelSlot* CanvasPanelSlot = Cast<UCanvasPanelSlot>(PanelSlot);
	if (!CanvasPanelSlot)
	{
		return;
	}

	// 获取父画布的缓存几何信息 (用于坐标换算)
	const FGeometry CanvasGeometry = ParentPanel->GetCachedGeometry();

	// 计算相对位置: 绝对位置减去父控件根位置
	const FVector2D RelativePosition = AbsolutePosition - ParentRootPosition;
	// 转换为父画布的本地坐标
	const FVector2D LocalPosition =
		CanvasGeometry.AbsoluteToLocal(RelativePosition + CanvasGeometry.LocalToAbsolute(FVector2D::ZeroVector));

	// 应用插槽配置: 锚点固定左上角, 设置偏移 (位置乘以缩放系数) 与尺寸、层级
	CanvasPanelSlot->SetAnchors(FAnchors(0.0f, 0.0f, 0.0f, 0.0f));
	CanvasPanelSlot->SetOffsets(
		FMargin(LocalPosition.X * InPositionScale, LocalPosition.Y * InPositionScale, SlotSize.X, SlotSize.Y));
	CanvasPanelSlot->SetZOrder(ZOrder);
}

// 收集 UserWidget 层级内所有控件 ID 到忽略列表
void URootObjWidget::CollectIgnoredWidgets(UUserWidget* UserWidgetInstance)
{
	UWidget* RootWidget = UserWidgetInstance->GetRootWidget();
	if (!RootWidget)
	{
		return;
	}

	// 递归收集后追加到总忽略列表
	TArray<int32> WidgetUniqueIDs;
	CollectWidgetUniqueIDs(RootWidget, WidgetUniqueIDs);

	IgnoreUniqueIds.Append(WidgetUniqueIDs);
}

// 将面板添加到另一面板并配置插槽 (JSON 优先, 失败回退默认画布定位)
void URootObjWidget::AddPanel(UPanelWidget* ParentPanel, FString ParentPanelType, FVector2D ParentRootPosition,
	UPanelWidget* Panel, FString PanelType, FVector2D PanelPosition, FVector2D PanelSize,
	UUserWidget* UserWidgetInstance, TSharedPtr<FJsonObject> PanelSlotInfo, int32 ZOrder, int32 InPositionScale)
{
	// 若为 UserWidget 则跳过 (由 AddUserWidget 单独处理)
	if (UserWidgetInstance)
	{
		UE_LOG(LogLQARestoreRootObj, Log, TEXT("this is UserWidgetInstance, ignore!"));
		return;
	}

	if (!Panel)
	{
		return;
	}

	// 父面板为空时使用主画布
	if (!ParentPanel)
	{
		ParentPanel = MainCanvas;
	}

	// 添加到父面板并取得插槽
	ParentPanel->AddChild(Panel);
	UPanelSlot* PanelSlot = Panel->Slot;

	// 尝试从 JSON 配置插槽
	bool bSlotConfigured = false;
	if (PanelSlotInfo.IsValid())
	{
		bSlotConfigured = FSlot2JsonFactory::SlotFromJson(PanelSlotInfo, PanelSlot);
	}

	// JSON 配置失败则回退默认画布定位 (注意此处使用成员变量 PositionScale)
	if (!bSlotConfigured)
	{
		ApplyDefaultCanvasSlot(
			PanelSlot, ParentPanel, ParentRootPosition, PanelPosition, PanelSize, ZOrder, this->PositionScale);
	}
}

// 将子控件添加到面板, 并在 needOCR 时注册到 LQA 检查列表
void URootObjWidget::AddWidgetInPanel(UPanelWidget* Panel, FVector2D PanelPosition, FString PanelType, UWidget* Child,
	TSharedPtr<FJsonValue> ChildSlotInfo, FVector2D ChildPosition, FVector2D ChildSize, int32 ChildZOrder,
	TSharedPtr<FJsonObject> ChildProperty, UWorld* WorldInstance)
{
	if (!Child)
	{
		return;
	}

	// 根据子控件属性判断是否需要注册到 LQA 检查
	if (ChildProperty.IsValid())
	{
		const bool bIsImage = ChildProperty->GetBoolField(TEXT("isImage"));
		const bool bIsText = ChildProperty->GetBoolField(TEXT("isText"));
		const bool bNeedOCR = ChildProperty->GetBoolField(TEXT("needOCR"));

		// 仅当需要 OCR 时才登记
		if (bNeedOCR)
		{
			if (bIsImage)
			{
				// 图片控件: 加入图片检查列表及对应属性
				CheckImageWidgets.Add(Child);
				ImageProperty.Add(ChildProperty);
			}
			else if (bIsText)
			{
				// 文本控件: 加入文本检查列表及对应属性
				CheckTextWidgets.Add(Child);
				TextProperty.Add(ChildProperty);
			}
		}
	}

	// 添加到面板并取得插槽
	Panel->AddChild(Child);
	UPanelSlot* PanelSlot = Child->Slot;

	// 尝试从 JSON 应用插槽配置
	bool bSlotConfigured = false;
	if (ChildSlotInfo.IsValid())
	{
		TSharedPtr<FJsonObject> SlotJsonObject = ChildSlotInfo->AsObject();
		if (SlotJsonObject.IsValid())
		{
			bSlotConfigured = FSlot2JsonFactory::SlotFromJson(SlotJsonObject, PanelSlot);
		}
	}

	// JSON 配置失败则回退默认画布定位
	if (!bSlotConfigured)
	{
		ApplyDefaultCanvasSlot(
			PanelSlot, Panel, PanelPosition, ChildPosition, ChildSize, ChildZOrder, this->PositionScale);
	}
}

// 初始化缩放系数 (当前实现保持为 1, 原始缩放逻辑已注释保留)
void URootObjWidget::InitScale()
{
	// 当前禁用: 原逻辑通过计算反向缩放来归一化画布渲染
	// 若重新启用, 会根据画布几何缩放来设置 PositionScale

	// 默认缩放为 1 (即不缩放)
	PositionScale = 1;

	/* 原始实现 (已注释):
	if (FSlateApplication::Get().GetGameViewport())
	{
		FVector2D Scale{MainCanvas->GetCachedGeometry().Scale};
		UE_LOG(LogLQARestore, Warning, TEXT("Get Scale: %f"), Scale.X);
		Scale.X = 1 / Scale.X;
		Scale.Y = 1 / Scale.Y;
		MainCanvas->SetRenderScale(Scale); // 设置为归一化缩放
		MainCanvas->SetRenderTransformPivot(FVector2D::ZeroVector);

		// 可在此根据计算结果设置 PositionScale
		// PositionScale = static_cast<int32>(Scale.X);
	}
	*/
}

// 控件重建: 纯 C++ 创建主画布作为根控件
TSharedRef<SWidget> URootObjWidget::RebuildWidget()
{
	// 纯 C++ 创建根画布, 不依赖任何蓝图资产; 且仅创建一次
	if (WidgetTree && !MainCanvas)
	{
		MainCanvas = WidgetTree->ConstructWidget<UCanvasPanel>(
			UCanvasPanel::StaticClass(), TEXT("MainCanvas"));
		WidgetTree->RootWidget = MainCanvas;
	}
	return Super::RebuildWidget();
}

/**
 * 校验文本内容的常见 LQA 问题
 * - 错误码 9: 行高过小 (< 0.7)
 * - 错误码 8: 译文与原文之间 HTML 标签或 Hash 标签 (#标记) 不匹配
 */
void URootObjWidget::CheckTextBugs(TSharedPtr<FJsonObject> TextInfo)
{
	// 使用 TSet 去重, 避免重复加入相同错误码
	TSet<FString> Bugs;

	// 检查行高占比: 有效且小于阈值则记为错误码 9
	const float LineHeightPercentage = TextInfo->GetNumberField(TEXT("lineHeightPercentage"));
	if (LineHeightPercentage > 0.0f && LineHeightPercentage < LQAConstants::MinLineHeightPercentage)
	{
		Bugs.Add(TEXT("9"));
	}

	// 取出译文与原文字符串
	const FString TextStr = TextInfo->GetStringField(TEXT("textStr"));
	const FString SourceStr = TextInfo->GetStringField(TEXT("SourceString"));

	// 若译文包含 '<', 比较译文与原文的 HTML 标签集合是否一致
	if (TextStr.Contains(TEXT("<")))
	{
		TArray<FString> Tags1, Tags2;
		const bool bIsEqual = FValidatorUtils::AreHtmlTagSetsEqual(TextStr, SourceStr, Tags1, Tags2);
		if (!bIsEqual)
		{
			Bugs.Add(TEXT("8"));
		}
	}

	// 若译文含 '#' 但不是 "##Notrans" 标记, 比较 Hash 标签集合是否一致
	if (!TextStr.Contains(TEXT("##Notrans")) && TextStr.Contains(TEXT("#")))
	{
		TArray<FString> Tags1, Tags2;
		const bool bIsEqual = FValidatorUtils::AreHashTagSetsEqual(TextStr, SourceStr, Tags1, Tags2);
		if (!bIsEqual)
		{
			Bugs.Add(TEXT("8"));
		}
	}

	// 将错误码集合写回 JSON 的 "preprocessing_err" 字段
	TArray<TSharedPtr<FJsonValue>> BugJsonArray;
	for (const FString& Bug : Bugs)
	{
		BugJsonArray.Add(MakeShared<FJsonValueString>(Bug));
	}
	TextInfo->SetArrayField(TEXT("preprocessing_err"), BugJsonArray);
}

/**
 * 收集所有已注册文本控件的 LQA 信息
 * 若提供了 CheckParentWidgets，则按父控件名前缀过滤
 * 返回包含角点、缺陷、显示信息的 JSON 对象数组
 */
TArray<TSharedPtr<FJsonValue>> URootObjWidget::GetTextCheckInfo(
	UWorld* WorldInstance, TArray<FString> CheckParentWidgets)
{
	UE_LOG(LogLQARestoreRootObj, Warning, TEXT("GenerateTextCheckInfo：%d"), CheckTextWidgets.Num());
	UE_LOG(LogLQARestoreRootObj, Warning, TEXT("TextProperty：%d"), TextProperty.Num());

	TArray<TSharedPtr<FJsonValue>> TextInfos;
	// 预留容量, 减少动态扩容开销
	TextInfos.Reserve(CheckTextWidgets.Num());

	// 取过滤用的顶层父控件名 (取列表首项), 非空时启用过滤
	const FString TopParentWidgetName = (CheckParentWidgets.Num() > 0) ? CheckParentWidgets[0] : TEXT("");
	const bool bFilterByParent = !TopParentWidgetName.IsEmpty();

	for (int32 Index = 0; Index < CheckTextWidgets.Num(); ++Index)
	{
		// 弱引用取原始指针, 可能已被 GC 回收
		UWidget* Widget = CheckTextWidgets[Index].Get();
		if (!Widget)
		{
			continue;
		}

		// 取对应的文本属性 JSON
		const TSharedPtr<FJsonObject>& TextInfo = TextProperty[Index];
		if (!TextInfo.IsValid())
		{
			continue;
		}

		// 跳过空文本
		if (TextInfo->GetStringField(TEXT("textStr")).IsEmpty())
		{
			continue;
		}

		// 跳过忽略列表中的控件
		if (IgnoreUniqueIds.Contains(Widget->GetUniqueID()))
		{
			continue;
		}

		// 按父控件名前缀过滤
		if (bFilterByParent)
		{
			const FString ParentWidgetName = TextInfo->GetStringField(TEXT("ParentWidget"));
			if (!ParentWidgetName.StartsWith(TopParentWidgetName))
			{
				continue;
			}
		}

		// 计算并更新角点坐标 (文本模式, 带对齐信息)
		TextInfo->SetArrayField(
			TEXT("corners"), GetCorners(Widget, WorldInstance, true, TextInfo->GetStringField(TEXT("justification")),
								 TextInfo->GetStringField(TEXT("verticalJustification"))));

		// 执行文本缺陷校验
		CheckTextBugs(TextInfo);

		TextInfos.Add(MakeShared<FJsonValueObject>(TextInfo));
	}

	UE_LOG(LogLQARestoreRootObj, Warning, TEXT("TextInfos: %d"), TextInfos.Num());
	return TextInfos;
}

/**
 * 收集所有已注册图片控件的 LQA 信息
 * 会过滤不可见控件及超出视口范围的控件
 * 返回包含角点坐标的 JSON 对象数组
 */
TArray<TSharedPtr<FJsonValue>> URootObjWidget::GetImageCheckInfo(
	UWorld* WorldInstance, TArray<FString> CheckParentWidgets)
{
	UE_LOG(LogLQARestoreRootObj, Warning, TEXT("GenerateImageCheckInfo: %d"), CheckImageWidgets.Num());
	UE_LOG(LogLQARestoreRootObj, Warning, TEXT("ImageProperty: %d"), ImageProperty.Num());

	TArray<TSharedPtr<FJsonValue>> ImageInfos;
	ImageInfos.Reserve(CheckImageWidgets.Num());

	// 过滤用父控件名及开关
	const FString TopParentWidgetName = (CheckParentWidgets.Num() > 0) ? CheckParentWidgets[0] : TEXT("");
	const bool bFilterByParent = !TopParentWidgetName.IsEmpty();

	for (int32 Index = 0; Index < CheckImageWidgets.Num(); ++Index)
	{
		// 跳过已回收或不可见的控件
		UWidget* Widget = CheckImageWidgets[Index].Get();
		if (!Widget || !Widget->IsVisible())
		{
			continue;
		}

		const TSharedPtr<FJsonObject>& ImageInfo = ImageProperty[Index];
		if (!ImageInfo.IsValid())
		{
			continue;
		}

		// 跳过忽略列表中的控件
		if (IgnoreUniqueIds.Contains(Widget->GetUniqueID()))
		{
			continue;
		}

		// 按父控件名前缀过滤
		if (bFilterByParent)
		{
			const FString ParentWidgetName = ImageInfo->GetStringField(TEXT("ParentWidget"));
			if (!ParentWidgetName.StartsWith(TopParentWidgetName))
			{
				continue;
			}
		}

		// 根据控件类型进一步判断可见性
		bool bVisible = false;
		if (UImage* Image = Cast<UImage>(Widget))
		{
			// 图片: 根据笔刷、可见性、渲染透明度、缩放综合判断
#if ENGINE_MAJOR_VERSION >= 5
			bVisible = FImageRenderUtils::IsBrushVisible(
				Image->GetBrush(), Image->GetVisibility(), Image->GetRenderOpacity(), Image->GetRenderTransform().Scale);
#else
			bVisible = FImageRenderUtils::IsBrushVisible(
				Image->Brush, Image->GetVisibility(), Image->GetRenderOpacity(), Image->RenderTransform.Scale);
#endif
		}
		else if (Cast<UButton>(Widget))
		{
			// 按钮: 始终视为可见
			bVisible = true;
		}
		else
		{
			// 不支持的控件类型, 跳过
			continue;
		}

		if (!bVisible)
		{
			continue;
		}

		// 计算角点坐标 (图片模式); 为空说明被过滤掉 (无背景/超视口等)
		TArray<TSharedPtr<FJsonValue>> Corners = GetCorners(Widget, WorldInstance, false);
		if (Corners.Num() == 0)
		{
			continue;
		}

		// 写入角点、添加索引, 并初始化错误列表为空
		ImageInfo->SetArrayField(TEXT("corners"), Corners);
		ImageInfo->SetNumberField(TEXT("addIndex"), Index);
		ImageInfo->SetArrayField(TEXT("preprocessing_err"), TArray<TSharedPtr<FJsonValue>>());

		ImageInfos.Add(MakeShared<FJsonValueObject>(ImageInfo));
	}

	UE_LOG(LogLQARestoreRootObj, Warning, TEXT("ImageInfos: %d"), ImageInfos.Num());
	return ImageInfos;
}

// 将二维坐标转换为含 x/y 字段的 JSON 对象
TSharedPtr<FJsonObject> URootObjWidget::ConvertPos2Json(const FVector2D& InPos)
{
	TSharedPtr<FJsonObject> PosValue = MakeShared<FJsonObject>();
	PosValue->SetNumberField(TEXT("x"), InPos.X);
	PosValue->SetNumberField(TEXT("y"), InPos.Y);
	return PosValue;
}

//==============================================================================
// 区块: 角点计算 - 辅助函数
//==============================================================================

// 计算文本控件的四个角点 (按期望尺寸 + 对齐偏移, Y 轴翻转)
bool URootObjWidget::CalculateTextCorners(UWidget* Widget, const FVector2D& PixelPos, const FVector2D& ViewportSize,
	const FString& Justification, const FString& VerticalJustification, FVector2D& OutLeftBottom,
	FVector2D& OutLeftUpper, FVector2D& OutRightUpper, FVector2D& OutRightBottom)
{
	// 取控件几何、容器绝对尺寸, 以及按参考分辨率换算的缩放
	const FGeometry& CanvasGeometry = Widget->GetCachedGeometry();
	const FVector2D AbsoluteSize = USlateBlueprintLibrary::GetAbsoluteSize(CanvasGeometry);
	const float Scale = ViewportSize.X / LQAConstants::ReferenceViewportWidth;
	// 使用期望尺寸 (实际渲染文本大小) 乘以缩放
	const FVector2D DesiredSize = Widget->GetDesiredSize() * Scale;

	// 根据水平对齐计算水平偏移
	float HorizontalOffset = 0.0f;
	const FString LowerJustification = Justification.ToLower();
	if (LowerJustification == TEXT("center"))
	{
		HorizontalOffset = (AbsoluteSize.X - DesiredSize.X) / 2.0f;  // 居中
	}
	else if (LowerJustification == TEXT("right"))
	{
		HorizontalOffset = AbsoluteSize.X - DesiredSize.X;  // 右对齐
	}

	// 根据垂直对齐计算垂直偏移
	float VerticalOffset = 0.0f;
	const FString LowerVerticalJustification = VerticalJustification.ToLower();
	if (LowerVerticalJustification == TEXT("center"))
	{
		VerticalOffset = (AbsoluteSize.Y - DesiredSize.Y) / 2.0f;  // 垂直居中
	}
	else if (LowerVerticalJustification == TEXT("bottom"))
	{
		VerticalOffset = AbsoluteSize.Y - DesiredSize.Y;  // 底部对齐
	}

	// 计算四个角点坐标 (Y 轴翻转: 屏幕坐标与视口坐标 Y 方向相反)
	OutLeftUpper.X = PixelPos.X + HorizontalOffset;
	OutLeftUpper.Y = ViewportSize.Y - (PixelPos.Y + VerticalOffset);

	OutLeftBottom.X = PixelPos.X + HorizontalOffset;
	OutLeftBottom.Y = ViewportSize.Y - (PixelPos.Y + VerticalOffset + DesiredSize.Y);

	OutRightUpper.X = OutLeftUpper.X + DesiredSize.X;
	OutRightUpper.Y = ViewportSize.Y - (PixelPos.Y + VerticalOffset);

	OutRightBottom.X = OutLeftUpper.X + DesiredSize.X;
	OutRightBottom.Y = ViewportSize.Y - (PixelPos.Y + VerticalOffset + DesiredSize.Y);

	return true;
}

// 针对 Texture2D, 根据源图 Alpha 边界缩放角点 (裁剪透明边)
void URootObjWidget::ApplyTextureAlphaScaling(
	UTexture2D* Texture, FVector2D& LeftBottom, FVector2D& LeftUpper, FVector2D& RightUpper, FVector2D& RightBottom)
{
	if (!Texture)
	{
		return;
	}

#if WITH_EDITOR
	// 从源数据由外向内扫描得到非透明像素的包围盒
	const FIntRect AlphaBounds = FImageRenderUtils::GetAlphaBoundsFromSource_OuterToInner(Texture, 0);
	const int32 OrigWidth = Texture->Source.GetSizeX();
	const int32 OrigHeight = Texture->Source.GetSizeY();

	// 用可见边界与原始尺寸的比例作为缩放系数
	if (OrigWidth > 0 && OrigHeight > 0)
	{
		const float ScaleX = AlphaBounds.Width() / static_cast<float>(OrigWidth);
		const float ScaleY = AlphaBounds.Height() / static_cast<float>(OrigHeight);
		ScaleCornerPoints(LeftBottom, LeftUpper, RightUpper, RightBottom, ScaleX, ScaleY);
	}
#else
	// 打包 (非编辑器) 构建下无法读取纹理源数据, 不做 Alpha 裁剪缩放, 保持原角点
	UE_LOG(LogLQARestoreRootObj, Warning,
		TEXT("ApplyTextureAlphaScaling 依赖编辑器源数据(Source), 打包版本跳过 Alpha 缩放"));
#endif
}

// 针对 PaperSprite, 根据其在源纹理中的区域计算 Alpha 边界并缩放角点
void URootObjWidget::ApplySpriteAlphaScaling(
	UPaperSprite* Sprite, FVector2D& LeftBottom, FVector2D& LeftUpper, FVector2D& RightUpper, FVector2D& RightBottom)
{
	if (!Sprite)
	{
		return;
	}

#if WITH_EDITOR
	// 取精灵的源纹理
	UTexture2D* SpriteTexture = Sprite->GetSourceTexture();
	if (!SpriteTexture)
	{
		return;
	}

	// 取精灵在源纹理中的 UV 起点与尺寸 (浮点)
	const FVector2D SpriteUV_Float = Sprite->GetSourceUV();
	const FVector2D SpriteSize_Float = Sprite->GetSourceSize();

	// 转为整型像素坐标
	const FIntPoint SourceUV(FMath::FloorToInt(SpriteUV_Float.X), FMath::FloorToInt(SpriteUV_Float.Y));
	const FIntPoint SourceDimension(FMath::FloorToInt(SpriteSize_Float.X), FMath::FloorToInt(SpriteSize_Float.Y));

	// 在指定子区域内计算 Alpha 边界
	const FIntRect AlphaBounds =
		FImageRenderUtils::GetAlphaBoundsFromSource_OuterToInner(SpriteTexture, 0, SourceUV, SourceDimension);

	// 用可见边界与精灵尺寸的比例缩放角点
	if (SourceDimension.X > 0 && SourceDimension.Y > 0)
	{
		const float ScaleX = AlphaBounds.Width() / static_cast<float>(SourceDimension.X);
		const float ScaleY = AlphaBounds.Height() / static_cast<float>(SourceDimension.Y);
		ScaleCornerPoints(LeftBottom, LeftUpper, RightUpper, RightBottom, ScaleX, ScaleY);
	}
#else
	// 打包 (非编辑器) 构建下 UPaperSprite 源纹理接口不可用, 跳过 Alpha 缩放
	UE_LOG(LogLQARestoreRootObj, Warning,
		TEXT("ApplySpriteAlphaScaling 依赖编辑器 PaperSprite 源数据, 打包版本跳过 Alpha 缩放"));
#endif
}

// 计算图片控件的四个角点 (含有效性校验、坐标换算、Alpha 裁剪与视口判断)
bool URootObjWidget::CalculateImageCorners(UWidget* Widget, UWorld* WorldInstance, const FVector2D& ViewportSize,
	FVector2D& OutLeftBottom, FVector2D& OutLeftUpper, FVector2D& OutRightUpper, FVector2D& OutRightBottom)
{
	const FGeometry& CanvasGeometry = Widget->GetCachedGeometry();
	const FVector2D AbsoluteSize = USlateBlueprintLibrary::GetAbsoluteSize(CanvasGeometry);
	const float Scale = ViewportSize.X / LQAConstants::ReferenceViewportWidth;
	const FVector2D DesiredSize = Widget->GetDesiredSize() * Scale;

	// 尺寸近似为 0 时视为无效, 直接返回
	if (FMath::IsNearlyZero(FMath::Min(AbsoluteSize.X, DesiredSize.X)) ||
		FMath::IsNearlyZero(FMath::Min(AbsoluteSize.Y, DesiredSize.Y)))
	{
		return false;
	}

	// 控件无可见背景时跳过
	if (FImageRenderUtils::IsWidgetNoBackground(Widget))
	{
		return false;
	}

	// 取控件几何与本地尺寸, 构造本地坐标系下的四个角
	const FGeometry Geometry = Widget->GetCachedGeometry();
	const FVector2D LocalSize = Geometry.GetLocalSize();

	const FVector2D BottomLeft(0, LocalSize.Y);
	const FVector2D TopLeft(0, 0);
	const FVector2D TopRight(LocalSize.X, 0);
	const FVector2D BottomRight(LocalSize.X, LocalSize.Y);

	// 将本地坐标转换为视口坐标
	FVector2D ViewportPos;
	USlateBlueprintLibrary::LocalToViewport(WorldInstance, Geometry, BottomLeft, OutLeftBottom, ViewportPos);
	USlateBlueprintLibrary::LocalToViewport(WorldInstance, Geometry, TopLeft, OutLeftUpper, ViewportPos);
	USlateBlueprintLibrary::LocalToViewport(WorldInstance, Geometry, TopRight, OutRightUpper, ViewportPos);
	USlateBlueprintLibrary::LocalToViewport(WorldInstance, Geometry, BottomRight, OutRightBottom, ViewportPos);

	// Y 轴翻转
	OutLeftBottom.Y = ViewportSize.Y - OutLeftBottom.Y;
	OutLeftUpper.Y = ViewportSize.Y - OutLeftUpper.Y;
	OutRightUpper.Y = ViewportSize.Y - OutRightUpper.Y;
	OutRightBottom.Y = ViewportSize.Y - OutRightBottom.Y;

	// 取控件的笔刷 (图片直接取笔刷: 按钮按当前状态取对应样式)
	const FSlateBrush* ImageBrush = nullptr;

	if (UImage* MyImage = Cast<UImage>(Widget))
	{
#if ENGINE_MAJOR_VERSION >= 5
		ImageBrush = &MyImage->GetBrush();
#else
		ImageBrush = &MyImage->Brush;
#endif
	}
	else if (UButton* MyButton = Cast<UButton>(Widget))
	{
#if ENGINE_MAJOR_VERSION >= 5
		const FButtonStyle& ButtonStyle = MyButton->GetStyle();
#else
		const FButtonStyle& ButtonStyle = MyButton->WidgetStyle;
#endif
		// 取底层 Slate 按钮以读取按下/悬停状态
		TSharedPtr<SWidget> SlateWidget = MyButton->GetCachedWidget();
		TSharedPtr<SButton> SButtonWidget = StaticCastSharedPtr<SButton>(SlateWidget);

		if (SButtonWidget.IsValid())
		{
			const bool bPressed = SButtonWidget->IsPressed();
			const bool bHovered = SButtonWidget->IsHovered();

			// 根据状态选择对应笔刷: 按下 > 悬停 > 普通
			if (bPressed)
			{
				ImageBrush = &ButtonStyle.Pressed;
			}
			else if (bHovered)
			{
				ImageBrush = &ButtonStyle.Hovered;
			}
			else
			{
				ImageBrush = &ButtonStyle.Normal;
			}
		}
	}

	if (ImageBrush)
	{
		// 根据资源类型应用 Alpha 裁剪缩放
		if (UTexture2D* Texture = Cast<UTexture2D>(ImageBrush->GetResourceObject()))
		{
			ApplyTextureAlphaScaling(Texture, OutLeftBottom, OutLeftUpper, OutRightUpper, OutRightBottom);
		}
		else if (UPaperSprite* Sprite = Cast<UPaperSprite>(ImageBrush->GetResourceObject()))
		{
			ApplySpriteAlphaScaling(Sprite, OutLeftBottom, OutLeftUpper, OutRightUpper, OutRightBottom);
		}
		else if (Cast<UMaterialInstanceConstant>(ImageBrush->GetResourceObject()))
		{
			// 材质实例暂不支持, 跳过
			return false;
		}

		// 任一角点超出视口即判定为不可用
		const bool bIsAnyPointOutOfViewport = FImageRenderUtils::IsPointOutOfViewport(OutLeftBottom, ViewportSize) ||
											  FImageRenderUtils::IsPointOutOfViewport(OutLeftUpper, ViewportSize) ||
											  FImageRenderUtils::IsPointOutOfViewport(OutRightUpper, ViewportSize) ||
											  FImageRenderUtils::IsPointOutOfViewport(OutRightBottom, ViewportSize);

		if (bIsAnyPointOutOfViewport)
		{
			return false;
		}
	}

	return true;
}

// 将四个角点按 [左下, 左上, 右上, 右下] 顺序转换为 JSON 数组
TArray<TSharedPtr<FJsonValue>> URootObjWidget::CornersToJsonArray(
	const FVector2D& LeftBottom, const FVector2D& LeftUpper, const FVector2D& RightUpper, const FVector2D& RightBottom)
{
	TArray<TSharedPtr<FJsonValue>> CornerPosList;
	CornerPosList.Reserve(4);

	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(LeftBottom)));
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(LeftUpper)));
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(RightUpper)));
	CornerPosList.Emplace(MakeShared<FJsonValueObject>(ConvertPos2Json(RightBottom)));

	return CornerPosList;
}

//==============================================================================
// 区块: 角点计算 - 主函数
//==============================================================================

/**
 * 计算控件在屏幕空间中的四个角点坐标
 *
 * 文本控件:
 * - 使用 DesiredSize (实际渲染文本尺寸) 而非 AbsoluteSize (容器尺寸)
 * - 应用文本对齐偏移 (水平 Justification 与垂直 VerticalJustification)
 * - 返回基于实际文本边界的角点
 *
 * 图片控件:
 * - 分析纹理 Alpha 通道以裁剪透明边缘
 * - 支持 Texture2D 与 PaperSprite 资源
 * - 根据可见像素边界缩放角点
 * - 过滤无背景或超出视口的控件
 *
 * 坐标系: Y 轴翻转 (ViewportSize.Y - PixelPos.Y)
 *
 * @return 4 个 JSON 角点坐标: [左下, 左上, 右上, 右下]
 */
TArray<TSharedPtr<FJsonValue>> URootObjWidget::GetCorners(
	UWidget* Widget, UWorld* WorldInstance, bool bIsText, FString Justification, FString VerticalJustification)
{
	// World 无效直接报错返回
	if (!WorldInstance)
	{
		UE_LOG(LogLQARestoreRootObj, Error, TEXT("[LQA] Get Invalid World!"));
		return TArray<TSharedPtr<FJsonValue>>();
	}

	// 获取视口尺寸
	FVector2D ViewportSize = FVector2D::ZeroVector;
	if (const UGameViewportClient* ViewportClient = WorldInstance->GetGameViewport())
	{
		ViewportClient->GetViewportSize(ViewportSize);
	}

	// 根据控件类型分别计算角点
	FVector2D LeftBottomPos, LeftUpperPos, RightUpperPos, RightBottomPos;
	bool bSuccess = false;

	if (bIsText)
	{
		// 文本: 先取控件左上角在视口中的像素位置
		const FGeometry& CanvasGeometry = Widget->GetCachedGeometry();
		FVector2D PixelPos, ViewportPos;
		USlateBlueprintLibrary::LocalToViewport(
			WorldInstance, CanvasGeometry, FVector2D::ZeroVector, PixelPos, ViewportPos);

		bSuccess = CalculateTextCorners(Widget, PixelPos, ViewportSize, Justification, VerticalJustification,
			LeftBottomPos, LeftUpperPos, RightUpperPos, RightBottomPos);
	}
	else
	{
		// 图片: 直接计算
		bSuccess = CalculateImageCorners(
			Widget, WorldInstance, ViewportSize, LeftBottomPos, LeftUpperPos, RightUpperPos, RightBottomPos);
	}

	// 计算失败返回空数组
	if (!bSuccess)
	{
		return TArray<TSharedPtr<FJsonValue>>();
	}

	// 转换为 JSON 数组返回
	return CornersToJsonArray(LeftBottomPos, LeftUpperPos, RightUpperPos, RightBottomPos);
}