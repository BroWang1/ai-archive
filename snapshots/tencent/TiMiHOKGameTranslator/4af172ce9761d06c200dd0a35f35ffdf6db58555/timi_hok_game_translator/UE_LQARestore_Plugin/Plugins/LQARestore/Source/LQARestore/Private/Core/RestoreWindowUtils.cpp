#include "Core/RestoreWindowUtils.h"

#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "Core/RestoreWindowProxy.h"
#include "Core/LQARestoreManager.h"
#include "CoreMinimal.h"
#include "Engine/Engine.h"
#include "Engine/Texture2D.h"
#include "Engine/Texture2DDynamic.h"
#include "IImageWrapper.h"
#include "IImageWrapperModule.h"
#include "ImageUtils.h"
#include "Json.h"
#include "JsonObjectConverter.h"
#include "Kismet/KismetRenderingLibrary.h"
#include "Materials/MaterialInstanceConstant.h"
#include "Materials/MaterialInstanceDynamic.h"
#include "Materials/MaterialInterface.h"
#include "Math/Color.h"
#include "Modules/ModuleManager.h"
#include "Slate/WidgetRenderer.h"
#include "Utils/JsonUtils.h"
#include "Utils/SlateBrushUtils.h"
#include "Utils/TextureUtils.h"
#include "Utils/TranslationUtils/LoaderUtils.h"
#if WITH_EDITOR
#include "Factories/TextureFactory.h"
#endif
#include "WidgetSlots/Core/RestoreWidget2JsonFactory.h"
#include "WidgetSlots/Core/WidgetDefines.h"
#include "WidgetTree/LQAWidgetNode.h"

// ============================================================================
// 匿名命名空间 —— 常量定义
// 使用匿名命名空间使常量仅在本翻译单元 (本 .cpp) 内可见, 避免符号污染
// ============================================================================

namespace
{
// 顶层父控件检测所用的 Layer (层级) 阈值
// 层级值小于该阈值的控件才会被视为 “顶层” 候选
constexpr int32 TopParentLayerThreshold = 10000;
}

// ============================================================================
// 静态成员初始化
// ============================================================================

// 还原窗口销毁委托的定义
FOnRestoreWindowDestroyed FRestoreWindowUtils::OnRestoreWindowDestroyed;
// 校验用父控件列表的定义
TArray<FString> FRestoreWindowUtils::AllCheckParentWidgets;

// 纯文本控件类型集合: 包含各类文本块、可编辑文本框等, 不含图片
const TArray<FName> FRestoreWindowUtils::PureTextWidgetTypes = {LQAWidgetNames::LQA_TextBlock,
	LQAWidgetNames::LQA_RichTextBlock, LQAWidgetNames::LQA_EditableText, LQAWidgetNames::LQA_EditableTextBox,
	LQAWidgetNames::LQA_MultilineEditableText, LQAWidgetNames::LQA_MultilineEditableTextBox,
	LQAWidgetNames::LQA_LEDRichTextBlock};

// 文本与图片控件类型集合: 在纯文本类型基础上额外包含 Image 图片控件
const TArray<FName> FRestoreWindowUtils::TextAndImageWidgetTypes = {LQAWidgetNames::LQA_TextBlock,
	LQAWidgetNames::LQA_RichTextBlock, LQAWidgetNames::LQA_EditableText, LQAWidgetNames::LQA_EditableTextBox,
	LQAWidgetNames::LQA_MultilineEditableText, LQAWidgetNames::LQA_MultilineEditableTextBox,
	LQAWidgetNames::LQA_LEDRichTextBlock, LQAWidgetNames::LQA_Image};

// ============================================================================
// 窗口创建与构建
// ============================================================================

