#include "Core/FileManager.h"

#include "HAL/PlatformFileManager.h"        // 平台文件系统抽象层, 用于创建目录树等操作
#include "Misc/FileHelper.h"                // 提供字符串与文件互相读写的便捷函数
#include "Misc/Paths.h"                     // 路径处理工具 (拼接、判断存在性、取路径等)
#include "Serialization/JsonSerializer.h"   // JSON 序列化/反序列化支持

// 定义 (实现) 在头文件中声明的日志分类, 使其在本翻译单元中真正生效
DEFINE_LOG_CATEGORY(LogLQARestoreFile);

// 递归查找目录下所有 JSON 文件
void UFileManager::FindJsonFilesRecursive(const FString& Path, TArray<FString>& OutJsonFiles)
{
	// 将可能的相对路径转换为绝对路径, 便于日志输出和存在性校验
	const FString FullDirectoryPath = FPaths::ConvertRelativePathToFull(Path);

	// 目录不存在时直接报错返回, 避免后续无效操作
	if (!IFileManager::Get().DirectoryExists(*FullDirectoryPath))
	{
		UE_LOG(LogLQARestoreFile, Error, TEXT("Directory not found: %s"), *FullDirectoryPath);
		return;
	}

	// 递归查找所有扩展名为 .json 的文件:
	// 参数 Files=true 表示查找文件, Directories=false 表示不收集目录本身
	IFileManager::Get().FindFilesRecursive(OutJsonFiles, *Path, TEXT("*.json"), true, false);

	UE_LOG(LogLQARestoreFile, Log, TEXT("Found %d JSON files in: %s"), OutJsonFiles.Num(), *Path);
}

// 根据传入路径 (文件或目录) 解析出待处理文件列表
void UFileManager::GetFilePaths(const FString& DumpFilePath, TArray<FString>& OutFilePaths)
{
	// 情况一: 传入的是一个已存在的文件, 直接加入结果列表
	if (FPaths::FileExists(DumpFilePath))
	{
		OutFilePaths.Add(DumpFilePath);
	}
	// 情况二: 传入的是一个目录, 递归收集其中的所有 JSON 文件
	else if (FPaths::DirectoryExists(DumpFilePath))
	{
		IFileManager::Get().FindFilesRecursive(OutFilePaths, *DumpFilePath, TEXT("*.json"), true, false);
	}
	// 情况三: 路径既不是文件也不是目录, 记录警告
	else
	{
		UE_LOG(LogLQARestoreFile, Warning, TEXT("Path does not exist: %s"), *DumpFilePath);
	}
}

// 将 JSON 内容保存为 dump 文件
FString UFileManager::SaveDumpDataToFile(const FString& DataId, const FString& JsonContent, const FString& SaveDir)
{
	// 依据 DataId 和目录生成完整的目标文件路径
	const FString OutputFilePath = GetDumpFilePath(DataId, SaveDir);
	// 取出该文件所在的目录部分
	const FString OutputDir = FPaths::GetPath(OutputFilePath);

	// 写入前先确保目标目录存在 (必要时创建)
	EnsureDirectoryExists(OutputDir);

	// 将 JSON 字符串写入文件, 成功则返回文件路径
	if (FFileHelper::SaveStringToFile(JsonContent, *OutputFilePath))
	{
		UE_LOG(LogLQARestoreFile, Log, TEXT("Dump data saved: %s"), *OutputFilePath);
		return OutputFilePath;
	}

	// 写入失败时记录错误并返回空字符串
	UE_LOG(LogLQARestoreFile, Error, TEXT("Failed to save dump data: %s"), *OutputFilePath);
	return FString();
}

// 加载并解析 JSON 文件
TSharedPtr<FJsonObject> UFileManager::LoadJsonFromFile(const FString& FilePath)
{
	// 文件不存在, 提前返回空指针
	if (!FPaths::FileExists(FilePath))
	{
		UE_LOG(LogLQARestoreFile, Warning, TEXT("JSON file not found: %s"), *FilePath);
		return nullptr;
	}

	// 将整个文件内容读入字符串; 读取失败则返回空指针
	FString JsonStr;
	if (!FFileHelper::LoadFileToString(JsonStr, *FilePath))
	{
		UE_LOG(LogLQARestoreFile, Error, TEXT("Failed to load JSON file: %s"), *FilePath);
		return nullptr;
	}

	// 创建 JSON 读取器, 并将字符串反序列化为 JSON 对象
	TSharedPtr<FJsonObject> JsonObject;
	const TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonStr);

	// 反序列化失败或结果无效时, 返回空指针
	if (!FJsonSerializer::Deserialize(JsonReader, JsonObject) || !JsonObject.IsValid())
	{
		UE_LOG(LogLQARestoreFile, Error, TEXT("Failed to parse JSON file: %s"), *FilePath);
		return nullptr;
	}

	return JsonObject;
}

// 判断指定 DataId 对应的 dump 文件是否存在
bool UFileManager::DumpFileExists(const FString& DataId, const FString& SaveDir) const
{
	// 复用路径生成逻辑, 再判断文件是否存在
	const FString FilePath = GetDumpFilePath(DataId, SaveDir);
	return FPaths::FileExists(FilePath);
}

// 删除目录及其全部内容
bool UFileManager::DeleteDirectory(const FString& DirectoryPath)
{
	// 目录本就不存在, 视为删除成功
	if (!FPaths::DirectoryExists(DirectoryPath))
	{
		return true;
	}

	// 删除目录: RequireExists=false (不强制要求存在), Tree=true (递归删除子目录与文件)
	const bool bSuccess = IFileManager::Get().DeleteDirectory(*DirectoryPath, false, true);
	if (!bSuccess)
	{
		UE_LOG(LogLQARestoreFile, Warning, TEXT("Failed to delete directory: %s"), *DirectoryPath);
	}

	return bSuccess;
}

// 确保目录存在, 不存在则创建
bool UFileManager::EnsureDirectoryExists(const FString& DirectoryPath)
{
	// 目录已存在, 无需创建。
	if (FPaths::DirectoryExists(DirectoryPath))
	{
		return true;
	}

	// 创建完整的目录树 (会自动创建缺失的多级父目录)
	const bool bSuccess = FPlatformFileManager::Get().GetPlatformFile().CreateDirectoryTree(*DirectoryPath);
	if (!bSuccess)
	{
		UE_LOG(LogLQARestoreFile, Error, TEXT("Failed to create directory: %s"), *DirectoryPath);
	}

	return bSuccess;
}

// 生成 dump 文件的完整路径: {SaveDir}/LQAData/LQA_{DataId}.json
FString UFileManager::GetDumpFilePath(const FString& DataId, const FString& SaveDir) const
{
	// 先在基础目录下拼出专用子目录 LQAData
	const FString LQADataDir = FPaths::Combine(SaveDir, TEXT("LQAData"));
	// 再拼上以 DataId 命名的 JSON 文件名
	return FPaths::Combine(LQADataDir, FString::Printf(TEXT("LQA_%s.json"), *DataId));
}