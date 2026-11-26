#include "Utils/HttpUtils/HttpRequestConfig.h"

#include "Misc/ConfigCacheIni.h"       // 提供 GConfig, 用于读取 .ini 配置文件
#include "Interfaces/IPluginManager.h" // 提供 IPluginManager, 用于定位插件目录

// 为头文件中声明的日志分类提供唯一定义 (整个模块只能定义一次)
DEFINE_LOG_CATEGORY(LogLQARestoreHttp);

namespace HttpRequestConfig
{
// 全局配置变量的实际定义与初始值 (默认空字符串, 加载成功后被覆盖)
FString Host = TEXT("");
FString FileHost = TEXT("");
FString Authorization = TEXT("");

/**
 * 从插件的 Config/LQARestore.ini 读取 HTTP 配置并写入全局变量
 * 流程:
 *   1. 定位 LQARestore 插件;
 *   2. 拼接并校验配置文件绝对路径;
 *   3. 通过 GConfig 读取 [HttpConfig] 节下的 Host / Authorization
 * 任意步骤失败都会记录日志并安全返回, 不会抛出异常
 */
void Initialize()
{
	// 通过插件管理器查找名为 "LQARestore" 的插件实例
	const TSharedPtr<IPlugin> Plugin = IPluginManager::Get().FindPlugin(TEXT("LQARestore"));
	if (!Plugin.IsValid())
	{
		// 未找到插件 (例如插件未启用或名称不匹配), 无法继续加载配置
		UE_LOG(LogLQARestoreHttp, Error, TEXT("Plugin 'LQARestore' not found"));
		return;
	}

	// 以插件根目录为基准拼接配置文件路径, 并转换为绝对路径以保证可靠性
	const FString ConfigFile = FPaths::ConvertRelativePathToFull(Plugin->GetBaseDir() / TEXT("Config/LQARestore.ini"));

	UE_LOG(LogLQARestoreHttp, Log, TEXT("Attempting to load config from: %s"), *ConfigFile);

	// 文件不存在时仅警告并返回, 使用默认 (空) 配置
	if (!FPaths::FileExists(ConfigFile))
	{
		UE_LOG(LogLQARestoreHttp, Warning, TEXT("Config file not found: %s"), *ConfigFile);
		return;
	}

	UE_LOG(LogLQARestoreHttp, Log, TEXT("Config file found, loading..."));

	// 配置项所在的节 (section) 名称, 对应 .ini 中的 [HttpConfig]
	const FString ConfigSection = TEXT("HttpConfig");

	// GConfig 是引擎全局配置缓存, 正常运行期一般有效, 这里仍做空指针防护
	if (GConfig)
	{
		FString ConfigHost;
		FString ConfigAuth;

		// 读取 Host: 成功时自动补全 "http://" 前缀后写入全局 Host
		if (GConfig->GetString(*ConfigSection, TEXT("Host"), ConfigHost, ConfigFile))
		{
			Host = TEXT("http://") + ConfigHost;
			UE_LOG(LogLQARestoreHttp, Log, TEXT("Loaded Host: %s"), *Host);
		}
		else
		{
			// 缺少 Host 配置项, 保持默认空值
			UE_LOG(LogLQARestoreHttp, Warning, TEXT("Host not found in config"));
		}

		// 读取 FileHost (下载基址): 成功时补全 "http://" 前缀; 缺省时回退到 Host
		FString ConfigFileHost;
		if (GConfig->GetString(*ConfigSection, TEXT("FileHost"), ConfigFileHost, ConfigFile) &&
			!ConfigFileHost.IsEmpty())
		{
			FileHost = TEXT("http://") + ConfigFileHost;
			UE_LOG(LogLQARestoreHttp, Log, TEXT("Loaded FileHost: %s"), *FileHost);
		}
		else
		{
			// 未配置 FileHost 时, 回退使用 Host (保持旧行为的兼容)
			FileHost = Host;
			UE_LOG(LogLQARestoreHttp, Warning, TEXT("FileHost not found, fallback to Host: %s"), *FileHost);
		}

		// 读取 Authorization: 成功时写入全局 Authorization
		if (GConfig->GetString(*ConfigSection, TEXT("Authorization"), ConfigAuth, ConfigFile))
		{
			Authorization = ConfigAuth;
			// 出于安全考虑只打印长度, 不打印令牌内容本身, 避免泄露敏感信息
			UE_LOG(LogLQARestoreHttp, Log, TEXT("Loaded Authorization (length: %d)"), Authorization.Len());
		}
		else
		{
			// 缺少 Authorization 配置项, 保持默认空值
			UE_LOG(LogLQARestoreHttp, Warning, TEXT("Authorization not found in config"));
		}
	}
	else
	{
		// GConfig 不可用 (极少见, 通常是过早调用导致), 记录错误
		UE_LOG(LogLQARestoreHttp, Error, TEXT("GConfig is null"));
	}
}
}