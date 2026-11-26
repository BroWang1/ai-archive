#include "Core/LQARestoreManager.h"

#include "Core/ConfigManager.h"
#include "Core/FileManager.h"
#include "Core/RestoreWindowProxy.h"
#include "Core/RestoreWindowUtils.h"
#include "Core/RootObjWidget.h"
#include "Core/TaskManager.h"
#include "Framework/Application/SlateApplication.h" 
#include "Engine/GameViewportClient.h"
#include "Engine/TextureRenderTarget2D.h"
#include "ImageUtils.h"
#include "Interfaces/IPluginManager.h"
#include "Misc/FileHelper.h"
#include "Misc/ScopeExit.h"
#include "Slate/WidgetRenderer.h"
#include "UObject/StrongObjectPtr.h"
#include "Utils/TranslationUtils/LoaderUtils.h"
#include "Widgets/SViewport.h"

// 定义头文件中声明的日志分类
DEFINE_LOG_CATEGORY(LogLQARestoreManager);

// 子系统初始化: 重置状态 -> 创建并初始化管理器 -> 绑定委托 -> 延迟启动工作流
void ULQARestoreManager::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	UE_LOG(LogLQARestoreManager, Log, TEXT("LQARestoreManager initializing"));

	// 初始化内部状态变量
	NextWindowId = 0;
	CurrentRestoreIndex = 0;
	CurrentLocalFileIndex = 0;
	CurrentRestoreRetryCount = 0;
	bCanStartRestore = true;

	// 创建三大管理器实例 (以 this 为 Outer, 随本对象生命周期管理)
	ConfigManager = NewObject<UConfigManager>(this);
	TaskManager = NewObject<UTaskManager>(this);
	FileManager = NewObject<UFileManager>(this);

	// 初始化管理器: TaskManager 需要依赖 Config 与 File
	ConfigManager->Initialize();
	TaskManager->Initialize(ConfigManager, FileManager);

	// 绑定网络相关委托, 将 TaskManager 的事件回调到本类对应处理函数
	TaskManager->OnJobDataReceived.AddUObject(this, &ULQARestoreManager::OnJobDataReceived);
	TaskManager->OnDumpDataDownloaded.AddUObject(this, &ULQARestoreManager::OnDumpDataDownloaded);
	TaskManager->OnRestoreResultUploaded.AddUObject(this, &ULQARestoreManager::OnRestoreResultUploaded);

	// 延迟 InitialStartDelay 秒后启动工作流
	// 使用 TWeakObjectPtr 弱引用, 避免定时器回调时对象已被销毁导致悬空访问
	TWeakObjectPtr<ULQARestoreManager> WeakThis(this);
	GetWorld()->GetTimerManager().SetTimer(
		StartWorkTimer,
		[WeakThis]()
		{
			if (WeakThis.IsValid())
			{
				WeakThis->StartWork();
			}
		},
		InitialStartDelay, false);  // false 表示不循环, 仅触发一次
}

// 子系统反初始化: 销毁窗口、清理定时器, 确保无资源泄漏
void ULQARestoreManager::Deinitialize()
{
	// 销毁所有活动窗口
	for (const TPair<uint32, URestoreWindowProxy*>& Proxy : ActiveWindows)
	{
		Proxy.Value->DestroyWindow();
	}
	ActiveWindows.Empty();

	// 清理本对象注册的所有定时器
	if (GetWorld())
	{
		GetWorld()->GetTimerManager().ClearAllTimersForObject(this);
	}

	Super::Deinitialize();
	UE_LOG(LogLQARestoreManager, Log, TEXT("LQARestoreManager deinitialized"));
}

// 工作流入口: 先加载翻译数据, 再根据模式分流到本地/平台工作流
void ULQARestoreManager::StartWork()
{
	UE_LOG(LogLQARestoreManager, Log, TEXT("Starting restore workflow"));

	LoadTranslationData();

	if (ConfigManager->IsLocalMode())
	{
		HandleLocalWorkflow();   // 本地模式
	}
	else
	{
		HandlePlatformWorkflow(true);  // 平台模式 (首次请求)
	}
}

