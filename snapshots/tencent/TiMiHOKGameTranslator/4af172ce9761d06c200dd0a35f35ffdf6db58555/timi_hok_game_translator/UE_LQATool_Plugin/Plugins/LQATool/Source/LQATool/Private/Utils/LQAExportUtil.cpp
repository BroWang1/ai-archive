#include "Utils/LQAExportUtil.h"

// ---- 引擎与控件相关头文件 ----
#include "Components/CanvasPanel.h"           // 画布面板
#include "Components/CanvasPanelSlot.h"       // 画布面板插槽
#include "Components/Image.h"                 // 图片控件
#include "Engine/Engine.h"                    // GEngine 全局引擎对象
#include "Engine/GameViewportClient.h"        // 游戏视口客户端
#include "Engine/TextureRenderTarget2D.h"     // 2D 渲染目标纹理
#include "EngineUtils.h"
#include "Framework/Application/SlateApplication.h"  // Slate 应用 (窗口/输入管理)
#include "HighResScreenshot.h"                // 高分辨率截图
#include "ImageUtils.h"                        // 图像工具
#include "Internationalization/Internationalization.h"  // 国际化 (本地化)
#include "LQABase.h"
#include "LQAManager.h"
#include "RHICommandList.h"                    // 渲染硬件接口命令列表
#include "Engine/Texture2D.h"
#include "HAL/FileManager.h"
#include "Misc/PackageName.h"
#include "Misc/SecureHash.h"
#include "RHIResources.h"
#include "SceneView.h"
#include "Slate/SceneViewport.h"
#include "Slate/WidgetRenderer.h"
#include "Snapshot/LQAWidgetNode.h"            // LQA 控件节点定义
#include "Snapshot/LQAWidgetNodeUtil.h"        // LQA 控件节点工具
#include "Utils/LQACommonUtil.h"               // LQA 通用工具
#include "Utils/LQATextureUtil.h"              // LQA 纹理工具
#include "WidgetSlots/Slot2JsonFactory.h"      // 插槽转 JSON 工厂
#include "UObject/Package.h"
#include "UObject/UObjectGlobals.h"
#include "WidgetSlots/Slot2JsonInterface.h"
#include "WidgetSlots/Widget2JsonFactory.h"    // 控件转 JSON 工厂
#include "WidgetSlots/Widget2JsonInterface.h"
#include "Widgets/SViewport.h"
#include "Widgets/SWindow.h"

// Windows 平台专用头文件 (用于获取窗口句柄、坐标转换)
#if PLATFORM_WINDOWS
#include "Windows/AllowWindowsPlatformTypes.h"
#include <Windows.h>
#include "Windows/HideWindowsPlatformTypes.h"
#endif

// ========================================
// 静态成员与常量定义
// ========================================

// 静态成员变量在类外初始化 (默认空字符串)
FString FLQAExportUtil::ScreenshotPath = TEXT("");
FString FLQAExportUtil::BgScreenshotPath = TEXT("");

namespace LQAExportConstants
{
// 背景截图相对于前景截图的延迟秒数
constexpr float SCREENSHOT_DELAY_SECONDS = 1.2f;
// 控件包围盒的角点数量 (矩形为 4 个角)
constexpr int32 EXPECTED_CORNER_COUNT = 4;

// 所有被视为 “文本类” 的控件类型集合
const TArray<ELQAWidgetType> AllTextTypes = {ELQAWidgetType::LQA_TextBlock, ELQAWidgetType::LQA_RichText,
	ELQAWidgetType::LQA_EditableText, ELQAWidgetType::LQA_EditableTextBox, ELQAWidgetType::LQA_MultilineEditableText,
	ELQAWidgetType::LQA_MultilineEditableTextBox, ELQAWidgetType::LQA_TextScroller,
	ELQAWidgetType::LQA_ComboBoxStringText, ELQAWidgetType::LQA_LEDRichText, ELQAWidgetType::LQA_InputKeySelector};

// 需要被排除 (不导出) 的控件名称前缀, 通常为调试/工具类控件
const TArray<FString> ExcludedWidgetPrefixes = {
	TEXT("LQABaseView"),
	TEXT("Debugger_Widget"),
	TEXT("GM_Widget"),
};
}

// ========================================
// 辅助函数 (匿名命名空间, 仅本文件内可见)
// ========================================

