#include "Core/ConfigManager.h"

#include "Misc/CommandLine.h" // 提供 FCommandLine::Get() 用于获取进程命令行
#include "Misc/Paths.h"       // 提供 FPaths 路径处理工具函数

// 定义 (实现) 在头文件中声明的日志分类, 整个模块中仅能定义一次
DEFINE_LOG_CATEGORY(LogLQARestoreConfig);

void UConfigManager::Initialize()
{
	// ---- 1. 初始化所有配置项的默认值 ----
	ProjectId = TEXT("0");
	JobId = TEXT("0");
	Language = TEXT("LAN_EU_EN");
	PoLanguage = TEXT("en");
	Regression = TEXT("0");
	CreateBug = TEXT("0");
	BugId.Empty();
	AISign = TEXT("1");
	DefaultNums = TEXT("1");
	MinID = TEXT("1");
	Modules.Empty();
	IsCover = TEXT("false");
	BaseDataId.Empty();
	BaseDataFilePath.Empty();
	bIsLocalMode = true;  // 默认运行在本地模式
	RestoreDirection = ERestoreDirection::ChineseToForeign;  // 默认: 中文 -> 外文

	// ---- 2. 设置 PNG 保存目录 ----
	// 使用工程的 Saved 目录, 并转换为绝对路径, 避免相对路径带来的歧义
	PngSaveRootDir = FPaths::ConvertRelativePathToFull(FPaths::ProjectSavedDir());

	// ---- 3. 初始化语言映射表 ----
	InitializeLanguageMap();

	// ---- 4. 解析命令行参数 (会覆盖上面的默认值) ----
	ParseCommandLineParams();

	// ---- 5. 输出当前配置到日志, 便于排查问题 ----
	UE_LOG(LogLQARestoreConfig, Log, TEXT("=== ConfigManager Initialized ==="));
	UE_LOG(LogLQARestoreConfig, Log, TEXT("ProjectId: %s, JobId: %s"), *ProjectId, *JobId);
	UE_LOG(LogLQARestoreConfig, Log, TEXT("Language: %s, PoLanguage: %s"), *Language, *PoLanguage);
	UE_LOG(LogLQARestoreConfig, Log, TEXT("PngSaveRootDir: %s"), *PngSaveRootDir);
	UE_LOG(LogLQARestoreConfig, Log, TEXT("Regression: %s, IsLocalMode: %s"), *Regression,
		bIsLocalMode ? TEXT("true") : TEXT("false"));
}

void UConfigManager::InitializeLanguageMap()
{
	// 预留 14 个槽位, 避免插入过程中的多次扩容 (哈希表 rehash)
	LanguageMap.Reserve(14);

	// 建立 内部语言代码 -> PO 语言代码 的映射关系
	LanguageMap.Add(TEXT("LAN_EU_EN"), TEXT("en"));     // 英语
	LanguageMap.Add(TEXT("LAN_EU_DE"), TEXT("de"));     // 德语
	LanguageMap.Add(TEXT("LAN_FR_FR"), TEXT("fr"));     // 法语
	LanguageMap.Add(TEXT("LAN_RU_RU"), TEXT("ru"));     // 俄语
	LanguageMap.Add(TEXT("LAN_JP_JP"), TEXT("ja"));     // 日语
	LanguageMap.Add(TEXT("LAN_KO_KO"), TEXT("ko"));     // 韩语
	LanguageMap.Add(TEXT("LAN_CHT_CHT"), TEXT("zh-TW")); // 繁体中文
	LanguageMap.Add(TEXT("LAN_AR_AR"), TEXT("ar"));     // 阿拉伯语
	LanguageMap.Add(TEXT("LAN_ES_LT"), TEXT("es"));     // 西班牙语
	LanguageMap.Add(TEXT("LAN_PT_BR"), TEXT("pt-BR"));  // 巴西葡萄牙语
	LanguageMap.Add(TEXT("LAN_TR_TR"), TEXT("tr"));     // 土耳其语
	LanguageMap.Add(TEXT("LAN_TH_TH"), TEXT("th"));     // 泰语
	LanguageMap.Add(TEXT("LAN_ID_ID"), TEXT("id"));     // 印尼语
	LanguageMap.Add(TEXT("LAN_CHS_CHS"), TEXT("zh"));   // 简体中文
}