// 加载翻译数据: 根据配置的 PO 语言, 拼出两类本地化 JSON 文件路径并加载
void ULQARestoreManager::LoadTranslationData()
{
	const FString& PoLanguage = ConfigManager->GetPoLanguage();

	// 把配置里的还原方向下发给静态翻译工具 (影响 GetTranslateString 的中文守卫)
	FLoaderUtils::SetRestoreDirection(ConfigManager->GetRestoreDirection());

	// 本地化目录: <插件根目录>/LQALocalization
	const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("LQARestore"));
	const FString PluginBaseDir =
		Plugin.IsValid() ? Plugin->GetBaseDir() : (FPaths::ProjectPluginsDir() / TEXT("LQARestore"));
	const FString LocalizationDir =
		FPaths::ConvertRelativePathToFull(PluginBaseDir / TEXT("LQALocalization"));

	// 游戏本地化导出文件 与 文本翻译文件 (文件名带语言后缀)
	const FString GameLocFile =
		FPaths::Combine(LocalizationDir, FString::Printf(TEXT("GameLocalizationExport_%s.json"), *PoLanguage));
	const FString TextTransFile =
		FPaths::Combine(LocalizationDir, FString::Printf(TEXT("Text_Translations_%s.json"), *PoLanguage));

	UE_LOG(LogLQARestoreManager, Log, TEXT("Loading translation files:"));
	UE_LOG(LogLQARestoreManager, Log, TEXT("  - %s"), *GameLocFile);
	UE_LOG(LogLQARestoreManager, Log, TEXT("  - %s"), *TextTransFile);

	// 交由加载工具解析并缓存翻译数据
	FLoaderUtils::LoadJsonFromFile(GameLocFile, TextTransFile, PoLanguage);
}

// 对比模式准备: 仅当配置 IsCover == "true" 且基准数据有效时,
// 将基准数据插入待处理队列的最前面, 使其最先被还原并作为对比基准
void ULQARestoreManager::SetupBaseDataIfNeeded()
{
	const FString& IsCover = ConfigManager->GetIsCover();
	if (IsCover != TEXT("true"))
	{
		return;  // 未开启对比模式, 直接返回
	}

	const FString& BaseDataId = ConfigManager->GetBaseDataId();
	const FString& BaseDataFilePath = ConfigManager->GetBaseDataFilePath();

	// 基准数据配置不完整则跳过
	if (BaseDataId.IsEmpty() || BaseDataFilePath.IsEmpty())
	{
		return;
	}

	UE_LOG(LogLQARestoreManager, Log, TEXT("Inserting base data ID: %s"), *BaseDataId);
	// 插入到索引 0, 保证基准数据优先处理
	PendingDataIds.Insert(BaseDataId, 0);
	PendingFilePaths.Insert(BaseDataFilePath, 0);
}

// 启动平台模式的四个周期性定时器 (下载/还原/上传/拉任务, 均为循环定时器)
void ULQARestoreManager::SetupPlatformTimers()
{
	FTimerManager& TimerManager = GetWorld()->GetTimerManager();

	TimerManager.SetTimer(DownloadTimer, this, &ULQARestoreManager::OnDownloadTick, DownloadInterval, true);
	TimerManager.SetTimer(RestoreTimer, this, &ULQARestoreManager::OnRestoreTick, RestoreInterval, true);
	TimerManager.SetTimer(UploadTimer, this, &ULQARestoreManager::OnUploadTick, UploadInterval, true);
	TimerManager.SetTimer(JobDataTimer, this, &ULQARestoreManager::OnGetJobDataTick, JobDataInterval, true);
}

// 平台工作流: 首次请求时准备基准数据并启动定时器, 然后向平台请求任务数据
void ULQARestoreManager::HandlePlatformWorkflow(bool bIsFirstRequest)
{
	if (bIsFirstRequest)
	{
		SetupBaseDataIfNeeded();
		SetupPlatformTimers();
	}

	TaskManager->RequestJobData(bIsFirstRequest);
}