bool FRestoreWindowUtils::CreateWindow(const FString& DumpFilePath, URestoreWindowProxy* WindowProxy)
{
	// 校验 dump 文件是否存在, 不存在则记录错误并返回失败
	if (!FPaths::FileExists(DumpFilePath))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Target Dump File Not Found! Path: %s"), *DumpFilePath);
		return false;
	}

	// 将 dump 文件内容整体读取为字符串
	FString JsonStr;
	FFileHelper::LoadFileToString(JsonStr, *DumpFilePath);

	// 创建 JSON 对象并进行反序列化
	TSharedPtr<FJsonObject> RootObj = MakeShareable(new FJsonObject());
	const TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonStr);
	if (!FJsonSerializer::Deserialize(JsonReader, RootObj))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Deserialize Dump File Failed! Path: %s"), *DumpFilePath);
		return false;
	}

	// 从 JSON 中解析出窗口尺寸
	FVector2D WindowSize;
	if (!DeserializeWindowSize(RootObj, WindowSize))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Deserialize Window Size Failed! Path: %s"), *DumpFilePath);
		return false;
	}

	// 使用解析得到的尺寸创建窗口
	WindowProxy->CreateWindow(WindowSize);
	return true;
}

bool FRestoreWindowUtils::BuildWindow(
	const FString& DumpFilePath, URestoreWindowProxy* WindowProxy, TSharedPtr<FJsonObject> BaseUIDataObj)
{
	// 校验 dump 文件是否存在
	if (!FPaths::FileExists(DumpFilePath))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Target Dump File Not Found! Path: %s"), *DumpFilePath);
		return false;
	}

	// 读取 dump 文件内容
	FString JsonStr;
	if (!FFileHelper::LoadFileToString(JsonStr, *DumpFilePath))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to load dump file! Path: %s"), *DumpFilePath);
		return false;
	}

	TSharedPtr<FJsonObject> RootObj;                  // 最终用于构建 UI 的根 JSON 对象
	FString ObjectParentWidget = TEXT("");            // 需要重点校验的父控件名称
	FVector2D WindowSize;                             // 窗口尺寸
	// 判断是否传入了有效的基础 UI 数据
	const bool bHasBaseData = BaseUIDataObj.IsValid() && BaseUIDataObj->Values.Num() > 0;

	// 模式一: 将 dump 中的组件配置合并到基础 UI 数据中
	if (bHasBaseData)
	{
		// 解析 dump 文件以获取组件配置
		TSharedPtr<FJsonObject> DumpObj = MakeShareable(new FJsonObject());
		TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonStr);
		if (!FJsonSerializer::Deserialize(JsonReader, DumpObj))
		{
			UE_LOG(
				LogTemp, Error, TEXT("Failed to deserialize dump file for component config! Path: %s"), *DumpFilePath);
			return false;
		}

		// 提前校验窗口尺寸 (快速失败, 避免后续无谓处理)
		if (!DeserializeWindowSize(DumpObj, WindowSize))
		{
			UE_LOG(LogLQARestoreManager, Error, TEXT("Deserialize Window Size Failed! Path: %s"), *DumpFilePath);
			return false;
		}

		// 提取组件配置字段 componentConfig
		const TSharedPtr<FJsonValue> ComponentConfig = DumpObj->TryGetField(TEXT("componentConfig"));
		if (!ComponentConfig.IsValid() || ComponentConfig->Type != EJson::Object)
		{
			// 未找到组件配置时, 退化为直接加载模式
			UE_LOG(LogLQARestoreManager, Warning, TEXT("Component config not found, fallback to direct load"));
		}
		else
		{
			// 从组件配置中读取匹配与替换所需的字段
			const TSharedPtr<FJsonObject> ConfigObj = ComponentConfig->AsObject();
			const FString ParentWidget = ConfigObj->GetStringField(TEXT("parentWidget"));  // 目标父控件
			const FString WidgetName = ConfigObj->GetStringField(TEXT("widgetName"));       // 目标控件
			const FString ReplaceText = ConfigObj->GetStringField(TEXT("replaceText"));     // 替换文本
			const FString ReplaceKey = ConfigObj->GetStringField(TEXT("replaceKey"));       // 替换文本 Key

			UE_LOG(LogLQARestoreManager, Display, TEXT("Component Config - Parent: %s, Widget: %s, Text: %s"), *ParentWidget,
				*WidgetName, *ReplaceText);

			// 将替换应用到基础 UI 数据的 uitree 数组中
			const TArray<TSharedPtr<FJsonValue>>* UITrees;
			if (BaseUIDataObj->TryGetArrayField(TEXT("uitree"), UITrees))
			{
				for (const TSharedPtr<FJsonValue>& TreeValue : *UITrees)
				{
					if (TreeValue.IsValid() && TreeValue->Type == EJson::Object)
					{
						// 在该树中递归查找并替换, 成功后记录父控件并跳出循环
						if (ReplaceBaseData(TreeValue->AsObject(), ParentWidget, WidgetName, ReplaceText, ReplaceKey))
						{
							ObjectParentWidget = ParentWidget;
							break;
						}
					}
				}
			}
		}
		// 以基础 UI 数据作为最终构建数据源
		RootObj = BaseUIDataObj;
	}
	// 模式二: 直接从 dump 文件加载数据
	else
	{
		RootObj = MakeShareable(new FJsonObject());
		TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonStr);
		if (!FJsonSerializer::Deserialize(JsonReader, RootObj))
		{
			UE_LOG(LogLQARestoreManager, Error, TEXT("Deserialize Dump File Failed! Path: %s"), *DumpFilePath);
			return false;
		}

		// 提前校验窗口尺寸 (快速失败)
		if (!DeserializeWindowSize(RootObj, WindowSize))
		{
			UE_LOG(LogLQARestoreManager, Error, TEXT("Deserialize Window Size Failed! Path: %s"), *DumpFilePath);
			return false;
		}
	}

	// 使用解析得到的窗口尺寸正式构建 UI
	UE_LOG(LogLQARestoreManager, Display, TEXT("Deserialize Success! Size: %.0fx%.0f, Path: %s"), WindowSize.X, WindowSize.Y,
		*DumpFilePath);
	DeserializeData(RootObj, WindowProxy, WindowSize, WindowProxy, ObjectParentWidget);
	return true;
}

