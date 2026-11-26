#pragma once

#include "CoreMinimal.h"
#include "Http.h"  // UE HTTP 模块, 提供 FHttpResponsePtr 等类型

#include "TaskManager.generated.h"  // UHT 自动生成的反射代码, 必须放在最后一个 include

// 声明一个专属的日志分类 LogLQARestoreTask, 用于本模块所有日志输出
// 参数: 分类名、默认日志级别 (Log)、编译期允许的最高日志级别 (All)
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreTask, Log, All);

// 前向声明依赖的管理器类, 避免在头文件中引入其完整定义, 降低编译耦合
class UConfigManager;
class UFileManager;

/**
 * 任务数据接收完成的委托 (多播, 两个参数)
 * @param IdList     服务器返回的任务 ID 列表
 * @param IdPathList 与 ID 一一对应的远端文件路径列表
 */
DECLARE_MULTICAST_DELEGATE_TwoParams(
	FOnJobDataReceived, const TArray<FString>&, const TArray<FString>&);

/**
 * 单个 dump 数据下载成功的委托
 * @param DataId   数据 ID
 * @param FilePath 本地保存路径 (若文件已存在则为空字符串)
 */
DECLARE_MULTICAST_DELEGATE_TwoParams(FOnDumpDataDownloaded, const FString&, const FString&);

/**
 * 单个 dump 数据下载失败 (已达到最大重试次数) 的委托
 * @param DataId 数据 ID
 */
DECLARE_MULTICAST_DELEGATE_OneParam(FOnDumpDataFailed, const FString&);

/**
 * 还原结果上传成功的委托
 * @param DataId 数据 ID
 */
DECLARE_MULTICAST_DELEGATE_OneParam(FOnRestoreResultUploaded, const FString&);

/**
 * LQA 还原工具的任务管理器
 * 负责处理 HTTP 业务逻辑, 包括: 任务数据请求、下载/上传队列调度, 以及失败重试逻辑
 * 内部通过串行队列保证同一时刻只进行一个下载/一个上传任务
 */
UCLASS()
class LQARESTORE_API UTaskManager : public UObject
{
	GENERATED_BODY()

public:
	/**
	 * 初始化任务管理器, 注入依赖并重置内部状态
	 * @param InConfigManager 配置管理器实例 (提供 JobId、语言、路径等配置)
	 * @param InFileManager   文件管理器实例 (负责文件读写与目录操作)
	 */
	void Initialize(UConfigManager* InConfigManager, UFileManager* InFileManager);

	/**
	 * 向服务器请求任务数据
	 * @param bIsFirstRequest 是否为首次请求 (用于区分首次拉取与后续轮询的处理策略)
	 */
	void RequestJobData(bool bIsFirstRequest);

	/** 处理下载队列中的下一个任务 (若当前无下载进行中) */
	void ProcessDownloadQueue();

	/** 处理上传队列中的下一个任务 (若当前无上传进行中) */
	void ProcessUploadQueue();

	/**
	 * 将一条数据加入下载队列
	 * @param DataId   数据标识
	 * @param FilePath 远端文件路径
	 */
	void EnqueueDownload(const FString& DataId, const FString& FilePath);

	/**
	 * 将一条数据加入上传队列
	 * @param DataId 数据标识
	 */
	void EnqueueUpload(const FString& DataId);

	/** 当前是否允许发起下载 (无下载正在进行时返回 true) */
	FORCEINLINE bool CanDownload() const
	{
		return !bIsDownloading;
	}

	/** 当前是否允许发起上传 (无上传正在进行时返回 true) */
	FORCEINLINE bool CanUpload() const
	{
		return !bIsUploading;
	}

	/** 获取当前正在下载的数据 ID */
	FORCEINLINE const FString& GetCurrentDownloadId() const
	{
		return ActiveDownloadDataId;
	}

	/** 获取当前正在上传的数据 ID */
	FORCEINLINE const FString& GetCurrentUploadId() const
	{
		return ActiveUploadDataId;
	}

	// ===== 对外广播的事件委托, 供外部模块 (如 UI、调度器) 绑定监听 =====
	FOnJobDataReceived OnJobDataReceived;            // 任务数据接收完成
	FOnDumpDataDownloaded OnDumpDataDownloaded;      // dump 数据下载成功
	FOnDumpDataFailed OnDumpDataFailed;              // dump 数据下载失败
	FOnRestoreResultUploaded OnRestoreResultUploaded;// 还原结果上传成功

private:
	/** 任务数据请求成功的 HTTP 回调: 解析 JSON 并广播 OnJobDataReceived */
	void OnJobDataSuccess(FHttpResponsePtr Response);

	/** 下载成功的 HTTP 回调: 校验/解压/保存数据, 并广播下载结果 */
	void OnDownloadSuccess(FHttpResponsePtr Response);

	/** 下载失败处理: 按最大重试次数决定重新入队或广播失败 */
	void OnDownloadFail();

	/** 上传成功的 HTTP 回调: 重置状态并广播 OnRestoreResultUploaded */
	void OnUploadSuccess(FHttpResponsePtr Response);

	/** 上传失败处理: 按最大重试次数决定重新入队或放弃 */
	void OnUploadFail();

	/**
	 * 解压 gzip 格式数据
	 * @param CompressedData     输入的压缩数据
	 * @param OutDecompressedData 输出的解压后数据
	 * @return 解压成功返回 true, 失败返回 false
	 */
	bool DecompressGzipData(const TArray<uint8>& CompressedData, TArray<uint8>& OutDecompressedData);

	/**
	 * 计算指定数据的还原结果目录路径
	 * @param DataId     数据标识
	 * @param OutPngDir  输出的 PNG 文件所在目录
	 * @param OutJsonDir 输出的 JSON 文件所在目录 (当前实现与 PNG 目录相同)
	 */
	void GetRestoreResultPaths(const FString& DataId, FString& OutPngDir, FString& OutJsonDir) const;

	/** 配置管理器引用 (UPROPERTY 保证被 GC 追踪, 防止被回收) */
	UPROPERTY()
	UConfigManager* ConfigManager;

	/** 文件管理器引用 */
	UPROPERTY()
	UFileManager* FileManager;

	// ===== 下载状态 =====
	TQueue<TPair<FString, FString>> PendingDownloads;  // 待下载队列, 元素为 <DataId, 远端文件路径>
	FString ActiveDownloadDataId;                      // 当前正在下载的数据 ID
	FString ActiveDownloadFilePath;                    // 当前正在下载的远端文件路径
	bool bIsDownloading;                               // 是否有下载正在进行 (串行锁)
	int32 DownloadRetryCount;                          // 当前任务已重试次数

	// ===== 上传状态 =====
	TQueue<FString> PendingUploads;	 // 待上传队列, 元素为 DataId
	FString ActiveUploadDataId;      // 当前正在上传的数据 ID
	bool bIsUploading;               // 是否有上传正在进行 (串行锁)
	int32 UploadRetryCount;          // 当前任务已重试次数

	// ===== 配置常量 =====
	static constexpr int32 MaxRetryTimes = 3;  // 下载/上传的最大重试次数
};