// 本地工作流: 递归扫描本地 LQA 目录下的 JSON 文件, 并启动本地处理定时器
void ULQARestoreManager::HandleLocalWorkflow()
{
	const FString BasePath = ConfigManager->GetPngSaveRootDir();
	const FString LocalDataPath = FPaths::Combine(BasePath, TEXT("LQA"));

	// 递归查找所有 JSON 文件, 结果存入 LocalJsonFiles
	FileManager->FindJsonFilesRecursive(LocalDataPath, LocalJsonFiles);
	CurrentLocalFileIndex = 0;

	UE_LOG(LogLQARestoreManager, Log, TEXT("Found %d local JSON files in: %s"), LocalJsonFiles.Num(), *LocalDataPath);

	// 启动循环定时器, 逐个处理本地文件
	GetWorld()->GetTimerManager().SetTimer(
		LocalJobTimer, this, &ULQARestoreManager::OnLocalJobTick, LocalJobInterval, true);
}

// 收到平台任务数据回调: 对新 ID 去重后加入待处理列表, 并加入下载队列
void ULQARestoreManager::OnJobDataReceived(const TArray<FString>& InIdList, const TArray<FString>& InIdPathList)
{
	UE_LOG(LogLQARestoreManager, Log, TEXT("Received %d job data items"), InIdList.Num());

	for (int32 i = 0; i < InIdList.Num(); ++i)
	{
		// 去重: 避免重复加入同一数据 ID
		if (!PendingDataIds.Contains(InIdList[i]))
		{
			PendingDataIds.Add(InIdList[i]);
			PendingFilePaths.Add(InIdPathList[i]);
			TaskManager->EnqueueDownload(InIdList[i], InIdPathList[i]);  // 加入下载队列
		}
	}
}

// dump 数据下载完成回调: 若该文件为基准数据且尚未加载, 则加载为对比基准
void ULQARestoreManager::OnDumpDataDownloaded(const FString& DataId, const FString& FilePath)
{
	UE_LOG(LogLQARestoreManager, Log, TEXT("Dump data downloaded: %s"), *DataId);

	// 仅在基准数据尚未加载、且当前下载项正是基准数据时加载
	const FString& BaseDataId = ConfigManager->GetBaseDataId();
	if (!BaseComparisonData.IsValid() && DataId == BaseDataId)
	{
		BaseComparisonData = FileManager->LoadJsonFromFile(FilePath);
		if (BaseComparisonData.IsValid())
		{
			UE_LOG(LogLQARestoreManager, Log, TEXT("Base comparison data loaded: %s"), *BaseDataId);
		}
	}
}

// 还原结果上传完成回调: 目前仅记录日志
void ULQARestoreManager::OnRestoreResultUploaded(const FString& DataId)
{
	UE_LOG(LogLQARestoreManager, Log, TEXT("Restore result uploaded: %s"), *DataId);
}

// 拉取任务定时器回调: 本地模式跳过, 否则发起非首次的平台任务请求
void ULQARestoreManager::OnGetJobDataTick()
{
	// 本地模式不需要拉取平台任务
	if (ConfigManager->IsLocalMode())
	{
		return;
	}

	HandlePlatformWorkflow(false);
}

// 下载定时器回调: 本地模式跳过, 否则在可下载时处理下载队列
void ULQARestoreManager::OnDownloadTick()
{
	// 本地模式跳过
	if (ConfigManager->IsLocalMode())
	{
		return;
	}

	if (TaskManager->CanDownload())
	{
		TaskManager->ProcessDownloadQueue();
	}
}