namespace
{
/**
 * 判断控件名称是否包含被排除的前缀
 * @param TargetStr 待检查的控件名称
 * @return 若命中任意排除前缀则返回 true
 */
bool ContainsExcludedPrefix(const FString& TargetStr)
{
	for (const FString& Prefix : LQAExportConstants::ExcludedWidgetPrefixes)
	{
		if (TargetStr.Contains(Prefix))
		{
			return true;
		}
	}
	return false;
}

/**
 * 由当前控件名与父层级名构造 "父##子" 层级名
 * @param WidgetName 当前控件名, 会截去蓝图类名的 "_C_xxx" 后缀
 * @param ParentName 父层级名, 为 None 时表示当前控件已是顶层
 * @return 拼接后的层级名; 当前控件无名称时原样返回父层级名
 */
FName MakeChildParentName(const FName WidgetName, const FName ParentName)
{
	FName CleanName = WidgetName;

	// 去除蓝图类名中的 "_C_xxx" 后缀 (取左半部分作为纯净名称)
	FString Left, Right;
	CleanName.ToString().Split(TEXT("_C_"), &Left, &Right, ESearchCase::IgnoreCase, ESearchDir::FromEnd);
	if (!Left.IsEmpty())
	{
		CleanName = FName(*Left);
	}

	// 无名称的中间控件不参与层级拼接
	if (CleanName.IsNone())
	{
		return ParentName;
	}

	// 顶层控件直接使用自身名称
	if (ParentName.IsNone())
	{
		return CleanName;
	}

	return FName(*FString::Printf(TEXT("%s##%s"), *ParentName.ToString(), *CleanName.ToString()));
}

/**
 * 将屏幕点击坐标转换为视口 (Viewport) 坐标
 * 在 Windows 平台上会先把屏幕坐标转换为客户区坐标,
 * 最后再做 Y 轴翻转 (屏幕坐标原点在左上, 视口坐标原点在左下)
 */
FVector2D AdjustClickPositionForViewport(const FVector2D& ClickPosition)
{
	// 引擎或游戏视口无效时直接返回原始坐标
	if (!GEngine || !GEngine->GameViewport)
	{
		return ClickPosition;
	}

	FVector2D ViewportSize;
	GEngine->GameViewport->GetViewportSize(ViewportSize);
	FVector2D AdjustedPosition = ClickPosition;

#if PLATFORM_WINDOWS
	// 获取原生窗口句柄
	HWND WindowHandle = nullptr;
	if (GEngine->GameViewport)
	{
		void* WindowPtr = GEngine->GameViewport->GetWindow()->GetNativeWindow()->GetOSWindowHandle();
		WindowHandle = static_cast<HWND>(WindowPtr);
	}

	if (WindowHandle)
	{
		RECT ClientRect;
		// 获取窗口客户区矩形
		if (GetClientRect(WindowHandle, &ClientRect))
		{
			// 计算客户区左上角在屏幕中的坐标
			POINT ClientTopLeft = {0, 0};
			if (ClientToScreen(WindowHandle, &ClientTopLeft))
			{
				const FVector2D ClientScreenPos(ClientTopLeft.x, ClientTopLeft.y);
				// 屏幕坐标减去客户区左上角坐标, 得到相对视口坐标
				const FVector2D ViewportPosition = ClickPosition - ClientScreenPos;
				AdjustedPosition = ViewportPosition;
			}
		}
	}
#endif
	// Y 轴翻转: 将坐标系原点从左上角转换到左下角
	AdjustedPosition.Y = ViewportSize.Y - AdjustedPosition.Y;
	return AdjustedPosition;
}

/**
 * 判断某个点是否落在控件的包围盒范围内
 * @param Point   待判断的坐标点
 * @param Corners 控件四个角点的 JSON 数组
 * @return 若点在包围盒内返回 true
 */
bool IsPointInWidgetBounds(const FVector2D& Point, const TArray<TSharedPtr<FJsonValue>>& Corners)
{
	// 角点数量不符 (非矩形) 直接返回 false
	if (Corners.Num() != LQAExportConstants::EXPECTED_CORNER_COUNT)
	{
		return false;
	}

	// 读取左下、右下、左上三个角点坐标 (用于构造矩形范围判断)
	const FVector2D LeftBottom(
		Corners[0]->AsObject()->GetNumberField(TEXT("x")), Corners[0]->AsObject()->GetNumberField(TEXT("y")));
	const FVector2D RightBottom(
		Corners[3]->AsObject()->GetNumberField(TEXT("x")), Corners[3]->AsObject()->GetNumberField(TEXT("y")));
	const FVector2D LeftTop(
		Corners[1]->AsObject()->GetNumberField(TEXT("x")), Corners[1]->AsObject()->GetNumberField(TEXT("y")));

	// 判断点的 X 在左右范围内、Y 在上下范围内
	return Point.X >= LeftBottom.X && Point.X <= RightBottom.X && Point.Y >= LeftBottom.Y && Point.Y <= LeftTop.Y;
}

/**
 * 在屏幕上显示本地化 (Localization) 调试信息
 * @param TextStr    当前显示的文本
 * @param TextKey    文本的本地化 Key
 * @param TextSource 文本源字符串 (可选, 为空时显示简略信息)
 */
void DisplayLocalizationInfo(const FString& TextStr, const FString& TextKey, const FString& TextSource = TEXT(""))
{
	// 根据是否有源字符串, 组装不同详细程度的调试信息
	const FString DebugMessage =
		TextSource.IsEmpty()
			? FString::Printf(TEXT("localization: %s"), *TextStr)
			: FString::Printf(TEXT("localization: %s\nsourceText: %s\ntextKey: %s"), *TextStr, *TextSource, *TextKey);

	// 在屏幕上输出调试信息: 简略信息橙色显示 2 秒, 详细信息红色显示 8 秒
	GEngine->AddOnScreenDebugMessage(
		-1, TextSource.IsEmpty() ? 2.0f : 8.0f, TextSource.IsEmpty() ? FColor::Orange : FColor::Red, DebugMessage);
}

/**
 * 处理 “文本 Key 有效” 的场景: 尝试取出源字符串并显示本地化信息
 */
void HandleValidKeyScenario(
	const TSharedPtr<FJsonObject>& MatchedJsonObject, const FString& TextStr, const FString& TextKey)
{
	FString TextSource = TEXT("");
	if (MatchedJsonObject->HasField(TEXT("SourceString")))
	{
		TextSource = MatchedJsonObject->GetStringField(TEXT("SourceString"));
	}
	DisplayLocalizationInfo(TextStr, TextKey, TextSource);
}
}

