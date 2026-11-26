#include "Utils/LQACommonUtil.h"

#include "HAL/PlatformFilemanager.h" // 提供平台文件管理器, 用于路径转换
#include "HAL/PlatformMisc.h"        // 提供平台杂项接口, 用于获取系统/设备信息
#include "Misc/App.h"                // 提供应用信息, 如项目名称
#include "Misc/ConfigCacheIni.h"     // 提供配置文件 (ini) 读取能力
#include "Misc/Paths.h"              // 提供路径相关工具函数

// 定义 (实现) 在头文件中声明的日志分类
DEFINE_LOG_CATEGORY(LogLQAToolCommonUtil);

// 获取游戏 Saved 存档目录的绝对路径, 根据不同平台采用不同的获取逻辑
FString FLQACommonUtil::GetGameSavedPath()
{
	FString SavedPath;

#if PLATFORM_ANDROID
	// ------- Android 平台 -------
	// Android 上 Saved 目录位于持久化下载目录下, 需要用项目名拼接出完整路径

	// 获取项目名称, 若为空则无法构造路径, 直接返回空字符串
	const FString ProjectName = FApp::GetProjectName();
	if (ProjectName.IsEmpty())
	{
		UE_LOG(LogLQAToolCommonUtil, Error, TEXT("Project name is empty"));
		return FString();
	}

	// 获取持久化下载目录, 若为空同样无法构造路径
	const FString PersistentDownloadDir = FPaths::ProjectPersistentDownloadDir();
	if (PersistentDownloadDir.IsEmpty())
	{
		UE_LOG(LogLQAToolCommonUtil, Error, TEXT("Persistent download directory is empty"));
		return FString();
	}

	// 拼接出 Android 下的 Saved 目录完整路径
	SavedPath = PersistentDownloadDir / TEXT("UEGame") / ProjectName / ProjectName / TEXT("Saved");

#elif PLATFORM_IOS
	// ------- iOS 平台 -------
	// 先获取项目 Saved 目录
	SavedPath = FPaths::ProjectSavedDir();
	if (!IsValidPath(SavedPath))
	{
		UE_LOG(LogLQAToolCommonUtil, Error, TEXT("Invalid iOS saved directory: %s"), *SavedPath);
		return FString();
	}

	// iOS 的沙盒机制特殊, 需要将路径转换为可供外部应用读取的绝对路径
	SavedPath =
		FPlatformFileManager::Get().GetPlatformFile().GetPlatformPhysical().ConvertToAbsolutePathForExternalAppForRead(
			*SavedPath);

#else
	// ------- 其他平台 (Windows / Mac / Linux 等) -------
	// 直接获取项目 Saved 目录
	SavedPath = FPaths::ProjectSavedDir();
	if (!IsValidPath(SavedPath))
	{
		UE_LOG(LogLQAToolCommonUtil, Error, TEXT("Invalid saved directory: %s"), *SavedPath);
		return FString();
	}

	// 将相对路径转换为绝对路径
	SavedPath = FPaths::ConvertRelativePathToFull(SavedPath);
#endif

	// 最终统一的路径合法性校验, 确保返回的路径有效
	if (!IsValidPath(SavedPath))
	{
		UE_LOG(LogLQAToolCommonUtil, Error, TEXT("Final path validation failed: %s"), *SavedPath);
		return FString();
	}

	return SavedPath;
}

// 收集当前设备的系统信息, 并拼接为 URL 查询参数格式的字符串
FString FLQACommonUtil::GetSystemInfo()
{
	// 获取平台名称
	const FString Platform = GetCurrentPlatformName();
	// 获取操作系统版本 (为空时回退为 Unknown)
	const FString OSVersion = GetSafeStringValue(FPlatformMisc::GetOSVersion());
	// 获取设备厂商与型号 (为空时回退为 Unknown)
	const FString DeviceMakeAndModel = GetSafeStringValue(FPlatformMisc::GetDeviceMakeAndModel());
	// 获取 CPU 厂商信息 (为空时回退为 Unknown)
	const FString CPUInfo = GetSafeStringValue(FPlatformMisc::GetCPUVendor());

	// 将各项信息进行 URL 编码后, 按 key=value&key=value 的格式拼接返回
	return FString::Printf(TEXT("Platform=%s&OSVersion=%s&DeviceMake=%s&CPUInfo=%s"), *UrlEncodeString(Platform),
		*UrlEncodeString(OSVersion), *UrlEncodeString(DeviceMakeAndModel), *UrlEncodeString(CPUInfo));
}

// 从项目配置 (ini) 中读取客户端版本号
FString FLQACommonUtil::GetClientVersion()
{
	FString ClientVersion;

	// 从 GameIni 的 GeneralProjectSettings 配置段中读取 ProjectVersion 字段
	if (GConfig && GConfig->GetString(TEXT("/Script/EngineSettings.GeneralProjectSettings"), TEXT("ProjectVersion"),
					   ClientVersion, GGameIni))
	{
		// 读取成功且非空时才返回
		if (!ClientVersion.IsEmpty())
		{
			return ClientVersion;
		}
	}

	// 读取失败或为空时, 返回默认版本号
	return DEFAULT_VERSION;
}

// 对字符串进行 URL 编码, 转义会影响 URL 解析的特殊字符
FString FLQACommonUtil::UrlEncodeString(const FString& InputString)
{
	// 空字符串无需处理, 直接返回
	if (InputString.IsEmpty())
	{
		return InputString;
	}

	// 依次替换特殊字符为对应的百分号编码:
	// & -> %26、= -> %3D、空格 -> %20、# -> %23、? -> %3F
	return InputString.Replace(TEXT("&"), TEXT("%26"))
		.Replace(TEXT("="), TEXT("%3D"))
		.Replace(TEXT(" "), TEXT("%20"))
		.Replace(TEXT("#"), TEXT("%23"))
		.Replace(TEXT("?"), TEXT("%3F"));
}

// 返回安全字符串: 若原值为空则返回默认值, 避免出现空字段
FString FLQACommonUtil::GetSafeStringValue(const FString& Value, const FString& DefaultValue)
{
	return Value.IsEmpty() ? DefaultValue : Value;
}

// 校验路径是否合法: 必须非空, 且长度大于设定的最小长度
bool FLQACommonUtil::IsValidPath(const FString& Path)
{
	return !Path.IsEmpty() && Path.Len() > MIN_PATH_LENGTH;
}

// 根据编译期的平台宏, 返回当前运行平台的名称字符串
FString FLQACommonUtil::GetCurrentPlatformName()
{
#if PLATFORM_ANDROID
	return TEXT("Android");
#elif PLATFORM_IOS
	return TEXT("iOS");
#elif PLATFORM_WINDOWS
	return TEXT("Windows");
#elif PLATFORM_MAC
	return TEXT("Mac");
#elif PLATFORM_LINUX
	return TEXT("Linux");
#else
	return TEXT("Unknown");
#endif
}