// 还原定时器回调: 本地模式跳过 (本地走 OnLocalJobTick):
// 平台模式下在允许还原且仍有待处理项时, 处理当前还原项
void ULQARestoreManager::OnRestoreTick()
{
	// 本地模式使用 OnLocalJobTick, 这里跳过
	if (ConfigManager->IsLocalMode())
	{
		return;
	}

	// 没有待处理项, 直接返回
	if (PendingDataIds.Num() == 0)
	{
		return;
	}

	// 当前有还原在进行 (!bCanStartRestore) 或 索引越界, 则不处理
	if (!bCanStartRestore || CurrentRestoreIndex >= PendingDataIds.Num())
	{
		return;
	}

	ProcessCurrentRestoreItem();
}

// 处理当前还原项: 检查 dump 文件是否已就绪
//   - 已就绪: 开始创建还原窗口
//   - 未就绪: 按最大次数重试等待下载, 超过上限则跳过该项
void ULQARestoreManager::ProcessCurrentRestoreItem()
{
	bCanStartRestore = false;  // 加锁, 防止并发还原

	const FString& CurrentDataId = PendingDataIds[CurrentRestoreIndex];
	// 拼出 dump 文件路径: <根目录>/LQAData/LQA_<DataId>.json
	const FString DumpFilePath = FPaths::Combine(
		ConfigManager->GetPngSaveRootDir(), TEXT("LQAData"), FString::Printf(TEXT("LQA_%s.json"), *CurrentDataId));

	if (FPaths::FileExists(DumpFilePath))
	{
		// 文件已就绪, 开始还原
		UE_LOG(LogLQARestoreManager, Log, TEXT("Restoring data ID: %s"), *CurrentDataId);
		CurrentRestoreRetryCount = 0;  // 重置重试计数
		MakeRestoredWindow(DumpFilePath, CurrentDataId);
	}
	else
	{
		// 文件尚未下载完成, 增加重试计数
		++CurrentRestoreRetryCount;

		if (CurrentRestoreRetryCount < MaxRestoreRetryTimes)
		{
			// 未达重试上限, 继续等待 (下一次定时器再试, 不推进索引)
			UE_LOG(LogLQARestoreManager, Log, TEXT("Waiting for file download: %s (Attempt: %d/%d)"), *CurrentDataId,
				CurrentRestoreRetryCount, MaxRestoreRetryTimes);
			bCanStartRestore = true;  // 解锁以便下次重试
		}
		else
		{
			// 达到重试上限, 跳过该项
			UE_LOG(LogLQARestoreManager, Warning, TEXT("File not found after %d attempts, skipping: %s"),
				MaxRestoreRetryTimes, *DumpFilePath);
			CurrentRestoreRetryCount = 0;  // 重置重试计数
			bCanStartRestore = true;
			++CurrentRestoreIndex;         // 推进到下一项
		}
	}
}

// 上传定时器回调: 本地模式跳过, 否则在可上传时处理上传队列
void ULQARestoreManager::OnUploadTick()
{
	// 本地模式不上传
	if (ConfigManager->IsLocalMode())
	{
		return;
	}

	if (TaskManager->CanUpload())
	{
		TaskManager->ProcessUploadQueue();
	}
}

// 本地任务定时器回调: 逐个处理本地 JSON 文件, 全部处理完则停止定时器
void ULQARestoreManager::OnLocalJobTick()
{
	// 没有可处理的文件, 停止定时器
	if (LocalJsonFiles.Num() == 0)
	{
		UE_LOG(LogLQARestoreManager, Warning, TEXT("No JSON files found for local processing"));
		GetWorld()->GetTimerManager().ClearTimer(LocalJobTimer);
		return;
	}

	// 全部处理完, 停止定时器
	if (CurrentLocalFileIndex >= LocalJsonFiles.Num())
	{
		UE_LOG(LogLQARestoreManager, Log, TEXT("All local JSON files processed"));
		GetWorld()->GetTimerManager().ClearTimer(LocalJobTimer);
		return;
	}

	// 取当前文件路径, 用文件名 (不含扩展名) 作为 DataId
	const FString& JsonFilePath = LocalJsonFiles[CurrentLocalFileIndex];
	const FString DataId = FPaths::GetBaseFilename(JsonFilePath);

	UE_LOG(LogLQARestoreManager, Log, TEXT("Processing local file [%d/%d]: %s"), CurrentLocalFileIndex + 1,
		LocalJsonFiles.Num(), *JsonFilePath);

	MakeRestoredWindow(JsonFilePath, DataId);
	++CurrentLocalFileIndex;  // 推进到下一个本地文件
}

