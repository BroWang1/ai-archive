#pragma once

#include "CoreMinimal.h"
#include "Utils/TranslationUtils/LoaderUtils.h"

// UHT (Unreal Header Tool) 自动生成的头文件, 必须放在所有 UCLASS/USTRUCT 相关宏之后、
// 且作为本头文件最后一个 include, 否则会编译报错
#include "ConfigManager.generated.h"

// 声明一个专属的日志分类 LogLQARestoreConfig, 供 ConfigManager 相关日志输出使用
// 第二个参数 Log 表示默认日志级别, 第三个参数 All 表示编译期允许的最高详细级别
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreConfig, Log, All);

/**
 * 配置管理器 (Config Manager)
 * 负责 LQA Restore 工具的配置与命令行参数管理
 * 职责包括: 解析命令行参数、存储配置项, 并对外提供统一的访问接口
 */
UCLASS()
class LQARESTORE_API UConfigManager : public UObject
{
	GENERATED_BODY()

public:
	/**
	 * 初始化配置管理器并解析命令行参数
	 * 应在子系统 (Subsystem) 初始化期间调用一次
	 */
	void Initialize();

	/**
	 * 获取指定的命令行参数值
	 * @param Key          - 要查找的参数键名
	 * @param DefaultValue - 当参数不存在时返回的默认值
	 * @return 参数对应的值; 若未找到则返回 DefaultValue
	 */
	FString GetCommandLineParam(const FString& Key, const FString& DefaultValue) const;

	/**
	 * 将内部语言代码转换为 PO 文件使用的语言代码
	 * @param InLanguage - 内部语言标识 (例如 "LAN_EU_EN")
	 * @return PO 语言代码 (例如 "en"); 若未匹配到则默认返回 "en"
	 */
	FString ConvertToPoLanguage(const FString& InLanguage) const;

	// ============================================================
	// 配置项 Getter (只读访问接口)
	// 使用 FORCEINLINE 强制内联, 返回 const 引用以避免字符串拷贝开销
	// ============================================================

	/** 获取项目 ID */
	FORCEINLINE const FString& GetProjectId() const
	{
		return ProjectId;
	}
	/** 获取任务 (Job) ID */
	FORCEINLINE const FString& GetJobId() const
	{
		return JobId;
	}
	/** 获取内部语言代码 */
	FORCEINLINE const FString& GetLanguage() const
	{
		return Language;
	}
	/** 获取 PO 语言代码 */
	FORCEINLINE const FString& GetPoLanguage() const
	{
		return PoLanguage;
	}
	/** 获取回归测试标志 */
	FORCEINLINE const FString& GetRegression() const
	{
		return Regression;
	}
	/** 获取是否创建 Bug 的标志 */
	FORCEINLINE const FString& GetCreateBug() const
	{
		return CreateBug;
	}
	/** 获取 Bug 跟踪 ID */
	FORCEINLINE const FString& GetBugId() const
	{
		return BugId;
	}
	/** 获取 AI 签名标志 */
	FORCEINLINE const FString& GetAISign() const
	{
		return AISign;
	}
	/** 获取默认拉取数量 */
	FORCEINLINE const FString& GetDefaultNums() const
	{
		return DefaultNums;
	}
	/** 获取查询用的最小数据 ID */
	FORCEINLINE const FString& GetMinID() const
	{
		return MinID;
	}
	/** 获取模块过滤列表 */
	FORCEINLINE const FString& GetModules() const
	{
		return Modules;
	}
	/** 获取是否覆盖已有文件的标志 */
	FORCEINLINE const FString& GetIsCover() const
	{
		return IsCover;
	}
	/** 获取基线对比数据 ID */
	FORCEINLINE const FString& GetBaseDataId() const
	{
		return BaseDataId;
	}
	/** 获取基线对比数据文件路径 */
	FORCEINLINE const FString& GetBaseDataFilePath() const
	{
		return BaseDataFilePath;
	}
	/** 获取 PNG 文件保存的根目录 */
	FORCEINLINE const FString& GetPngSaveRootDir() const
	{
		return PngSaveRootDir;
	}
	/** 是否运行在本地模式 (true 表示本地模式) */
	FORCEINLINE bool IsLocalMode() const
	{
		return bIsLocalMode;
	}

	/** 获取还原语言方向 */
	FORCEINLINE ERestoreDirection GetRestoreDirection() const
	{
		return RestoreDirection;
	}

private:
	/** 解析命令行参数并填充各配置项 */
	void ParseCommandLineParams();

	/** 初始化语言代码映射表 (内部语言代码 -> PO 语言代码) */
	void InitializeLanguageMap();

	/** 缓存解析后的命令行参数 (键 -> 值) */
	TMap<FString, FString> CommandLineParams;

	/** 语言代码映射表: 内部语言代码 映射到 PO 语言代码 */
	TMap<FString, FString> LanguageMap;

	// ============================================================
	// 配置成员变量
	// ============================================================

	/** PNG 文件保存的根目录 */
	FString PngSaveRootDir;

	/** 项目标识 ID */
	FString ProjectId;

	/** 任务 (Job) 标识 ID */
	FString JobId;

	/** 内部语言代码 (例如 LAN_EU_EN) */
	FString Language;

	/** PO 语言代码 (例如 en) */
	FString PoLanguage;

	/** 回归测试标志 (0 或 1) */
	FString Regression;

	/** 创建 Bug 标志 (0 或 1) */
	FString CreateBug;

	/** Bug 跟踪 ID */
	FString BugId;

	/** AI 签名标志 */
	FString AISign;

	/** 默认拉取的条目数量 */
	FString DefaultNums;

	/** 查询时使用的最小数据 ID */
	FString MinID;

	/** 模块过滤列表 */
	FString Modules;

	/** 是否覆盖已存在的文件 */
	FString IsCover;

	/** 基线对比数据 ID */
	FString BaseDataId;

	/** 基线对比数据文件路径 */
	FString BaseDataFilePath;

	/** 是否运行在本地模式 */
	bool bIsLocalMode;

	/** 还原语言方向 (默认: 外文 -> 中文) */
	ERestoreDirection RestoreDirection;
};