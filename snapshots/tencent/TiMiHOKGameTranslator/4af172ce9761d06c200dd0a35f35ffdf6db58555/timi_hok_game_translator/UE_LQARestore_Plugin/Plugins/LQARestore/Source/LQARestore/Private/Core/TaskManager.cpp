#include "Core/TaskManager.h"

#include "Core/ConfigManager.h"
#include "Core/FileManager.h"
#include "Serialization/JsonSerializer.h"              // JSON 序列化/反序列化
#include "Utils/HttpUtils/HttpRequestHelper.h"         // 封装的 HTTP 请求辅助类
#include "zlib.h"                                       // gzip 解压所需的 zlib 库

// 定义头文件中声明的日志分类 (每个分类在整个工程中仅能定义一次)
DEFINE_LOG_CATEGORY(LogLQARestoreTask);

// 匿名命名空间: 仅在本编译单元内可见的常量, 避免污染全局命名空间
namespace
{
constexpr int32 InitialDecompressionBufferSize = 1024 * 1024;  // 解压缓冲区初始大小: 1MB
constexpr int32 DecompressionGrowthFactor = 2;                 // 缓冲区不足时的扩容倍数
}

void UTaskManager::Initialize(UConfigManager* InConfigManager, UFileManager* InFileManager)
{
	// 保存依赖引用并将所有运行时状态重置为初始值
	ConfigManager = InConfigManager;
	FileManager = InFileManager;
	bIsDownloading = false;
	bIsUploading = false;
	DownloadRetryCount = 0;
	UploadRetryCount = 0;
	UE_LOG(LogLQARestoreTask, Log, TEXT("TaskManager Initialized"));
}

void UTaskManager::RequestJobData(bool bIsFirstRequest)
{
	// 前置校验: 配置管理器必须有效
	if (!ConfigManager)
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("ConfigManager is null"));
		return;
	}

	// JobId 为 "0" 表示无有效任务, 直接跳过请求
	const FString& JobId = ConfigManager->GetJobId();
	if (JobId == TEXT("0"))
	{
		UE_LOG(LogLQARestoreTask, Warning, TEXT("JobId is 0, skipping job data request"));
		return;
	}

	// 发起获取任务数据的 HTTP 请求, 所有查询参数均来自配置管理器
	FHttpRequestHelper::GetJobData(JobId, ConfigManager->GetRegression(), ConfigManager->GetLanguage(),
		ConfigManager->GetDefaultNums(), ConfigManager->GetMinID(), ConfigManager->GetModules());

	// 使用弱指针捕获 this, 防止在异步回调触发时对象已被销毁而产生悬空访问
	TWeakObjectPtr<UTaskManager> WeakThis(this);
	FHttpRequestHelper::OnRequestSuccess.BindLambda(
		[WeakThis](FHttpResponsePtr ResponsePtr)
		{
			// 回调执行前再次确认对象仍然有效
			if (WeakThis.IsValid())
			{
				WeakThis->OnJobDataSuccess(ResponsePtr);
			}
		});
}

void UTaskManager::OnJobDataSuccess(FHttpResponsePtr Response)
{
	// 响应有效性校验
	if (!Response.IsValid())
	{
		UE_LOG(LogLQARestoreTask, Warning, TEXT("Job data response is invalid"));
		return;
	}

	const int32 ResponseCode = Response->GetResponseCode();
	const FString ResponseData = Response->GetContentAsString();

	// 非 2xx: 直接暴露状态码与响应体前 500 字符 (便于识别 HTML 错误页 / 鉴权失败等)
	if (ResponseCode < 200 || ResponseCode >= 300)
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("Job data HTTP error: %d, Body: %s"), ResponseCode,
			*ResponseData.Left(500));
		return;
	}

	// 将响应体内容解析为 JSON 对象
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(ResponseData);

	if (!FJsonSerializer::Deserialize(JsonReader, JsonObject) || !JsonObject.IsValid())
	{
		// 解析失败时打印响应码与响应体预览 (如误把前端 HTML 当成 JSON 即可一眼看出)
		UE_LOG(LogLQARestoreTask, Error, TEXT("Failed to parse job data response. Code: %d, Preview: %s"),
			ResponseCode, *ResponseData.Left(500));
		return;
	}

	// 取出外层的 "data" 对象字段
	const TSharedPtr<FJsonObject>* DataObject;
	if (!JsonObject->TryGetObjectField(TEXT("data"), DataObject) || !DataObject->IsValid())
	{
		UE_LOG(LogLQARestoreTask, Warning, TEXT("No data field in job data response"));
		return;
	}

	// 取出 "data.datas" 数组字段, 其中每个元素是一条任务记录
	const TArray<TSharedPtr<FJsonValue>>* DataList;
	if (!(*DataObject)->TryGetArrayField(TEXT("datas"), DataList))
	{
		return;
	}

	// 预分配容器大小, 减少动态扩容开销
	TArray<FString> IdList;
	TArray<FString> IdPathList;
	IdList.Reserve(DataList->Num());
	IdPathList.Reserve(DataList->Num());

	// 遍历每条任务记录, 提取 id 与 file_path 字段
	for (const TSharedPtr<FJsonValue>& Value : *DataList)
	{
		const TSharedPtr<FJsonObject>& DataItem = Value->AsObject();
		if (DataItem.IsValid())
		{
			IdList.Add(DataItem->GetStringField(TEXT("id")));
			IdPathList.Add(DataItem->GetStringField(TEXT("file_path")));
		}
	}

	// 广播任务数据, 通知外部监听者进行后续处理 (如入队下载)
	UE_LOG(LogLQARestoreTask, Log, TEXT("Received %d job data items"), IdList.Num());
	OnJobDataReceived.Broadcast(IdList, IdPathList);
}

