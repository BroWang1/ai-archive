#include "WidgetSlots/Core/Widget2JsonInterface.h"

#include "Utils/TranslationUtils/LoaderUtils.h" // 翻译工具类, 提供按 Key/原文 查询译文的能力

// 定义头文件中声明的日志分类 (与 DECLARE_LOG_CATEGORY_EXTERN 配对使用)
DEFINE_LOG_CATEGORY(LogLQARestoreWidget2Json);

/**
 * 从 JSON 数据中解析文本, 并根据 TextKey 的不同形态选择对应的翻译策略,
 * 最终返回翻译 (或原文) 后的 FText
 */
FText FWidget2JsonInterface::GetTextFromJson(const TSharedPtr<FJsonObject> JsonData, const FString& TextEntryName,
	const FString& TextKeyName, const FString& SourceStringKeyName)
{
	// TextStr: 源字符串 (原文); TextKey: 翻译定位 Key; TransStr: 最终输出的译文
	FString TextStr, TextKey, TransStr;

	// 若 JSON 中存在源字符串字段, 则读取原文
	if (JsonData->HasField(SourceStringKeyName))
		TextStr = JsonData->GetStringField(SourceStringKeyName);

	// 若 JSON 中存在文本 Key 字段, 则读取 Key
	if (JsonData->HasField(TextKeyName))
		TextKey = JsonData->GetStringField(TextKeyName);

	// 仅在原文非空时才进行翻译处理
	if (TextStr != TEXT(""))
	{
		if (TextKey.Equals(TEXT(",FORTEST")))
		{
			// 测试标记: 直接使用原文, 不做翻译
			TransStr = TextStr;
		}
		else if (TextKey.Equals(TEXT(",INVALIDKEY")))
		{
			// 无效 Key: 以空 Key 结合原文去查询译文 (通常走原文匹配逻辑)
			TransStr = FLoaderUtils::GetTranslateString(TEXT(""), TextStr);
		}
		else if (TextKey.Contains(TEXT("##")))
		{
			// Key 中包含 "##" 的特殊格式: 直接使用完整 Key 查询译文
			TransStr = FLoaderUtils::GetTranslateString(TextKey, TextStr);
		}
		else
		{
			// 常规情况: Key 可能形如 "命名空间,实际Key", 需要截取逗号右侧部分作为真正的 Key
			int32 CommaIndex;
			if (TextKey.FindChar(',', CommaIndex))
			{
				FString LeftPart = TextKey.Left(CommaIndex);        // 逗号左侧 (命名空间, 此处暂不使用)
				FString RightPart = TextKey.Mid(CommaIndex + 1);    // 逗号右侧 (真正的 Key)
				TextKey = RightPart;
			}

			// 使用处理后的 Key 与原文查询译文
			TransStr = FLoaderUtils::GetTranslateString(TextKey, TextStr);

			// 若返回 "##Notrans" 表示未找到翻译, 则附加 Key 信息以便定位问题
			if (TransStr == TEXT("##Notrans"))
			{
				TransStr += TEXT("(");
				TransStr += TextKey;
				TransStr += TEXT(")");
			}
		}
	}

	// 输出调试日志: 打印原文与最终译文, 便于排查翻译结果
	UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("TextStr: %s"), *TextStr);
	UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("TransStr: %s"), *TransStr);

	// 将译文字符串转换为 FText 返回
	return FText::FromString(TransStr);
}