bool FRestoreWindowUtils::DeserializeWindowSize(const TSharedPtr<FJsonObject>& RootObj, FVector2D& OutSize)
{
	TSharedPtr<FJsonObject> MetaData;

	// 兼容两种元数据字段命名: 优先 gameData, 其次 meta
	if (RootObj->HasField(TEXT("gameData")))
	{
		MetaData = RootObj->GetObjectField(TEXT("gameData"));
	}
	else if (RootObj->HasField(TEXT("meta")))
	{
		MetaData = RootObj->GetObjectField(TEXT("meta"));
	}
	else
	{
		// 两种字段都不存在, 视为失败
		UE_LOG(LogLQARestoreManager, Error, TEXT("Find Meta Data Failed!"));
		return false;
	}

	// 从元数据中读取 sizeX / sizeY 作为窗口宽高
	if (MetaData->HasField(TEXT("sizeX")) && MetaData->HasField(TEXT("sizeY")))
	{
		OutSize.X = MetaData->GetNumberField(TEXT("sizeX"));
		OutSize.Y = MetaData->GetNumberField(TEXT("sizeY"));
		return true;
	}

	UE_LOG(LogLQARestoreManager, Error, TEXT("Deserialize Window Size Failed!"));
	return false;
}

bool FRestoreWindowUtils::ReplaceBaseData(const TSharedPtr<FJsonObject>& Node, const FString& MatchParentWidget,
	const FString& MatchWidgetName, const FString& ReplaceText, const FString& ReplaceKey)
{
	// 节点无效直接返回, 防止空指针访问
	if (!Node.IsValid())
	{
		return false;
	}

	// 读取当前节点的父控件名与控件名, 用于匹配判断
	const FString ParentWidget = Node->GetStringField(TEXT("ParentWidget"));
	const FString WidgetName = Node->GetStringField(TEXT("WidgetName"));

	// 当前节点与目标控件匹配, 执行文本替换
	if (ParentWidget == MatchParentWidget && WidgetName == MatchWidgetName)
	{
		// 替换节点上的文本相关字段
		Node->SetStringField(TEXT("TextKey"), ReplaceKey);
		Node->SetStringField(TEXT("SourceString"), ReplaceText);
		Node->SetStringField(TEXT("textStr"), ReplaceText);

		// 若存在 ObjectData 子对象, 也需替换其中的文本字段
		if (Node->HasField(TEXT("ObjectData")))
		{
			TSharedPtr<FJsonObject> ObjectData = Node->GetObjectField(TEXT("ObjectData"));
			if (ObjectData.IsValid())
			{
				// 兼容多种命名方式的文本字段, 找到第一个即替换并退出
				static const TArray<FString> TextFieldNames = {
					TEXT("Text"), TEXT("text"), TEXT("HintText"), TEXT("hintText")};

				for (const FString& FieldName : TextFieldNames)
				{
					if (ObjectData->HasField(FieldName))
					{
						ObjectData->SetStringField(FieldName, ReplaceText);
						break;
					}
				}
			}
		}
		return true;
	}

	// 当前节点不匹配, 则递归搜索其子节点 ChildNodes
	const TArray<TSharedPtr<FJsonValue>>* ChildNodes;
	if (Node->TryGetArrayField(TEXT("ChildNodes"), ChildNodes))
	{
		for (const TSharedPtr<FJsonValue>& ChildValue : *ChildNodes)
		{
			if (ChildValue.IsValid() && ChildValue->Type == EJson::Object)
			{
				// 任一子节点替换成功即可向上返回 true
				if (ReplaceBaseData(
						ChildValue->AsObject(), MatchParentWidget, MatchWidgetName, ReplaceText, ReplaceKey))
				{
					return true;
				}
			}
		}
	}

	// 整棵子树均未匹配
	return false;
}