void UTaskManager::EnqueueDownload(const FString& DataId, const FString& FilePath)
{
	// 将 <DataId, 远端路径> 作为一个二元组加入下载队列
	PendingDownloads.Enqueue(MakeTuple(DataId, FilePath));
}

void UTaskManager::ProcessDownloadQueue()
{
	// 若正在下载或依赖未就绪, 则不启动新的下载 (保证串行执行)
	if (bIsDownloading || !FileManager || !ConfigManager)
	{
		return;
	}

	// 从队列取出下一个待下载项: 队列为空则直接返回
	TPair<FString, FString> DownloadItem;
	if (!PendingDownloads.Dequeue(DownloadItem))
	{
		return;
	}

	// 使用 MoveTemp 避免字符串拷贝, 记录当前活动下载任务信息
	ActiveDownloadDataId = MoveTemp(DownloadItem.Key);
	ActiveDownloadFilePath = MoveTemp(DownloadItem.Value);

	// 若本地已存在对应 dump 文件, 则跳过下载并直接视为成功 (FilePath 传空表示复用已有文件)
	if (FileManager->DumpFileExists(ActiveDownloadDataId, ConfigManager->GetPngSaveRootDir()))
	{
		UE_LOG(LogLQARestoreTask, Log, TEXT("Dump file already exists: %s"), *ActiveDownloadDataId);
		OnDumpDataDownloaded.Broadcast(ActiveDownloadDataId, FString());
		return;
	}

	// 置下载标志位, 加锁防止并发下载
	bIsDownloading = true;
	UE_LOG(LogLQARestoreTask, Log, TEXT("Downloading dump data: %s"), *ActiveDownloadDataId);

	// 发起下载请求
	FHttpRequestHelper::GetDumpData(ActiveDownloadDataId, ActiveDownloadFilePath);

	// 绑定成功/失败回调 (弱指针保护, 防止悬空访问)
	TWeakObjectPtr<UTaskManager> WeakThis(this);
	FHttpRequestHelper::OnRequestSuccessForDump.BindLambda(
		[WeakThis](FHttpResponsePtr ResponsePtr)
		{
			if (WeakThis.IsValid())
			{
				WeakThis->OnDownloadSuccess(ResponsePtr);
			}
		});

	FHttpRequestHelper::OnRequestFailForDump.BindLambda(
		[WeakThis]()
		{
			if (WeakThis.IsValid())
			{
				WeakThis->OnDownloadFail();
			}
		});
}