// ========================================
// 公共接口 —— 主要导出函数
// ========================================

FString FLQAExportUtil::DumpViewAdvanced(const FDateTime& CurDate, bool bContainsTextures, bool bNeedObjectData)
{
	UE_LOG(LogLQATool, Log, TEXT("FLQAExportUtil::DumpView()"));
	// 记录开始时间 (毫秒), 用于统计耗时
	const double Start = FDateTime::Now().GetTimeOfDay().GetTotalMilliseconds();

	// 获取当前激活的顶层窗口
	const TSharedPtr<SWindow> ActiveWindow = FSlateApplication::Get().GetActiveTopLevelWindow();
	// 基于该窗口创建高级快照, 返回控件蓝图名称
	const FString WBPName = CreateSnapshotAdvanced(ActiveWindow, CurDate, bContainsTextures, bNeedObjectData);

	// 记录结束时间并输出总耗时
	const double End = FDateTime::Now().GetTimeOfDay().GetTotalMilliseconds();
	UE_LOG(LogLQATool, Log, TEXT("DumpView Takes: %f ms"), End - Start);

	return WBPName;
}

TArray<TSharedPtr<FJsonObject>> FLQAExportUtil::DumpText()
{
	TArray<TSharedPtr<FJsonObject>> AllTexts;
	// 获取当前激活窗口
	const TSharedPtr<SWindow> ActiveWindow = FSlateApplication::Get().GetActiveTopLevelWindow();
	if (!ActiveWindow.IsValid())
	{
		return AllTexts;  // 窗口无效则返回空数组
	}

	TSharedRef<SWindow> WidgetRef = ActiveWindow.ToSharedRef();
	int32 Index = 0;
	// 从窗口的几何信息构建控件节点树
	TSharedPtr<FLQAWidgetNode> NodeTree =
		FLQAWidgetNodeUtil::GetNodeFromTree(FArrangedWidget(WidgetRef, WidgetRef->GetWindowGeometryInScreen()), Index);

	// 递归收集所有文本节点
	GetAllTextNodes(NodeTree, AllTexts);

	return AllTexts;
}

void FLQAExportUtil::ScreenShot(const FDateTime& CurDate, const FString& WBPName)
{
	UE_LOG(LogLQATool, Log, TEXT("FLQAExportUtil::ScreenShot()"));
	const auto Start = FDateTime::Now().GetTimeOfDay().GetTotalMilliseconds();

	// 生成截图保存路径并启动截图流程
	const FString ScreenshotFilePath = GetScreenShotFileName(CurDate, WBPName);
	StartScreenshotSequence(ScreenshotFilePath);

	const auto End = FDateTime::Now().GetTimeOfDay().GetTotalMilliseconds();
	UE_LOG(LogLQATool, Log, TEXT("Screen Shot Takes: %f ms"), End - Start);
}

// ========================================
// 公共接口 —— 交互相关函数
// ========================================

