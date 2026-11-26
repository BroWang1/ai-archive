#pragma once

#include "CoreMinimal.h"
#include "Json.h"

// 前置声明 LQA 控件节点类, 避免头文件相互包含
class FLQAWidgetNode;

// 外部声明的控制台变量: 用于控制是否绘制 LQA 调试线 (在其他 cpp 中定义)
extern TAutoConsoleVariable<int32> CVarEnableDrawLQADebugLine;

/**
 * 还原翻译的语言方向
 */
enum class ERestoreDirection : uint8
{
	/** 中文原文 -> 外文译文 (默认): 中文是待翻译原文, 必须先查字典 */
	ChineseToForeign,
	/** 外文原文 -> 中文译文: 原文含中文则视为已翻译, 原样返回 */
	ForeignToChinese
};

/**
 * 翻译数据加载与处理工具类
 * 负责从 JSON 文件中加载翻译数据, 并提供核心的翻译查询功能
 */

/**
 * 大小写敏感的字符串键函数 (用于翻译映射表)
 * 为翻译的键值对提供「区分大小写」的匹配与哈希逻辑
 * 默认的 TMap 键比较通常不区分大小写, 这里通过自定义 KeyFuncs 强制区分大小写,
 * 从而保证例如 "Key" 与 "key" 被视为两个不同的键
 */
struct FCaseSensitiveStringKeyFuncs : public TDefaultMapKeyFuncs<FString, FString, false>
{
	/** 区分大小写的字符串匹配: 使用 Strcmp 精确比较, 完全相等才返回 true */
	static FORCEINLINE bool Matches(const FString& A, const FString& B)
	{
		return FCString::Strcmp(*A, *B) == 0;
	}

	/** 
	 * 区分大小写的哈希函数: 基于宽字符数组按字节做 CRC32 哈希
	 * 之所以自定义哈希, 是因为默认哈希可能忽略大小写, 必须让大小写不同的字符串
	 * 产生不同的哈希值, 才能配合上面的 Matches 实现真正的大小写敏感
	 */
	static FORCEINLINE uint32 GetKeyHash(const FString& Key)
	{
		// Key.Len() 返回的是 TCHAR 的数量, 而非字节数
		// 在 Windows 平台上 TCHAR 为 wchar (2 字节)
		// 因此需要按 Key.Len() * sizeof(TCHAR) 个字节来计算哈希
		return FCrc::MemCrc32(reinterpret_cast<const uint8*>(*Key), Key.Len() * sizeof(TCHAR));
	}
};

/**
 * 翻译数据加载工具类
 * 提供加载与处理翻译数据的核心功能 (全部为静态成员, 作为全局翻译数据的容器)
 */
class FLoaderUtils
{
public:
	/** JSON 中表示「翻译内容」的字段名称 */
	static constexpr const TCHAR* TranslationFieldName = TEXT("translation");

	/** 当找不到任何匹配的翻译时返回的标记字符串 */
	static constexpr const TCHAR* UnmatchedMarker = TEXT("##UnMatched");

	/** 「翻译键 -> 翻译文本」的映射表 (使用大小写敏感的键函数) */
	static TMap<FString, FString, FDefaultSetAllocator, FCaseSensitiveStringKeyFuncs> AllKeyText;

	/** 「源文本 -> 翻译文本」的映射表 (使用大小写敏感的键函数) */
	static TMap<FString, FString, FDefaultSetAllocator, FCaseSensitiveStringKeyFuncs> AllTextKey;

	/**
	 * 从 JSON 文件加载翻译数据
	 * @param FilePath        「键-翻译」JSON 文件的路径 (填充 AllKeyText)
	 * @param FilePathForText 「文本-翻译」JSON 文件的路径 (填充 AllTextKey)
	 * @param Language        语言标识符
	 * @return 加载成功返回 true, 否则返回 false
	 */
	static bool LoadJsonFromFile(const FString& FilePath, const FString& FilePathForText, const FString& Language);

	/**
	 * 同时根据「键」和「内容」查询翻译后的字符串
	 * @param QueryKey     翻译键
	 * @param QueryContent 源内容文本
	 * @return 最终翻译得到的字符串 (若无匹配则返回 UnmatchedMarker 标记)
	 */
	static FString GetTranslateString(const FString& QueryKey, const FString& QueryContent);

	/** 当前还原方向 (默认: 外文 -> 中文) */
	static ERestoreDirection RestoreDirection;

	/** 设置还原方向 (在加载译文时由上层根据配置写入) */
	static void SetRestoreDirection(ERestoreDirection InDirection) { RestoreDirection = InDirection; }
};