void UTaskManager::OnDownloadSuccess(FHttpResponsePtr Response)
{
	// 响应无效, 转入失败处理 (可能触发重试)
	if (!Response.IsValid())
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("Response is invalid: %s"), *ActiveDownloadDataId);
		OnDownloadFail();
		return;
	}

	// 校验 HTTP 状态码是否为 2xx 成功区间
	const int32 ResponseCode = Response->GetResponseCode();
	UE_LOG(LogLQARestoreTask, Log, TEXT("Download response code: %d, DataId: %s"), ResponseCode, *ActiveDownloadDataId);

	if (ResponseCode < 200 || ResponseCode >= 300)
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("HTTP error response: %d, Content: %s"), ResponseCode,
			*Response->GetContentAsString());
		OnDownloadFail();
		return;
	}

	// 获取响应二进制内容
	const TArray<uint8>& CompressedData = Response->GetContent();
	UE_LOG(LogLQARestoreTask, Log, TEXT("Downloaded data size: %d bytes"), CompressedData.Num());

	// 空数据视为失败
	if (CompressedData.Num() == 0)
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("Download data is empty: %s"), *ActiveDownloadDataId);
		OnDownloadFail();
		return;
	}

	// 通过文件头魔数 (0x1f 0x8b) 判断数据是否为 gzip 压缩格式
	if (CompressedData.Num() >= 2)
	{
		const bool bIsGzip = (CompressedData[0] == 0x1f && CompressedData[1] == 0x8b);
		UE_LOG(LogLQARestoreTask, Log, TEXT("Data format check - IsGzip: %s, First bytes: %02X %02X"),
			bIsGzip ? TEXT("Yes") : TEXT("No"), CompressedData[0], CompressedData[1]);

		if (!bIsGzip)
		{
			// 非 gzip: 按未压缩的原始 JSON 文本处理
			FString JsonString(UTF8_TO_TCHAR(CompressedData.GetData()));
			UE_LOG(LogLQARestoreTask, Warning, TEXT("Data is not gzip compressed, treating as raw JSON"));

			// 校验 JSON 合法性
			TSharedPtr<FJsonObject> JsonObject;
			const TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonString);
			if (!FJsonSerializer::Deserialize(JsonReader, JsonObject) || !JsonObject.IsValid())
			{
				// 打印前 200 字符便于定位非法数据
				UE_LOG(LogLQARestoreTask, Error, TEXT("Invalid JSON data (raw): %s, Preview: %s"), *ActiveDownloadDataId,
					*JsonString.Left(200));
				OnDownloadFail();
				return;
			}

			// 保存到本地文件
			const FString SavedPath =
				FileManager->SaveDumpDataToFile(ActiveDownloadDataId, JsonString, ConfigManager->GetPngSaveRootDir());
			if (SavedPath.IsEmpty())
			{
				OnDownloadFail();
				return;
			}

			// 下载成功: 重置重试计数、释放下载锁并广播结果
			UE_LOG(LogLQARestoreTask, Log, TEXT("Download success (raw JSON): %s"), *ActiveDownloadDataId);
			DownloadRetryCount = 0;
			bIsDownloading = false;
			OnDumpDataDownloaded.Broadcast(ActiveDownloadDataId, SavedPath);
			return;
		}
	}

	// gzip 数据: 执行解压
	TArray<uint8> DecompressedData;
	if (!DecompressGzipData(CompressedData, DecompressedData))
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("Failed to decompress gzip data: %s"), *ActiveDownloadDataId);
		OnDownloadFail();
		return;
	}

	// 将解压后的字节转为字符串, 并截断到最后一个 '}' 为止
	// (防止解压缓冲区尾部残留的未初始化/填充字节导致 JSON 解析失败)
	FString JsonString(UTF8_TO_TCHAR(DecompressedData.GetData()));
	int32 LastBraceIndex;
	if (JsonString.FindLastChar(TCHAR('}'), LastBraceIndex))
	{
		JsonString.LeftInline(LastBraceIndex + 1);
	}

	// 校验 JSON 合法性
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonString);
	if (!FJsonSerializer::Deserialize(JsonReader, JsonObject) || !JsonObject.IsValid())
	{
		UE_LOG(LogLQARestoreTask, Error, TEXT("Invalid JSON data: %s"), *ActiveDownloadDataId);
		OnDownloadFail();
		return;
	}

	// 保存到本地文件
	const FString SavedPath =
		FileManager->SaveDumpDataToFile(ActiveDownloadDataId, JsonString, ConfigManager->GetPngSaveRootDir());
	if (SavedPath.IsEmpty())
	{
		OnDownloadFail();
		return;
	}

	// 下载成功: 重置重试计数、释放下载锁并广播结果
	UE_LOG(LogLQARestoreTask, Log, TEXT("Download success: %s"), *ActiveDownloadDataId);
	DownloadRetryCount = 0;
	bIsDownloading = false;
	OnDumpDataDownloaded.Broadcast(ActiveDownloadDataId, SavedPath);
}