void FLQAExportUtil::OnPointerDown(const FPointerEvent& MouseEvent)
{
	// 获取鼠标点击的屏幕坐标
	const FVector2D ScreenSpacePosition = MouseEvent.GetScreenSpacePosition();
	// 提取当前视图中的所有文本控件
	const TArray<TSharedPtr<FJsonObject>> AllTextWidgets = DumpText();

	// 查找点击位置命中的控件
	TArray<TSharedPtr<FJsonObject>> FoundWidgets;
	FindAllWidgetsContainingPoint(ScreenSpacePosition, AllTextWidgets, FoundWidgets);
}

bool FLQAExportUtil::FindAllWidgetsContainingPoint(const FVector2D& ClickPosition,
	const TArray<TSharedPtr<FJsonObject>>& TextWidgets, TArray<TSharedPtr<FJsonObject>>& OutWidgets)
{
	OutWidgets.Empty();

	// 校验游戏视口是否有效
	if (!GEngine || !GEngine->GameViewport)
	{
		UE_LOG(LogLQATool, Warning, TEXT("FindAllWidgetsContainingPoint: GameViewport is null"));
		return false;
	}

	// 校验世界 (World) 是否有效
	UWorld* World = GEngine->GetWorldContexts()[0].World();
	if (!World)
	{
		UE_LOG(LogLQATool, Warning, TEXT("FindAllWidgetsContainingPoint: World is null"));
		return false;
	}

	// 将屏幕点击坐标转换为视口坐标
	const FVector2D AdjustedClickPosition = AdjustClickPositionForViewport(ClickPosition);

	// 从后往前遍历 (后渲染的控件在上层, 优先命中) 查找匹配控件
	TSharedPtr<FJsonObject> MatchedJsonObject;
	for (int32 i = TextWidgets.Num() - 1; i >= 0; --i)
	{
		const TSharedPtr<FJsonObject>& JsonObject = TextWidgets[i];
		if (!JsonObject.IsValid())
		{
			continue;
		}

		// 读取控件角点并判断点击点是否在其范围内
		const TArray<TSharedPtr<FJsonValue>> Corners = JsonObject->GetArrayField(TEXT("corners"));
		if (IsPointInWidgetBounds(AdjustedClickPosition, Corners))
		{
			OutWidgets.Add(JsonObject);
			MatchedJsonObject = JsonObject;
			break;  // 命中最上层控件后即停止
		}
	}

	// 未命中、或缺少必要字段则返回 false
	if (!MatchedJsonObject.IsValid() || !MatchedJsonObject->HasField(TEXT("textStr")) ||
		!MatchedJsonObject->HasField(TEXT("TextKey")))
	{
		return false;
	}

	// 取出命中控件的文本内容与本地化 Key
	const FString TextStr = MatchedJsonObject->GetStringField(TEXT("textStr"));
	const FString TextKey = MatchedJsonObject->GetStringField(TEXT("TextKey"));

	// 显示基础本地化信息
	DisplayLocalizationInfo(TextStr, TextKey);

	// 根据 TextKey 是否有效走不同处理分支
	if (TextKey.Contains(TEXT("INVALIDKEY")))
	{
		// 无效 Key —— 无需额外处理, 仅记录日志
		UE_LOG(LogLQATool, Verbose, TEXT("Found invalid localization key for text: %s"), *TextStr);
	}
	else
	{
		// 有效 Key —— 进一步展示源字符串等信息
		HandleValidKeyScenario(MatchedJsonObject, TextStr, TextKey);
	}

	return OutWidgets.Num() > 0;
}

// ========================================
// 公共接口 —— 通用工具函数
// ========================================

FString FLQAExportUtil::GetCurrentCulture()
{
	// 通过国际化模块获取当前 Culture, 并返回其名称 (如 "zh-CN")
	const FCultureRef CurrentCultureRef = FInternationalization::Get().GetCurrentCulture();
	return CurrentCultureRef->GetName();
}

void FLQAExportUtil::AddSystemData(const TSharedPtr<FJsonObject>& JsonObject)
{
	// 获取设备信息与客户端版本号
	const FString DeviceInfo = FLQACommonUtil::GetSystemInfo();
	const FString Version = FLQACommonUtil::GetClientVersion();

	// 组装元数据对象
	const TSharedPtr<FJsonObject> NewObject = MakeShareable(new FJsonObject());
	NewObject->SetStringField(TEXT("version"), Version);
	NewObject->SetStringField(TEXT("device"), DeviceInfo);

	// 追加视口尺寸信息
	UGameViewportClient* GameViewportClient = GEngine->GameViewport;
	if (GameViewportClient)
	{
		const TSharedPtr<SViewport> ViewportWidget = GameViewportClient->GetGameViewportWidget();
		const FVector2D ViewportSize = GameViewportClient->GetGameViewport()->GetSizeXY();
		NewObject->SetNumberField(TEXT("sizeX"), ViewportSize.X);
		NewObject->SetNumberField(TEXT("sizeY"), ViewportSize.Y);
	}

	// 将元数据挂载到 "meta" 字段下
	JsonObject->SetObjectField(TEXT("meta"), NewObject);
}