// 创建还原窗口: 新建窗口代理 -> 创建窗口 -> 延迟刷新文本后构建窗口
bool ULQARestoreManager::MakeRestoredWindow(const FString& DumpFilePath, const FString& DataId)
{
	URestoreWindowProxy* WindowProxy = NewObject<URestoreWindowProxy>(this);
	if (!WindowProxy)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to create RestoreWindowProxy"));
		return false;
	}

	// 分配唯一窗口 ID 并登记到活动窗口表
	++NextWindowId;
	WindowProxy->Initialize(NextWindowId, GetGameInstance());
	ActiveWindows.Emplace(NextWindowId, WindowProxy);

	// 记录本次 dump 的 session 目录, 以便资源按路径加载失败时,
	// 能从同目录的 Textures/<nameMD5>.png 兜底还原运行时生成的纹理
	WindowProxy->SetSnapshotDirectory(FPaths::GetPath(DumpFilePath));

	// 先创建窗口 (加载布局)
	FRestoreWindowUtils::CreateWindow(DumpFilePath, WindowProxy);

	// 延迟一段时间等待文本刷新后再构建窗口内容
	// 使用弱引用防止回调时对象已销毁
	TWeakObjectPtr<ULQARestoreManager> WeakThis(this);
	GetWorld()->GetTimerManager().SetTimer(
		RefreshTextTimer,
		[WeakThis, DumpFilePath, WindowProxy, DataId]()
		{
			if (!WeakThis.IsValid())
			{
				return;
			}

			// 判断当前项是否为基准数据:
			//   - 是基准数据: 构建时不使用对比数据 (nullptr)
			//   - 非基准数据: 使用已加载的 BaseComparisonData 做对比
			const bool bIsBaseData = (DataId == WeakThis->ConfigManager->GetBaseDataId());
			const TSharedPtr<FJsonObject>& ComparisonData = bIsBaseData ? nullptr : WeakThis->BaseComparisonData;

			// 构建窗口内容
			const bool bBuildSuccess = FRestoreWindowUtils::BuildWindow(DumpFilePath, WindowProxy, ComparisonData);
			if (bBuildSuccess)
			{
				// 构建成功: 安排截图与上传
				WeakThis->ScheduleScreenshotAndUpload(WindowProxy, DataId);
			}
			else
			{
				// 构建失败: 记录错误，解锁并推进到下一项
				UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to build window for: %s"), *DataId);
				WeakThis->bCanStartRestore = true;
				++WeakThis->CurrentRestoreIndex;
			}
		},
		RefreshTextDelay, false);

	return true;
}

// 设置截图模式; 仅影响之后排好的截图, 不会改动正在进行中的那次
void ULQARestoreManager::SetScreenshotMode(ELQAScreenshotMode InMode)
{
	if (ScreenshotMode == InMode)
	{
		return;
	}

	ScreenshotMode = InMode;

	UE_LOG(LogLQARestoreManager, Log, TEXT("Screenshot mode switched to: %s"),
		InMode == ELQAScreenshotMode::WidgetOnly ? TEXT("WidgetOnly") : TEXT("Viewport"));
}

ELQAScreenshotMode ULQARestoreManager::GetScreenshotMode() const
{
	return ScreenshotMode;
}