// ============================================================================
// 控件类型检测
// ============================================================================

bool FRestoreWindowUtils::ContainsWidgetType(const TSharedPtr<FJsonObject>& JsonObject, const TArray<FName>& TypeList)
{
	// 节点无效直接返回
	if (!JsonObject.IsValid())
	{
		return false;
	}

	// 检查当前节点的 WidgetType 是否在给定类型列表中
	FString WidgetType;
	if (JsonObject->TryGetStringField(TEXT("WidgetType"), WidgetType))
	{
		if (TypeList.Contains(FName(*WidgetType)))
		{
			return true;
		}
	}

	// 递归检查所有子节点
	const TArray<TSharedPtr<FJsonValue>>* ChildNodes;
	if (JsonObject->TryGetArrayField(TEXT("ChildNodes"), ChildNodes))
	{
		for (const TSharedPtr<FJsonValue>& ChildValue : *ChildNodes)
		{
			if (ChildValue.IsValid() && ChildValue->Type == EJson::Object)
			{
				if (ContainsWidgetType(ChildValue->AsObject(), TypeList))
				{
					return true;
				}
			}
		}
	}

	return false;
}

bool FRestoreWindowUtils::ContainsDisplayableWidget(const TSharedPtr<FJsonObject>& JsonObject)
{
	// 复用通用检测, 判断是否包含文本或图片控件
	return ContainsWidgetType(JsonObject, TextAndImageWidgetTypes);
}

bool FRestoreWindowUtils::ContainsOnlyTextWidget(const TSharedPtr<FJsonObject>& JsonObject)
{
	// 复用通用检测, 判断是否包含纯文本控件
	return ContainsWidgetType(JsonObject, PureTextWidgetTypes);
}

// ============================================================================
// 校验与导出
// ============================================================================

void FRestoreWindowUtils::GenerateCheckJson(URestoreWindowProxy* WindowProxy, const FString& ResultDirPath)
{
	// 窗口代理为空时无法生成, 记录错误并返回
	if (!WindowProxy)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("GenerateCheckJson: WindowProxy is null"));
		return;
	}

	// 组合输出文件路径并生成校验角点信息
	FString CheckInfoFilePath = FPaths::Combine(ResultDirPath, TEXT("check_info.json"));
	WindowProxy->GenerateCheckCorners(CheckInfoFilePath, AllCheckParentWidgets);
}

