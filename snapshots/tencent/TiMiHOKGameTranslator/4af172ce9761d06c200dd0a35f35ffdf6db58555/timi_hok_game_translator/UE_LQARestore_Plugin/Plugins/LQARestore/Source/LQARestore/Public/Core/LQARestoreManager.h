#pragma once

#include "CoreMinimal.h"
#include "Subsystems/GameInstanceSubsystem.h"

#include "LQARestoreManager.generated.h"

// 声明本类专用的日志分类, 便于在输出日志中按 "LogLQARestoreManager" 过滤
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreManager, Log, All);

// 前置声明, 避免在头文件中包含完整定义, 降低编译依赖
class URestoreWindowProxy;  // 还原窗口代理: 负责具体窗口的创建/构建/销毁
class UConfigManager;       // 配置管理器: 读取语言、模式、路径等配置
class UTaskManager;         // 任务管理器: 负责网络请求 (拉任务/下载/上传)
class UFileManager;         // 文件管理器: 负责本地文件/目录读写与查找

/**
 * 截图取景范围: 决定截图链路走哪一条
 * 两种模式产出的是两种不同用途的图, 不可互相替代:
 *   - WidgetOnly: 只有还原出来的控件本身, 没有周围环境, 适合校验单个控件
 *   - Viewport:   玩家真正看到的画面, 包含背景与其他 UI, 适合还原比对
 */
UENUM(BlueprintType)
enum class ELQAScreenshotMode : uint8
{
	WidgetOnly UMETA(DisplayName = "仅控件 (离屏渲染)"),

	Viewport UMETA(DisplayName = "游戏视口 (含 UI)")
};

/**
 * LQA 还原工具的主控制器 (GameInstance 子系统)
 * 职责:
 *   1. 协调 配置(Config) / 网络(Task) / 文件(File) 三大模块的工作流
 *   2. 同时支持两种还原流程:
 *      - 平台模式 (Platform): 从远端服务器拉取任务、下载、还原、上传
 *      - 本地模式 (Local): 直接扫描本地 JSON 文件逐个还原
 * 生命周期跟随 GameInstance, 游戏实例创建时 Initialize, 销毁时 Deinitialize
 */
UCLASS()
class LQARESTORE_API ULQARestoreManager : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	// 子系统初始化入口: 创建管理器、绑定委托、启动工作定时器
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;
	// 子系统反初始化入口: 销毁所有窗口、清理定时器
	virtual void Deinitialize() override;

	/**
	 * 根据 dump 文件创建一个还原窗口 (蓝图可调用)
	 * @param DumpFilePath  dump JSON 文件的完整路径
	 * @param DataId        数据标识符, 用于命名输出目录及区分任务项
	 * @return              创建成功返回 true, 失败返回 false
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA Restore")
	bool MakeRestoredWindow(const FString& DumpFilePath, const FString& DataId = TEXT("0"));

	/**
	 * 清理当前所有活动的还原窗口, 并将进度推进到下一项 (蓝图可调用)
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA Restore")
	void ClearRestoreWindow();

	/**
	 * 设置截图模式, 决定后续每次截图取哪一块画面 (蓝图可调用)
	 * @param InMode WidgetOnly=仅还原控件, Viewport=整个游戏视口 (含 UI)
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA Restore")
	void SetScreenshotMode(ELQAScreenshotMode InMode);

	/** 获取当前截图模式 (蓝图可调用) */
	UFUNCTION(BlueprintCallable, Category = "LQA Restore")
	ELQAScreenshotMode GetScreenshotMode() const;