// 安排截图与上传: 延迟等待渲染稳定后, 截图 -> 生成结果 JSON -> 清理窗口 -> 入上传队列
void ULQARestoreManager::ScheduleScreenshotAndUpload(URestoreWindowProxy* WindowProxy, const FString& DataId)
{
	TWeakObjectPtr<ULQARestoreManager> WeakThis(this);

	GetWorld()->GetTimerManager().SetTimer(
		ScreenshotTimer,
		[WeakThis, WindowProxy, DataId]()
		{
			if (!WeakThis.IsValid())
			{
				return;
			}

			// 结果输出目录: <根目录>/LQAResult/Restore_<DataId>_<Language>
			const FString& Language = WeakThis->ConfigManager->GetLanguage();
			const FString ResultDirName = FString::Printf(TEXT("Restore_%s_%s"), *DataId, *Language);
			const FString ResultDirPath =
				FPaths::Combine(WeakThis->ConfigManager->GetPngSaveRootDir(), TEXT("LQAResult"), ResultDirName);

			// 先删除旧目录再重建, 确保输出目录干净
			WeakThis->FileManager->DeleteDirectory(ResultDirPath);
			WeakThis->FileManager->EnsureDirectoryExists(ResultDirPath);

			// 截图并保存为 screenshot.png, 取景范围由 ScreenshotMode 决定:
			//   WidgetOnly -> CaptureWidgetScreenshot: 只截根控件 (离屏渲染, 不带背景)
			//   Viewport   -> CaptureViewportScreenshot: 截游戏视口 (背景 + 全部 UI)
			const FString ScreenshotFilePath = FPaths::Combine(ResultDirPath, TEXT("screenshot.png"));
			bool bScreenshotSuccess = false;

			switch (WeakThis->ScreenshotMode)
			{
			case ELQAScreenshotMode::WidgetOnly:
			{
				URootObjWidget* RootWidget = (WindowProxy != nullptr) ? WindowProxy->GetRootWidget() : nullptr;

				if (IsValid(RootWidget))
				{
					bScreenshotSuccess = WeakThis->CaptureWidgetScreenshot(RootWidget, ScreenshotFilePath);
				}
				else
				{
					UE_LOG(LogLQARestoreManager, Error, TEXT("WidgetOnly screenshot needs a valid root widget: %s"), *DataId);
				}

				break;
			}

			case ELQAScreenshotMode::Viewport:
			{
				bScreenshotSuccess = WeakThis->CaptureViewportScreenshot(ScreenshotFilePath);
				break;
			}

			default:
				UE_LOG(LogLQARestoreManager, Error, TEXT("Unsupported screenshot mode: %d"),
					static_cast<int32>(WeakThis->ScreenshotMode));
				break;
			}

			if (!bScreenshotSuccess)
			{
				UE_LOG(LogLQARestoreManager, Warning, TEXT("Failed to capture screenshot for: %s"), *DataId);
			}

			// 生成校验/结果 JSON
			UE_LOG(LogLQARestoreManager, Log, TEXT("Generating output for: %s"), *DataId);
			FRestoreWindowUtils::GenerateCheckJson(WindowProxy, ResultDirPath);

			// 清理窗口并推进进度: 入上传队列 (本地模式下 OnUploadTick 会跳过实际上传)
			WeakThis->ClearRestoreWindow();
			WeakThis->TaskManager->EnqueueUpload(DataId);
		},
		ScreenshotDelay, false);
}

// 清理还原窗口: 解锁 -> 记录已完成项 -> 推进索引 -> 销毁所有活动窗口
void ULQARestoreManager::ClearRestoreWindow()
{
	bCanStartRestore = true;  // 解锁, 允许开始下一项还原

	// 将当前项记入已完成队列
	if (CurrentRestoreIndex < PendingDataIds.Num())
	{
		CompletedDataIds.Enqueue(PendingDataIds[CurrentRestoreIndex]);
	}
	++CurrentRestoreIndex;  // 推进到下一项

	// 销毁所有活动窗口
	for (const TPair<uint32, URestoreWindowProxy*>& Proxy : ActiveWindows)
	{
		Proxy.Value->DestroyWindow();
	}
	ActiveWindows.Empty();

	UE_LOG(LogLQARestoreManager, Log, TEXT("Restore windows cleared, ready for next item"));
}