void UTaskManager::OnDownloadFail()
{
	// 累加重试计数
	++DownloadRetryCount;
	UE_LOG(LogLQARestoreTask, Error, TEXT("Download failed: %s (Retry: %d/%d)"), *ActiveDownloadDataId, DownloadRetryCount,
		MaxRetryTimes);

	if (DownloadRetryCount < MaxRetryTimes)
	{
		// 未达最大重试次数: 将任务重新入队, 等待下一轮调度
		PendingDownloads.Enqueue(MakeTuple(ActiveDownloadDataId, ActiveDownloadFilePath));
	}
	else
	{
		// 达到最大重试次数: 重置计数并广播最终失败
		DownloadRetryCount = 0;
		OnDumpDataFailed.Broadcast(ActiveDownloadDataId);
	}

	// 释放下载锁, 允许处理队列中的下一个任务
	bIsDownloading = false;
}

bool UTaskManager::DecompressGzipData(const TArray<uint8>& CompressedData, TArray<uint8>& OutDecompressedData)
{
	// 初始化 zlib 解压流结构体并清零
	z_stream strm;
	FMemory::Memset(&strm, 0, sizeof(strm));
	strm.zalloc = Z_NULL;   // 使用 zlib 默认内存分配器
	strm.zfree = Z_NULL;
	strm.opaque = Z_NULL;

	// inflateInit2 的窗口位参数: 16 + MAX_WBITS 表示启用 gzip 头解析
	if (inflateInit2(&strm, 16 + MAX_WBITS) != Z_OK)
	{
		return false;
	}

	// 设置输入缓冲区指针与长度 (const_cast 去掉常量性以符合 zlib C 接口要求)
	strm.avail_in = CompressedData.Num();
	strm.next_in = const_cast<Bytef*>(CompressedData.GetData());

	// 预分配输出缓冲区, 取 输入大小 与 1MB 中较大者, 减少后续扩容次数
	const int32 EstimatedSize = FMath::Max(CompressedData.Num(), InitialDecompressionBufferSize);
	OutDecompressedData.Reserve(EstimatedSize);
	OutDecompressedData.AddUninitialized(EstimatedSize);

	int32 Result;
	do
	{
		// 根据已输出字节数更新输出游标与剩余可写空间
		strm.avail_out = OutDecompressedData.Num() - strm.total_out;
		strm.next_out = OutDecompressedData.GetData() + strm.total_out;

		// 执行解压
		Result = inflate(&strm, Z_NO_FLUSH);

		// 解压完成
		if (Result == Z_STREAM_END)
		{
			break;
		}

		// 出错: 清理流、清空输出并返回失败
		if (Result != Z_OK)
		{
			inflateEnd(&strm);
			OutDecompressedData.Empty();
			return false;
		}

		// 输出缓冲区已满但数据未解压完: 按增长因子扩容后继续
		if (strm.avail_out == 0)
		{
			const int32 NewSize = OutDecompressedData.Num() * DecompressionGrowthFactor;
			OutDecompressedData.AddUninitialized(NewSize - OutDecompressedData.Num());
		}
	} while (true);

	// 释放解压流资源, 并将输出数组裁剪为实际解压出的字节数
	inflateEnd(&strm);
	OutDecompressedData.SetNum(strm.total_out);
	return true;
}

void UTaskManager::EnqueueUpload(const FString& DataId)
{
	// 将 DataId 加入上传队列
	PendingUploads.Enqueue(DataId);
}

void UTaskManager::GetRestoreResultPaths(const FString& DataId, FString& OutPngDir, FString& OutJsonDir) const
{
	// 结果目录命名规则: Restore_<DataId>_<语言>
	const FString DirName = FString::Printf(TEXT("Restore_%s_%s"), *DataId, *ConfigManager->GetLanguage());
	// 完整路径: <PNG根目录>/LQAResult/<DirName>
	OutPngDir = FPaths::Combine(ConfigManager->GetPngSaveRootDir(), TEXT("LQAResult"), DirName);
	// 当前实现 PNG 与 JSON 文件位于同一目录
	OutJsonDir = OutPngDir;
}