private:
	/** 初始化并启动整个还原工作流 (在 Initialize 延迟后调用) */
	void StartWork();

	/**
	 * 处理平台模式工作流
	 * @param bIsFirstRequest 是否为首次请求 (首次需要插入基准数据并启动定时器)
	 */
	void HandlePlatformWorkflow(bool bIsFirstRequest);

	/** 处理本地文件模式工作流: 扫描本地 JSON 并启动本地处理定时器 */
	void HandleLocalWorkflow();

	/** 根据配置的语言, 加载对应的翻译数据文件 */
	void LoadTranslationData();

	/** 若配置开启了对比 (cover) 模式, 则准备基准对比数据并插入待处理队列首位 */
	void SetupBaseDataIfNeeded();

	/** 设置平台模式下所有周期性定时器 (拉任务/下载/还原/上传) */
	void SetupPlatformTimers();

	// ===== 定时器回调 (周期性触发) =====
	void OnGetJobDataTick();   // 周期性向平台拉取任务数据
	void OnDownloadTick();     // 周期性处理下载队列
	void OnRestoreTick();      // 周期性尝试还原当前待处理项
	void OnUploadTick();       // 周期性处理上传队列
	void OnLocalJobTick();     // 本地模式下周期性处理下一个本地文件

	// ===== 网络委托回调 (由 TaskManager 触发) =====
	// 收到平台返回的任务列表 (ID 列表 + 对应文件路径列表)
	void OnJobDataReceived(const TArray<FString>& IdList, const TArray<FString>& IdPathList);
	// 某个 dump 数据下载完成
	void OnDumpDataDownloaded(const FString& DataId, const FString& FilePath);
	// 某个还原结果上传完成
	void OnRestoreResultUploaded(const FString& DataId);

	/** 处理当前索引指向的还原项 (含文件就绪的重试逻辑) */
	void ProcessCurrentRestoreItem();

	/** 窗口构建完成后, 安排延迟截图与结果上传 */
	void ScheduleScreenshotAndUpload(URestoreWindowProxy* Proxy, const FString& DataId);

	/** 截取整个视口 (Viewport) 画面并保存为文件 */
	bool CaptureViewportScreenshot(const FString& FilePath);

	/** 截取指定 UMG 控件的画面并保存为文件 */
	bool CaptureWidgetScreenshot(UUserWidget* Widget, const FString& FilePath);

	// ===== 核心管理器 (UPROPERTY 保证被 GC 引用, 不会被回收) =====
	UPROPERTY()
	UConfigManager* ConfigManager;   // 配置管理器实例

	UPROPERTY()
	UTaskManager* TaskManager;       // 任务 (网络) 管理器实例

	UPROPERTY()
	UFileManager* FileManager;       // 文件管理器实例

	// 当前所有活动的还原窗口: 键为窗口 ID, 值为窗口代理
	UPROPERTY()
	TMap<uint32, URestoreWindowProxy*> ActiveWindows;

	// 截图取景范围
	ELQAScreenshotMode ScreenshotMode = ELQAScreenshotMode::WidgetOnly;

	// ===== 工作数据 =====
	TArray<FString> PendingDataIds;    // 待还原的数据 ID 列表
	TArray<FString> PendingFilePaths;  // 与 PendingDataIds 一一对应的文件路径列表
	TArray<FString> LocalJsonFiles;    // 本地模式下扫描到的 JSON 文件路径列表
	TQueue<FString> CompletedDataIds;  // 已完成还原的数据 ID 队列

	// ===== 对比数据 =====
	TSharedPtr<FJsonObject> BaseComparisonData;  // 基准对比数据 (对比模式下使用)

	// ===== 状态跟踪 =====
	uint32 NextWindowId;              // 下一个窗口 ID (自增, 保证唯一)
	int32 CurrentRestoreIndex;        // 平台模式下当前还原项的索引
	int32 CurrentLocalFileIndex;      // 本地模式下当前处理文件的索引
	int32 CurrentRestoreRetryCount;   // 当前还原项的重试计数 (等待文件下载完成)
	bool bCanStartRestore;            // 是否允许开始新的还原 (防止并发还原)

	// ===== 定时器句柄 =====
	FTimerHandle StartWorkTimer;      // 启动工作流的延迟定时器
	FTimerHandle JobDataTimer;        // 拉取任务数据定时器
	FTimerHandle DownloadTimer;       // 下载处理定时器
	FTimerHandle RestoreTimer;        // 还原处理定时器
	FTimerHandle UploadTimer;         // 上传处理定时器
	FTimerHandle LocalJobTimer;       // 本地任务处理定时器
	FTimerHandle RefreshTextTimer;    // 文本刷新后构建窗口的延迟定时器
	FTimerHandle ScreenshotTimer;     // 截图的延迟定时器

	// ===== 定时器间隔 / 延迟 (单位: 秒) =====
	static constexpr float InitialStartDelay = 1.0f;    // 初始化后延迟多久启动工作流
	static constexpr float JobDataInterval = 150.0f;    // 拉取任务数据的周期
	static constexpr float DownloadInterval = 3.0f;     // 处理下载队列的周期
	static constexpr float RestoreInterval = 10.0f;     // 处理还原的周期
	static constexpr float UploadInterval = 4.0f;       // 处理上传队列的周期
	static constexpr float LocalJobInterval = 25.0f;    // 本地文件处理的周期
	static constexpr float RefreshTextDelay = 1.3f;     // 文本刷新到构建窗口的等待时间
	static constexpr float ScreenshotDelay = 8.0f;      // 窗口构建到截图的等待时间

	// ===== 重试配置 =====
	static constexpr int32 MaxRestoreRetryTimes = 3;    // 还原项等待文件的最大重试次数
};