void UConfigManager::ParseCommandLineParams()
{
	// 获取完整命令行字符串, 并以空格分割为若干参数 (最后一个参数 true 表示忽略空项)
	const FString CommandLine = FCommandLine::Get();
	TArray<FString> Params;
	CommandLine.ParseIntoArray(Params, TEXT(" "), true);

	// ---- 从命令行中解析出 "键=值" 形式的参数 ----
	for (const FString& Param : Params)
	{
		// 不含 "=" 的参数不是键值对, 跳过
		if (!Param.Contains(TEXT("=")))
		{
			continue;
		}

		FString Key, Value;
		// 以第一个 "=" 为界拆分为键和值
		if (Param.Split(TEXT("="), &Key, &Value))
		{
			// 去除键名前导的 "-" (例如 -ProjectId=123 -> ProjectId)
			Key.RemoveFromStart(TEXT("-"));

			CommandLineParams.Add(Key, Value);
			UE_LOG(LogLQARestoreConfig, Verbose, TEXT("Parsed CommandLine: %s = %s"), *Key, *Value);
		}
	}

	// ---- 从已解析的参数中提取各配置项 (未提供的参数保留原默认值) ----
	ProjectId = GetCommandLineParam(TEXT("ProjectId"), ProjectId);
	JobId = GetCommandLineParam(TEXT("JobId"), JobId);
	Language = GetCommandLineParam(TEXT("Language"), Language);
	PoLanguage = ConvertToPoLanguage(Language); // 根据语言代码换算 PO 语言代码
	Regression = GetCommandLineParam(TEXT("Regression"), Regression);
	CreateBug = GetCommandLineParam(TEXT("CreateBug"), CreateBug);
	BugId = GetCommandLineParam(TEXT("bugId"), BugId);
	AISign = GetCommandLineParam(TEXT("AISign"), AISign);
	DefaultNums = GetCommandLineParam(TEXT("DefaultNums"), DefaultNums);
	MinID = GetCommandLineParam(TEXT("MinID"), MinID);
	Modules = GetCommandLineParam(TEXT("Modules"), Modules);
	IsCover = GetCommandLineParam(TEXT("IsCover"), IsCover);
	BaseDataId = GetCommandLineParam(TEXT("BaseDataId"), BaseDataId);
	BaseDataFilePath = GetCommandLineParam(TEXT("BaseDataFilePath"), BaseDataFilePath);

	// ---- 解析还原语言方向 ----
	// RestoreDirection=F2C 表示「外文 -> 中文」, 其余 (含缺省) 均为「中文 -> 外文」
	const FString DirStr = GetCommandLineParam(TEXT("RestoreDirection"), TEXT("C2F"));
	RestoreDirection = DirStr.Equals(TEXT("F2C"), ESearchCase::IgnoreCase)
		                   ? ERestoreDirection::ForeignToChinese
		                   : ERestoreDirection::ChineseToForeign;

	// ---- 判定是否为本地模式 ----
	// 当 JobId 为 "0" (即未传入有效任务 ID) 时, 视为本地模式
	bIsLocalMode = (JobId == TEXT("0"));
}

FString UConfigManager::GetCommandLineParam(const FString& Key, const FString& DefaultValue) const
{
	// 在缓存的命令行参数表中查找指定键
	if (const FString* FoundValue = CommandLineParams.Find(Key))
	{
		return *FoundValue;
	}

	// 未找到则返回调用方提供的默认值
	return DefaultValue;
}

FString UConfigManager::ConvertToPoLanguage(const FString& InLanguage) const
{
	// 在语言映射表中查找对应的 PO 语言代码
	if (const FString* PoLang = LanguageMap.Find(InLanguage))
	{
		return *PoLang;
	}

	// 未匹配到时, 记录警告并回退到默认语言 "en"
	UE_LOG(LogLQARestoreConfig, Warning, TEXT("Language '%s' not found in LanguageMap, defaulting to 'en'"), *InLanguage);
	return TEXT("en");
}