// 截取指定 UMG 控件画面并保存为 PNG
// 流程: 计算控件尺寸 -> 创建渲染目标 -> 绘制控件 -> 读像素 -> 转 PNG -> 存盘
bool ULQARestoreManager::CaptureWidgetScreenshot(UUserWidget* Widget, const FString& FilePath)
{
	// UMG 绘制及 GameThread_GetRenderTargetResource 应在游戏线程执行
	if (!IsInGameThread())
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("CaptureWidgetScreenshot must run on the game thread"));
		return false;
	}

	if (!IsValid(Widget))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Widget is invalid"));
		return false;
	}

	if (FilePath.IsEmpty())
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Screenshot file path is empty"));
		return false;
	}

	// 更新布局预计算
	Widget->ForceLayoutPrepass();

	const FGeometry& CachedGeometry = Widget->GetCachedGeometry();
	const FVector2D LogicalSize = CachedGeometry.GetLocalSize();

	const float DrawScale = CachedGeometry.GetAccumulatedLayoutTransform().GetScale();
	const float SafeScale = (DrawScale > KINDA_SMALL_NUMBER) ? DrawScale : 1.0f;

	// DrawSize 使用物理像素 (逻辑尺寸 * DPI 缩放), 与窗口的实际像素尺寸一致
	const FVector2D DrawSize = LogicalSize * SafeScale;

	if (!FMath::IsFinite(DrawSize.X) || !FMath::IsFinite(DrawSize.Y) ||
		DrawSize.X <= 0.0 || DrawSize.Y <= 0.0)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Invalid widget size: %fx%f"), DrawSize.X, DrawSize.Y);
		return false;
	}


	const int32 Width = FMath::CeilToInt(DrawSize.X);
	const int32 Height = FMath::CeilToInt(DrawSize.Y);
	const int64 RequiredBytes = static_cast<int64>(Width) * Height * 4;

	if (Width <= 0 || Height <= 0 || RequiredBytes > MAX_int32)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Screenshot size is too large: %dx%d"), Width, Height);
		return false;
	}

	// 确保输出目录存在
	const FString OutputDirectory = FPaths::GetPath(FilePath);

	if (!OutputDirectory.IsEmpty() && !IFileManager::Get().DirectoryExists(*OutputDirectory))
	{
		if (!IFileManager::Get().MakeDirectory(*OutputDirectory, true))
		{
			UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to create directory: %s"), *OutputDirectory);
			return false;
		}
	}

	// 创建渲染目标
	TStrongObjectPtr<UTextureRenderTarget2D> RenderTarget(
		FWidgetRenderer::CreateTargetFor(FVector2D(Width, Height), TF_Bilinear, /*bUseGammaCorrection=*/false));

	if (!RenderTarget.IsValid())
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to create render target"));
		return false;
	}

	// 用作用域守卫保证任何退出路径都会释放 RT 的 GPU 资源
	ON_SCOPE_EXIT
	{
		if (RenderTarget.IsValid())
		{
			RenderTarget->ReleaseResource();
		}
	};

	// 绘制控件及其子控件
	TUniquePtr<FWidgetRenderer> WidgetRenderer = MakeUnique<FWidgetRenderer>(false);

	WidgetRenderer->DrawWidget(RenderTarget.Get(), Widget->TakeWidget(), SafeScale, FVector2D(Width, Height), 0.0f);

	// 同步等待渲染完成, 之后再读取像素
	FlushRenderingCommands();

	FTextureRenderTargetResource* RTResource = RenderTarget->GameThread_GetRenderTargetResource();

	if (!RTResource)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to get render target resource"));
		return false;
	}

	TArray<FColor> OutBMP;

	if (!RTResource->ReadPixels(OutBMP))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to read pixels from render target"));
		return false;
	}

	// 编码始终以渲染目标实际尺寸为准
	const int32 ImageWidth = RenderTarget->SizeX;
	const int32 ImageHeight = RenderTarget->SizeY;

	const int64 ExpectedPixelCount = static_cast<int64>(ImageWidth) * ImageHeight;

	if (static_cast<int64>(OutBMP.Num()) != ExpectedPixelCount)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Pixel count mismatch: RT=%dx%d, Pixels=%d"), ImageWidth, ImageHeight,
			OutBMP.Num());
		return false;
	}