// ============================================================================
// 私有辅助函数
// ============================================================================

void FRestoreWindowUtils::DeserializeData(const TSharedPtr<FJsonObject>& RootObj, URestoreWindowProxy* WindowProxy,
	const FVector2D& InWindowSize, URestoreWindowProxy* RestoreWindowProxy, const FString& ObjectParentWidget)
{
	// 取出 UI 树数组, 每个元素代表一棵控件树
	const TArray<TSharedPtr<FJsonValue>> UITrees = RootObj->GetArrayField(TEXT("uitree"));

	// 过滤与处理 UI 树节点
	TArray<TSharedPtr<FJsonValue>> ValidUITrees;   // 有效的 UI 树集合
	FString TopParentWidget;                        // 检测到的顶层父控件

	ValidUITrees.Reserve(UITrees.Num());  // 预分配内存, 减少动态扩容开销

	for (const TSharedPtr<FJsonValue>& JsonValue : UITrees)
	{
		const TSharedPtr<FJsonObject> TreeObject = JsonValue->AsObject();
		// if (!TreeObject.IsValid() || !ContainsDisplayableWidget(TreeObject))
		// 仅校验对象有效性 (此处暂不过滤 “可显示控件”, 保留原注释逻辑)
		if (!TreeObject.IsValid())
		{
			continue;
		}

		// 必须包含 ObjectData 字段, 否则跳过
		if (!TreeObject->HasField(TEXT("ObjectData")))
		{
			continue;
		}

		TSharedPtr<FJsonObject> ObjectData = TreeObject->GetObjectField(TEXT("ObjectData"));

		// 将 Layer (层级) 值限制在 int32 合法范围内, 防止溢出
		const double LayerValueDouble = ObjectData->GetNumberField(TEXT("Layer"));
		const int32 LayerValue =
			(LayerValueDouble > static_cast<double>(INT32_MAX)) ? INT32_MAX : static_cast<int32>(LayerValueDouble);

		// 将修正后的层级值写回 JSON
		ObjectData->SetNumberField(TEXT("Layer"), LayerValue);

		UE_LOG(LogLQARestoreManager, Log, TEXT("Widget: %s, PanelLayer: %s, Layer: %d"),
			*TreeObject->GetStringField(TEXT("WidgetName")), *ObjectData->GetStringField(TEXT("PanelLayer")),
			LayerValue);

		// 该树有效, 加入待处理列表
		ValidUITrees.Add(JsonValue);

		// 记录顶层父控件: 仅当为纯文本控件且层级小于阈值时才更新
		if (ContainsOnlyTextWidget(TreeObject) && LayerValue < TopParentLayerThreshold)
		{
			TopParentWidget = TreeObject->GetStringField(TEXT("ParentWidget"));
		}
	}

	// 设置校验用父控件列表, 先清空旧数据
	AllCheckParentWidgets.Empty();

	if (!ObjectParentWidget.IsEmpty())
	{
		// 覆盖优先: 使用外部指定的父控件
		AllCheckParentWidgets.Add(ObjectParentWidget);
	}
	else if (!TopParentWidget.IsEmpty())
	{
		// 默认情况: 使用自动检测到的顶层父控件
		AllCheckParentWidgets.Add(TopParentWidget);
	}

	UE_LOG(LogLQARestoreManager, Log, TEXT("ValidUITrees: %d, CheckParentWidgets: %d"), ValidUITrees.Num(),
		AllCheckParentWidgets.Num());

	// 无有效 UI 树则提前退出
	if (ValidUITrees.Num() == 0)
	{
		return;
	}

	// 若存在背景图数据则进行处理
	FString BackgroundImagePath;
	if (RootObj->HasField(TEXT("bg_data")))
	{
		const FString BgData = RootObj->GetStringField(TEXT("bg_data"));
		UE_LOG(LogLQARestoreManager, Log, TEXT("Found bg_data field, length: %d"), BgData.Len());

		// 将十六进制背景数据解码并保存为图片文件
		BackgroundImagePath = ProcessBackgroundImage(BgData);
		if (!BackgroundImagePath.IsEmpty())
		{
			UE_LOG(LogLQARestoreManager, Log, TEXT("Background image saved to: %s"), *BackgroundImagePath);
			// 将背景图设置到窗口
			WindowProxy->ProcessImageBackground(*BackgroundImagePath);
		}
		else
		{
			UE_LOG(LogLQARestoreManager, Warning, TEXT("Failed to process background image"));
		}
	}
	else
	{
		UE_LOG(LogLQARestoreManager, Log, TEXT("No bg_data field found in JSON"));
	}

	// 逐棵有效 UI 树构建 UI 面板
	static const TArray<TSharedPtr<FJsonValue>> EmptyArray;  // 复用的空数组, 避免重复构造
	for (const TSharedPtr<FJsonValue>& JsonValue : ValidUITrees)
	{
		const TSharedPtr<FJsonObject> TreeObject = JsonValue->AsObject();
		FRestoreWidgetMeta MetaData;

		// 添加面板: 传入窗口尺寸与各类构建参数, 由窗口代理完成具体控件创建
		WindowProxy->AddPanel(nullptr, nullptr, nullptr, MetaData, nullptr, TEXT(""), EmptyArray, false, EmptyArray,
			TreeObject, InWindowSize, FVector2D::ZeroVector);
	}

	// 清理临时背景图文件, 避免残留
	if (!BackgroundImagePath.IsEmpty() && FPaths::FileExists(BackgroundImagePath))
	{
		IFileManager::Get().Delete(*BackgroundImagePath);
	}
}

