#pragma once

#include "CoreMinimal.h"

// 声明一个名为 LogLQAToolCommonUtil 的外部日志分类 (供本类的 .cpp 及其他模块使用)
// 第二个参数 Log 为默认日志级别, 第三个参数 All 表示编译期允许输出的最高级别
DECLARE_LOG_CATEGORY_EXTERN(LogLQAToolCommonUtil, Log, All);

/**
 * LQA 工具通用工具类
 * 提供系统信息获取、路径处理、配置读取以及字符串编码等静态辅助方法
 * 本类为纯静态工具类, 无需实例化即可使用
 */
class LQATOOL_API FLQACommonUtil
{
public:
	/** 获取游戏的 Saved 存档目录的绝对路径 (会根据不同平台做差异化处理) */
	static FString GetGameSavedPath();

	/** 获取系统信息 (平台、操作系统版本、设备型号、CPU 信息), 并拼接为 URL 查询参数字符串 */
	static FString GetSystemInfo();

	/** 从项目配置文件中读取客户端版本号 */
	static FString GetClientVersion();

	/** 对字符串进行 URL 编码, 转义其中的特殊字符 */
	static FString UrlEncodeString(const FString& InputString);

private:
	// ---------- 常量定义 ----------

	/** 默认版本号: 当无法从配置中读取到版本时返回此值 */
	static constexpr const TCHAR* DEFAULT_VERSION = TEXT("0.0.0.0");

	/** 未知值占位符: 当某项系统信息为空时使用 */
	static constexpr const TCHAR* UNKNOWN_VALUE = TEXT("Unknown");

	/** 有效路径的最小长度 (用于路径合法性校验) */
	static constexpr int32 MIN_PATH_LENGTH = 1;

	/** 返回安全的字符串值: 若原值为空则返回默认值 (默认为 UNKNOWN_VALUE) */
	static FString GetSafeStringValue(const FString& Value, const FString& DefaultValue = UNKNOWN_VALUE);

	/** 校验路径字符串是否合法 (非空且长度大于最小长度) */
	static bool IsValidPath(const FString& Path);

	/** 获取当前运行平台的名称字符串 (如 Windows、Android、iOS 等) */
	static FString GetCurrentPlatformName();
};