#if ENGINE_MAJOR_VERSION >= 5
	// FImageView 直接指向 OutBMP 的像素, 不拷贝数据: FColor 数组即 BGRA8
	const FImageView ImageView(OutBMP.GetData(), ImageWidth, ImageHeight);
	TArray64<uint8> CompressedData;
	if (!FImageUtils::CompressImage(CompressedData, TEXT("png"), ImageView))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to compress image to PNG"));
		return false;
	}
#else
	TArray<uint8> CompressedData;
	FImageUtils::CompressImageArray(ImageWidth, ImageHeight, OutBMP, CompressedData);
#endif

	if (CompressedData.Num() == 0)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("PNG compression returned empty data"));
		return false;
	}

	if (!FFileHelper::SaveArrayToFile(CompressedData, *FilePath))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to save screenshot to: %s"), *FilePath);
		return false;
	}

	UE_LOG(LogLQARestoreManager, Log, TEXT("Widget screenshot saved to: %s (Size: %dx%d)"), *FilePath, ImageWidth,
		ImageHeight);

	return true;
}

// 截取当前游戏视口画面 (含 UI) 并保存为 PNG
// 流程: 取视口控件 -> Slate 截图 -> 转 PNG -> 存盘
bool ULQARestoreManager::CaptureViewportScreenshot(const FString& FilePath)
{
	UGameViewportClient* ViewportClient = GetWorld()->GetGameViewport();
	if (!ViewportClient)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to get GameViewportClient"));
		return false;
	}

	// 取游戏视口控件
	const TSharedPtr<SViewport> ViewportWidget = ViewportClient->GetGameViewportWidget();
	if (!ViewportWidget.IsValid() || !FSlateApplication::IsInitialized())
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to get game viewport widget"));
		return false;
	}

	// 确保输出目录存在, 否则 SaveArrayToFile 会直接失败
	const FString OutputDirectory = FPaths::GetPath(FilePath);

	if (!OutputDirectory.IsEmpty() && !IFileManager::Get().DirectoryExists(*OutputDirectory))
	{
		if (!IFileManager::Get().MakeDirectory(*OutputDirectory, true))
		{
			UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to create directory: %s"), *OutputDirectory);
			return false;
		}
	}

	TArray<FColor> Bitmap;
	FIntVector Size(0, 0, 0);
	if (!FSlateApplication::Get().TakeScreenshot(ViewportWidget.ToSharedRef(), Bitmap, Size))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to take screenshot of game viewport"));
		return false;
	}

	const int64 ExpectedPixelCount = static_cast<int64>(Size.X) * Size.Y;
	if (Size.X <= 0 || Size.Y <= 0 || static_cast<int64>(Bitmap.Num()) != ExpectedPixelCount)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Pixel count mismatch: ViewportWidget=%dx%d, Pixels=%d"), Size.X, Size.Y,
			Bitmap.Num());
		return false;
	}

#if ENGINE_MAJOR_VERSION >= 5
	const FImageView ImageView(Bitmap.GetData(), Size.X, Size.Y);
	TArray64<uint8> CompressedData;
	if (!FImageUtils::CompressImage(CompressedData, TEXT("png"), ImageView))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to compress image to PNG"));
		return false;
	}
#else
	TArray<uint8> CompressedData;
	FImageUtils::CompressImageArray(Size.X, Size.Y, Bitmap, CompressedData);
#endif

	if (CompressedData.Num() == 0)
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("PNG compression returned empty data"));
		return false;
	}

	if (!FFileHelper::SaveArrayToFile(CompressedData, *FilePath))
	{
		UE_LOG(LogLQARestoreManager, Error, TEXT("Failed to save screenshot to: %s"), *FilePath);
		return false;
	}

	UE_LOG(LogLQARestoreManager, Log, TEXT("Screenshot saved to: %s (Size: %dx%d)"), *FilePath, Size.X, Size.Y);
	return true;
}