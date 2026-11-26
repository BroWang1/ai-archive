#pragma once

#include "CoreMinimal.h"

// UHT (Unreal Header Tool) 自动生成的头文件, 必须放在所有自定义声明之后、本文件最后一个 include
// 它为带有 UCLASS/UPROPERTY/UFUNCTION 宏的类型生成反射相关的样板代码
#include "FileManager.generated.h"

// 声明一个专用的日志分类 LogLQARestoreFile, 供本模块文件操作打印日志使用
// 参数依次为: 分类名、默认日志等级 (Log)、编译期允许的最高等级 (All)
// EXTERN 表示仅声明, 真正的定义在 .cpp 中通过 DEFINE_LOG_CATEGORY 完成
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreFile, Log, All);

/**
 * LQA 还原工具的文件系统操作管理器
 * 负责文件读写（I/O）、目录操作, 以及 JSON 文件的加载与处理
 * 继承自 UObject, 可纳入 UE 的垃圾回收 (GC) 与反射系统管理
 */
UCLASS()
class LQARESTORE_API UFileManager : public UObject
{
	// UE 反射系统所需的样板宏, 为该类注入生成代码
	GENERATED_BODY()

public:
	/**
	 * 递归查找某个目录下的所有 JSON 文件
	 * @param Path         要搜索的目录路径 (可为相对路径, 内部会转为绝对路径)
	 * @param OutJsonFiles 输出参数, 用于接收找到的所有 JSON 文件的完整路径
	 */
	void FindJsonFilesRecursive(const FString& Path, TArray<FString>& OutJsonFiles);

	/**
	 * 根据传入路径解析出待处理的文件列表
	 * 支持两种情况: 传入的是单个文件, 或传入的是一个目录 (此时递归收集其中的 JSON)
	 * @param DumpFilePath 文件路径或目录路径
	 * @param OutFilePaths 输出参数, 用于接收解析得到的文件路径列表
	 */
	void GetFilePaths(const FString& DumpFilePath, TArray<FString>& OutFilePaths);

	/**
	 * 将 JSON 内容保存为一个 dump 数据文件
	 * @param DataId      数据标识符, 用于生成文件名 (格式为 "LQA_{DataId}.json")
	 * @param JsonContent 要写入文件的 JSON 字符串内容
	 * @param SaveDir     文件保存所在的目录
	 * @return 保存成功时返回文件的完整路径; 失败时返回空字符串
	 */
	FString SaveDumpDataToFile(const FString& DataId, const FString& JsonContent, const FString& SaveDir);

	/**
	 * 加载并解析一个 JSON 文件
	 * @param FilePath JSON 文件的路径
	 * @return 解析成功返回 JSON 对象; 文件不存在、读取失败或解析失败时返回 nullptr
	 */
	TSharedPtr<FJsonObject> LoadJsonFromFile(const FString& FilePath);

	/**
	 * 检查指定 DataId 对应的 dump 文件是否存在
	 * @param DataId  数据标识符
	 * @param SaveDir 要检查的目录
	 * @return 若对应的 dump 文件存在则返回 true
	 */
	bool DumpFileExists(const FString& DataId, const FString& SaveDir) const;

	/**
	 * 删除一个目录及其全部内容
	 * @param DirectoryPath 要删除的目录路径
	 * @return 删除成功或目录本就不存在时返回 true; 删除失败返回 false
	 */
	bool DeleteDirectory(const FString& DirectoryPath);

	/**
	 * 确保某个目录存在, 如不存在则创建它 (含多级父目录)
	 * @param DirectoryPath 目录路径
	 * @return 目录已存在或创建成功返回 true; 创建失败返回 false
	 */
	bool EnsureDirectoryExists(const FString& DirectoryPath);

private:
	/**
	 * 根据 DataId 和目录拼装出 dump 文件的完整路径
	 * 规则: {SaveDir}/LQAData/LQA_{DataId}.json
	 * @param DataId  数据标识符
	 * @param SaveDir 基础保存目录
	 * @return 拼装好的完整文件路径
	 */
	FString GetDumpFilePath(const FString& DataId, const FString& SaveDir) const;
};