void UTaskManager::ProcessUploadQueue()
{
	// 若正在上传或依赖未就绪, 则不启动新的上传 (保证串行执行)
	if (bIsUploading || !FileManager || !ConfigManager)
	{
		return;
	}

	// 从队列取出下一个待上传的 DataId；队列为空则返回
	if (!PendingUploads.Dequeue(ActiveUploadDataId))
	{
		return;
	}

	// 置上传标志位, 加锁防止并发上传
	bIsUploading = true;
	UE_LOG(LogLQARestoreTask, Log, TEXT("Uploading restore result: %s"), *ActiveUploadDataId);

	// 计算该数据对应的结果目录
	FString PngDirectoryPath, JsonDirectoryPath;
	GetRestoreResultPaths(ActiveUploadDataId, PngDirectoryPath, JsonDirectoryPath);

	// 结果目录不存在, 视为上传失败
	if (!FPaths::DirectoryExists(PngDirectoryPath))
	{
		UE_LOG(LogLQARestoreTask, Warning, TEXT("Result directory not found: %s"), *PngDirectoryPath);
		OnUploadFail();
		return;
	}

	// 分别查找目录下的 PNG 与 JSON 文件
	TArray<FString> PngFiles;
	TArray<FString> JsonFiles;
	IFileManager& FileManagerRef = IFileManager::Get();
	FileManagerRef.FindFiles(PngFiles, *PngDirectoryPath, TEXT("png"));
	FileManagerRef.FindFiles(JsonFiles, *JsonDirectoryPath, TEXT("json"));

	// PNG 或 JSON 缺失则无法上传
	if (PngFiles.Num() == 0 || JsonFiles.Num() == 0)
	{
		UE_LOG(LogLQARestoreTask, Warning, TEXT("No PNG or JSON files found for upload: %s"), *ActiveUploadDataId);
		OnUploadFail();
		return;
	}

	// 取第一个 PNG 和第一个 JSON 文件作为本次上传内容
	const FString PngFilePath = FPaths::Combine(PngDirectoryPath, PngFiles[0]);
	const FString CheckInfoFilePath = FPaths::Combine(JsonDirectoryPath, JsonFiles[0]);

	// 发送还原结果请求, 参数均来自配置管理器
	FHttpRequestHelper::SendRestoreResult(ConfigManager->GetProjectId(), ConfigManager->GetJobId(), ActiveUploadDataId,
		CheckInfoFilePath, {PngFilePath}, ConfigManager->GetLanguage(), ConfigManager->GetRegression(),
		ConfigManager->GetCreateBug(), ConfigManager->GetBugId(), ConfigManager->GetAISign());

	// 弱指针捕获, 并按值捕获目录路径供回调中清理使用
	TWeakObjectPtr<UTaskManager> WeakThis(this);
	FHttpRequestHelper::OnRequestSuccessForSendResult.BindLambda(
		[WeakThis, PngDirectoryPath, JsonDirectoryPath](FHttpResponsePtr ResponsePtr)
		{
			if (!WeakThis.IsValid() || !ResponsePtr.IsValid())
			{
				return;
			}

			// 上传成功后删除本地结果目录以释放磁盘空间
			WeakThis->FileManager->DeleteDirectory(PngDirectoryPath);
			WeakThis->FileManager->DeleteDirectory(JsonDirectoryPath);
			WeakThis->OnUploadSuccess(ResponsePtr);
		});

	FHttpRequestHelper::OnRequestFailForSendResult.BindLambda(
		[WeakThis]()
		{
			if (WeakThis.IsValid())
			{
				WeakThis->OnUploadFail();
			}
		});
}

void UTaskManager::OnUploadSuccess(FHttpResponsePtr Response)
{
	// 上传成功: 重置重试计数、释放上传锁并广播结果
	UE_LOG(LogLQARestoreTask, Log, TEXT("Upload success: %s"), *ActiveUploadDataId);
	UploadRetryCount = 0;
	bIsUploading = false;
	OnRestoreResultUploaded.Broadcast(ActiveUploadDataId);
}

void UTaskManager::OnUploadFail()
{
	// 累加重试计数
	++UploadRetryCount;
	UE_LOG(LogLQARestoreTask, Error, TEXT("Upload failed: %s (Retry: %d/%d)"), *ActiveUploadDataId, UploadRetryCount,
		MaxRetryTimes);

	if (UploadRetryCount < MaxRetryTimes)
	{
		// 未达最大重试次数: 重新入队等待重试
		PendingUploads.Enqueue(ActiveUploadDataId);
	}
	else
	{
		// 达到最大重试次数: 重置计数并放弃 (注意: 此处未广播失败事件)
		UploadRetryCount = 0;
	}

	// 释放上传锁, 允许处理队列中的下一个任务
	bIsUploading = false;
}