FString FRestoreWindowUtils::ProcessBackgroundImage(const FString& HexData)
{
	UE_LOG(LogLQARestoreManager, Log, TEXT("ProcessBackgroundImage called, HexData length: %d"), HexData.Len());

	// 将十六进制字符串转换为字节数组
	TArray<uint8> Bytes;
	const int32 Length = HexData.Len();
	Bytes.Reserve(Length / 2);  // 每两个十六进制字符对应一个字节

	for (int32 i = 0; i < Length; i += 2)
	{
		if (i + 1 < Length)
		{
			// 高位字符 * 16 + 低位字符, 合成一个字节
			const uint8 Byte = FParse::HexDigit(HexData[i]) * 16 + FParse::HexDigit(HexData[i + 1]);
			Bytes.Add(Byte);
		}
	}

	// 未解析出任何字节, 视为失败
	if (Bytes.Num() == 0)
	{
		UE_LOG(LogLQARestoreManager, Warning, TEXT("No bytes converted from hex data"));
		return TEXT("");
	}

	UE_LOG(LogLQARestoreManager, Log, TEXT("Converted %d bytes from hex data"), Bytes.Num());

	// 使用时间戳生成唯一文件名, 避免重名覆盖
	const FString Timestamp = FDateTime::Now().ToString(TEXT("%Y%m%d_%H%M%S"));
	const FString SaveDir = FPaths::Combine(FPaths::ProjectSavedDir(), TEXT("LQABg"));

	// 目录不存在时创建 (递归创建)
	if (!IFileManager::Get().DirectoryExists(*SaveDir))
	{
		UE_LOG(LogLQARestoreManager, Log, TEXT("Creating directory: %s"), *SaveDir);
		IFileManager::Get().MakeDirectory(*SaveDir, true);
	}

	const FString FileName = FString::Printf(TEXT("%s_BG.png"), *Timestamp);
	const FString FilePath = FPaths::Combine(SaveDir, FileName);

	// 将字节数组写入文件
	if (FFileHelper::SaveArrayToFile(Bytes, *FilePath))
	{
		UE_LOG(LogLQARestoreManager, Log, TEXT("Background image saved successfully: %s"), *FilePath);
		return FilePath;
	}

	UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to save background image to: %s"), *FilePath);
	return TEXT("");
}