bool FLQAExportUtil::SaveSnapshotData(const FString& InJsonData, const FString& WBPName, const FDateTime& CurDate)
{
	// 空数据不保存
	if (InJsonData.IsEmpty())
	{
		return false;
	}

	// 以时间戳 + 蓝图名拼接目录与文件名
	const FString CurTime = CurDate.ToString(TEXT("%Y_%m_%d_%H_%M_%S"));
	const FString JsonFileName = FString::Printf(TEXT("LQA_Snapshot_%s_%s.json"), *WBPName, *CurTime);
	const FString JsonFilePath = FPaths::Combine(GetSnapshotDirectory(CurDate, WBPName), *JsonFileName);

	// 以 UTF-8 (无 BOM) 编码保存字符串到文件
	return FFileHelper::SaveStringToFile(InJsonData, *JsonFilePath, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

// ========================================
// 私有 —— 核心快照函数
// ========================================

FString FLQAExportUtil::GetSnapshotDirectory(const FDateTime& CurDate, const FString& WBPName)
{
	const FString CurTime = CurDate.ToString(TEXT("%Y_%m_%d_%H_%M_%S"));
	return FPaths::Combine(
		*FLQACommonUtil::GetGameSavedPath(), TEXT("LQA"), *FString::Printf(TEXT("%s_%s"), *CurTime, *WBPName));
}

FString FLQAExportUtil::CreateSnapshotAdvanced(
	const TSharedPtr<SWindow>& VisibleWindow, const FDateTime& CurDate, bool bContainsTextures, bool bNeedObjectData)
{
	// 窗口无效直接返回空
	if (!VisibleWindow.IsValid())
	{
		UE_LOG(LogLQATool, Error,
			TEXT("CreateSnapshotAdvanced aborted: no valid top-level window to capture. "
				 "This usually means the game/viewport window was not focused when the dump was triggered."));
		return TEXT("");
	}

	TSharedRef<SWindow> WidgetRef = VisibleWindow.ToSharedRef();
	int32 Index = 0;
	// 构建控件节点树
	TSharedPtr<FLQAWidgetNode> NodeTree =
		FLQAWidgetNodeUtil::GetNodeFromTree(FArrangedWidget(WidgetRef, WidgetRef->GetWindowGeometryInScreen()), Index);

	// 收集所有有效节点 (UserWidget 且未被排除)
	TArray<TSharedPtr<FLQAWidgetNode>> ValidNodes;
	GetAllValidNodes(NodeTree, ValidNodes);

	// UI 树 JSON 数组、纹理缓存、名称列表
	TArray<TSharedPtr<FJsonValue>> UITrees;
	TMap<FString, UTexture*> SharedTextureMap;
	TArray<FName> NameList;

	const TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject());

	// 逐个有效节点序列化为 JSON 并加入 UI 树数组
	for (const auto& Node : ValidNodes)
	{
		TSharedPtr<FJsonObject> TreeObject = DumpNodeInfo(Node, SharedTextureMap, NameList, bNeedObjectData);
		if (TreeObject.IsValid())
		{
			UITrees.Add(MakeShareable(new FJsonValueObject(TreeObject)));
		}
	}

	// 将 UI 树挂到 "uitree" 字段
	JsonObject->SetArrayField(TEXT("uitree"), UITrees);

	// 追加系统元数据, 并解析控件蓝图名称
	AddSystemData(JsonObject);
	FString WBPName = FindWBPName(NameList);

	// 将 JSON 对象序列化为字符串
	FString OutString;
	const TSharedRef<TJsonWriter<>> JsonWriter = TJsonWriterFactory<>::Create(&OutString);
	FJsonSerializer::Serialize(JsonObject.ToSharedRef(), JsonWriter);

	// 保存到磁盘, 失败则输出错误日志
	if (!SaveSnapshotData(OutString, WBPName, CurDate))
	{
		UE_LOG(LogLQATool, Error, TEXT("Save Snapshot Data Failed!"));
	}
	if (bContainsTextures)
	{
		ExportSharedTextures(SharedTextureMap, CurDate, WBPName);
	}

	return WBPName;
}

bool FLQAExportUtil::IsRuntimeGeneratedTexture(const UTexture2D* Texture2D)
{
	if (!Texture2D)
	{
		return false;
	}

	// Objects living in the transient package have no footprint on disk
	const UPackage* Package = Texture2D->GetOutermost();
	if (!Package || Package == GetTransientPackage())
	{
		return true;
	}

	// Packages created this session that were never saved also have no file to load back
	if (Package->HasAnyPackageFlags(PKG_NewlyCreated))
	{
		return true;
	}

	return !FPackageName::DoesPackageExist(Package->GetName());
}

void FLQAExportUtil::ExportSharedTextures(
	const TMap<FString, UTexture*>& SharedTextureMap, const FDateTime& CurDate, const FString& WBPName)
{
	if (SharedTextureMap.Num() == 0)
	{
		return;
	}

	const FString TextureDirectory = FPaths::Combine(GetSnapshotDirectory(CurDate, WBPName), TEXT("Textures"));
	bool bTextureDirectoryReady = false;

	int32 ExportedCount = 0;
	int32 SkippedAssetCount = 0;
	for (const TPair<FString, UTexture*>& Pair : SharedTextureMap)
	{
		UTexture2D* Texture2D = IsValid(Pair.Value) ? Cast<UTexture2D>(Pair.Value) : nullptr;
		if (!Texture2D)
		{
			continue;
		}

		if (!IsRuntimeGeneratedTexture(Texture2D))
		{
			++SkippedAssetCount;
			continue;
		}

		TArray<uint8> PngData;
		if (!FLQATextureUtil::GetTexture2DData(Texture2D, PngData))
		{
			UE_LOG(LogLQATool, Warning, TEXT("Failed to export texture pixels: %s"), *Pair.Key);
			continue;
		}

		if (!bTextureDirectoryReady)
		{
			IFileManager::Get().MakeDirectory(*TextureDirectory, true);
			bTextureDirectoryReady = true;
		}

		const FString FileName = FMD5::HashAnsiString(*Pair.Key) + TEXT(".png");
		if (FFileHelper::SaveArrayToFile(PngData, *FPaths::Combine(TextureDirectory, FileName)))
		{
			++ExportedCount;
		}
	}

	UE_LOG(LogLQATool, Log,
		TEXT("Exported %d shared texture(s) to %s (%d disk-backed asset(s) skipped, %d total)"),
		ExportedCount, *TextureDirectory, SkippedAssetCount, SharedTextureMap.Num());
}

FString FLQAExportUtil::FindWBPName(TArray<FName>& NameList)
{
	// 默认名称
	FString Name = TEXT("None");
	if (NameList.Num() > 0)
	{
		Name = NameList[0].ToString();
	}
	// 名称中包含 "##" 分隔符时, 解析出真正的蓝图名
	if (Name.Contains(TEXT("##")))
	{
		FString Left, Right;
		// 第一次从头部按 "##" 切分, 取右半部分
		Name.Split(TEXT("##"), &Left, &Right, ESearchCase::IgnoreCase, ESearchDir::FromStart);
		Name = Right;
		if (Right.Contains(TEXT("##")))
		{
			// 右半部分仍含 "##" 时, 再次切分取左半部分
			Name.Split(TEXT("##"), &Left, &Right, ESearchCase::IgnoreCase, ESearchDir::FromStart);
			Name = Left;
		}
	}
	return Name;
}

// ========================================
// 私有 —— 控件树遍历处理
// ========================================

void FLQAExportUtil::GetAllValidNodes(
	const TSharedPtr<FLQAWidgetNode>& Node, TArray<TSharedPtr<FLQAWidgetNode>>& OutValidNodes)
{
	if (!Node.IsValid())
	{
		return;
	}

	const ELQAWidgetType NodeType = Node->GetNodeType();
	// 遇到 UserWidget 类型即作为一个 “有效根节点” 收集 (不再深入其内部)
	if (NodeType == ELQAWidgetType::LQA_UserWidget)
	{
		// 若命中排除前缀则跳过
		if (ContainsExcludedPrefix(Node->WidgetName.ToString()))
		{
			return;
		}
		OutValidNodes.Add(Node);
		return;
	}

	// 非 UserWidget 则递归处理其子节点
	for (const auto& Child : Node->GetChildNodes())
	{
		GetAllValidNodes(Child, OutValidNodes);
	}
}

void FLQAExportUtil::GetAllTextNodes(
	const TSharedPtr<FLQAWidgetNode>& Node, TArray<TSharedPtr<FJsonObject>>& OutValidTextNodes)
{
	if (!Node.IsValid())
	{
		return;
	}

	// 若当前节点属于文本类型, 则序列化为 JSON 并收集
	if (LQAExportConstants::AllTextTypes.Contains(Node->GetNodeType()))
	{
		TMap<FString, UTexture*> EmptyTextureMap;  // 文本节点无需纹理数据, 传入空映射
		const TSharedPtr<FJsonObject> TextNodeJson = FWidget2JsonFactory::Widget2Json(Node, EmptyTextureMap, false);
		if (TextNodeJson.IsValid())
		{
			OutValidTextNodes.Add(TextNodeJson);
		}
		return;
	}

	// 非文本节点则递归处理其子节点
	for (const auto& Child : Node->GetChildNodes())
	{
		GetAllTextNodes(Child, OutValidTextNodes);
	}
}

// ========================================
// 私有 —— 节点序列化
// ========================================

TSharedPtr<FJsonObject> FLQAExportUtil::DumpNodeInfo(const TSharedPtr<FLQAWidgetNode>& Node,
	TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData, const FName ParentName)
{
	if (!Node.IsValid())
	{
		return nullptr;
	}

	TSharedPtr<FJsonObject> NodeJson;
	const ELQAWidgetType NodeType = Node->GetNodeType();

	// 根据节点类型分发到不同的处理函数
	if (NodeType == ELQAWidgetType::LQA_UserWidget)
	{
		NodeJson = HandleUserWidget(Node, SharedTextureMap, NameList, bNeedObjectData, ParentName);
	}
	else if (NodeType == ELQAWidgetType::LQA_Undefined)
	{
		NodeJson = HandleUndefinedWidget(Node, SharedTextureMap, NameList, bNeedObjectData, ParentName);
	}
	else
	{
		NodeJson = HandleOtherWidget(Node, SharedTextureMap, NameList, bNeedObjectData, ParentName);
	}

	return NodeJson.IsValid() ? NodeJson : nullptr;
}

TSharedPtr<FJsonObject> FLQAExportUtil::HandleUserWidget(const TSharedPtr<FLQAWidgetNode>& Node,
	TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData, const FName ParentName)
{
	// 以当前控件名作为子节点的父名称
	const FName ChildParentName = MakeChildParentName(Node->WidgetName, ParentName);

	// 序列化控件本身与其插槽 (Slot) 信息
	const TSharedPtr<FJsonObject> NewObject = FWidget2JsonFactory::Widget2Json(Node, SharedTextureMap, bNeedObjectData);
	const TSharedPtr<FJsonObject> NewSlotObject = FSlot2JsonFactory::Slot2Json(Node);

	// 记录父控件名称
	NewObject->SetStringField(TEXT("ParentWidget"), ChildParentName.ToString());

	// 若有有效插槽信息则写入 Slot / SlotType, 否则记录被排除的插槽类型
	if (NewSlotObject->Values.Num() > 0)
	{
		if (NewSlotObject->HasField(TEXT("Slot")))
		{
			NewObject->SetObjectField(TEXT("Slot"), NewSlotObject->GetObjectField(TEXT("Slot")));
		}
		if (NewSlotObject->HasField(TEXT("SlotType")))
		{
			NewObject->SetStringField(TEXT("SlotType"), NewSlotObject->GetStringField(TEXT("SlotType")));
		}
	}
	else
	{
		NewObject->SetStringField(TEXT("ExcludedSlotType"), Node->BaseSlotType);
	}

	// 递归处理子节点
	ProcessChildNodes(Node, NewObject, SharedTextureMap, NameList, bNeedObjectData, ChildParentName);
	return NewObject;
}

TSharedPtr<FJsonObject> FLQAExportUtil::HandleUndefinedWidget(const TSharedPtr<FLQAWidgetNode>& Node,
	TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData, const FName ParentName)
{
	// 以当前控件名作为子节点的父名称
	const FName ChildParentName = MakeChildParentName(Node->WidgetName, ParentName);

	// 对未定义类型控件做专门的序列化
	TSharedPtr<FJsonObject> NewObject = FWidget2JsonFactory::UndefineWidget2Json(Node);

	// 记录父控件名称
	if (!ChildParentName.IsNone())
	{
		NewObject->SetStringField(TEXT("ParentWidget"), ChildParentName.ToString());
	}

	// 先递归处理子节点
	ProcessChildNodes(Node, NewObject, SharedTextureMap, NameList, bNeedObjectData, ChildParentName);

	// 若没有任何子节点, 则该未定义节点无意义, 返回空
	if (NewObject->GetArrayField(TEXT("ChildNodes")).Num() == 0)
	{
		return nullptr;
	}

	// 写入插槽信息 (同上逻辑)
	const TSharedPtr<FJsonObject> NewSlotObject = FSlot2JsonFactory::Slot2Json(Node);
	if (NewSlotObject->Values.Num() > 0)
	{
		if (NewSlotObject->HasField(TEXT("Slot")))
		{
			NewObject->SetObjectField(TEXT("Slot"), NewSlotObject->GetObjectField(TEXT("Slot")));
		}
		if (NewSlotObject->HasField(TEXT("SlotType")))
		{
			NewObject->SetStringField(TEXT("SlotType"), NewSlotObject->GetStringField(TEXT("SlotType")));
		}
	}
	else
	{
		NewObject->SetStringField(TEXT("ExcludedSlotType"), Node->BaseSlotType);
	}

	return NewObject;
}

TSharedPtr<FJsonObject> FLQAExportUtil::HandleOtherWidget(const TSharedPtr<FLQAWidgetNode>& Node,
	TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData, const FName ParentName)
{
	// 序列化普通控件与其插槽
	const TSharedPtr<FJsonObject> NewObject = FWidget2JsonFactory::Widget2Json(Node, SharedTextureMap, bNeedObjectData);
	const TSharedPtr<FJsonObject> NewSlotObject = FSlot2JsonFactory::Slot2Json(Node);

	// 记录父控件名称, 并将其加入名称列表 (用于后续解析蓝图名)
	if (!ParentName.IsNone())
	{
		NewObject->SetStringField(TEXT("ParentWidget"), ParentName.ToString());
		NameList.Emplace(ParentName);
	}
	
	// 写入插槽信息
	if (NewSlotObject->Values.Num() > 0)
	{
		NewObject->SetObjectField(TEXT("Slot"), NewSlotObject->GetObjectField(TEXT("Slot")));
		NewObject->SetStringField(TEXT("SlotType"), NewSlotObject->GetStringField(TEXT("SlotType")));
	}
	else
	{
		NewObject->SetStringField(TEXT("ExcludedSlotType"), Node->BaseSlotType);
	}

	// 递归处理子节点
	ProcessChildNodes(Node, NewObject, SharedTextureMap, NameList, bNeedObjectData, ParentName);
	return NewObject;
}

void FLQAExportUtil::ProcessChildNodes(const TSharedPtr<FLQAWidgetNode>& Node,
	const TSharedPtr<FJsonObject>& ParentJsonObject, TMap<FString, UTexture*>& SharedTextureMap,
	TArray<FName>& NameList, bool bNeedObjectData, const FName ParentName)
{
	TArray<TSharedPtr<FJsonValue>> ChildNodesJson;

	// 遍历所有子节点并递归序列化
	for (const auto& Child : Node->GetChildNodes())
	{
		TSharedPtr<FJsonObject> ChildJson =
			DumpNodeInfo(Child, SharedTextureMap, NameList, bNeedObjectData, ParentName);
		if (ChildJson.IsValid())
		{
			if (!Child->SlotName.IsNone())
			{
				ChildJson->SetStringField(TEXT("SlotName"), Child->SlotName.ToString());
			}
			ChildNodesJson.Add(MakeShareable(new FJsonValueObject(ChildJson)));
		}
	}

	// 将子节点数组写入父对象的 "ChildNodes" 字段
	ParentJsonObject->SetArrayField(TEXT("ChildNodes"), ChildNodesJson);
}

// ========================================
// 私有 —— 截图相关函数
// ========================================

FString FLQAExportUtil::GetScreenShotFileName(const FDateTime& CurDate, const FString& WBPName)
{
	// 以时间戳 + 蓝图名拼接截图目录与 PNG 文件名
	const FString CurTime = CurDate.ToString(TEXT("%Y_%m_%d_%H_%M_%S"));
	return FPaths::Combine(
		GetSnapshotDirectory(CurDate, WBPName), *FString::Printf(TEXT("LQA_ScreenShot_%s_%s.png"), *WBPName, *CurTime));
}

void FLQAExportUtil::StartScreenshotSequence(const FString& InScreenshotPath)
{
	// 记录前景截图路径
	ScreenshotPath = InScreenshotPath;
	// 基于前景路径推导背景截图路径 (追加 "_BG" 后缀)
	const FString Dir = FPaths::GetPath(InScreenshotPath);
	const FString BaseName = FPaths::GetBaseFilename(InScreenshotPath, true);
	BgScreenshotPath = FPaths::Combine(Dir, BaseName + TEXT("_BG.png"));

	// 先请求前景截图 (包含 UI)
	FScreenshotRequest::RequestScreenshot(ScreenshotPath, true, false);

	// 延迟一段时间后再请求背景截图 (不含 UI), 用于对比/抠图
	FTimerHandle TimerHandle;
	GWorld->GetTimerManager().SetTimer(
		TimerHandle, []() { FScreenshotRequest::RequestScreenshot(BgScreenshotPath, false, false); },
		LQAExportConstants::SCREENSHOT_DELAY_SECONDS, false);
}