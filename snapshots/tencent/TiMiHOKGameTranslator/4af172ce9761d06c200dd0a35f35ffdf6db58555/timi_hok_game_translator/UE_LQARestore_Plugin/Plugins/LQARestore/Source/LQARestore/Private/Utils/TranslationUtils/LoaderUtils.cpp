#include "Utils/TranslationUtils/LoaderUtils.h"

#include "LQABase.h"

#include "Utils/TranslationUtils/ValidatorUtils.h"

// 关闭编译器优化 (通常用于调试, 便于断点与单步跟踪该文件内的代码)
LQA_DISABLE_OPTIMIZATION

// 静态成员变量定义: 全局的翻译映射表
// AllKeyText：翻译键 -> 翻译文本
TMap<FString, FString, FDefaultSetAllocator, FCaseSensitiveStringKeyFuncs> FLoaderUtils::AllKeyText;
// AllTextKey：源文本 -> 翻译文本
TMap<FString, FString, FDefaultSetAllocator, FCaseSensitiveStringKeyFuncs> FLoaderUtils::AllTextKey;

// 还原方向默认值: 中文 -> 外文
ERestoreDirection FLoaderUtils::RestoreDirection = ERestoreDirection::ChineseToForeign;

/**
 * 从两个 JSON 文件分别加载翻译数据到 AllKeyText 和 AllTextKey 两张映射表中
 */
bool FLoaderUtils::LoadJsonFromFile(const FString& FilePath, const FString& FilePathForText, const FString& Language)
{
	// ===== 第一部分: 加载「键-翻译」JSON 文件, 填充 AllKeyText =====
	FString JsonString;
	// 将文件完整内容读取到字符串中
	if (FFileHelper::LoadFileToString(JsonString, *FilePath))
	{
		// 创建 JSON 读取器与承载解析结果的 JSON 对象
		TSharedRef<TJsonReader<>> JsonReader = TJsonReaderFactory<>::Create(JsonString);
		TSharedPtr<FJsonObject> JsonContent;

		// 反序列化: 将 JSON 字符串解析为 FJsonObject
		if (FJsonSerializer::Deserialize(JsonReader, JsonContent))
		{
			UE_LOG(LogLQARestore, Log, TEXT("LoadFileToString: %s"), *FilePath);
			// 遍历 JSON 顶层的每一个键值对
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : JsonContent->Values)
			{
				TSharedPtr<FJsonValue> JsonValue = Pair.Value;
				// 每个值本身是一个 JSON 对象, 从中取出其子对象
				TSharedPtr<FJsonObject> Content = JsonValue->AsObject();
				// 读取对象中的 "translation" 字段作为翻译文本
				FString ObjectText = Content->GetStringField(TranslationFieldName);
				// 以「外层键」为 Key、「translation 字段值」为 Value 存入映射表
				AllKeyText.Add(Pair.Key, ObjectText);
			}
		}
	}

	// ===== 第二部分: 加载「文本-翻译」JSON 文件, 填充 AllTextKey =====
	FString TextJsonString;
	if (FFileHelper::LoadFileToString(TextJsonString, *FilePathForText))
	{
		TSharedRef<TJsonReader<>> TextJsonReader = TJsonReaderFactory<>::Create(TextJsonString);
		TSharedPtr<FJsonObject> TextJsonContent;

		if (FJsonSerializer::Deserialize(TextJsonReader, TextJsonContent))
		{
			UE_LOG(LogLQARestore, Log, TEXT("LoadFileToString: %s"), *FilePathForText);
			// 遍历顶层键值对
			for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : TextJsonContent->Values)
			{
				TSharedPtr<FJsonValue> JsonValue = Pair.Value;
				// 这里的值是纯字符串类型, 直接取出
				if (JsonValue->Type == EJson::String)
				{
					FString Value = JsonValue->AsString();
					// 以「源文本」为 Key、「翻译文本」为 Value 存入映射表
					AllTextKey.Add(Pair.Key, Value);
				}
			}
		}
		else
		{
			// 解析失败则记录错误并直接返回 false
			UE_LOG(LogLQARestore, Error, TEXT("Failed to parse JSON file: %s"), *FilePathForText);
			return false;
		}
	}

	// 只有当两张映射表都成功加载到数据时, 才认为加载成功
	return AllKeyText.Num() > 0 && AllTextKey.Num() > 0;
}

/**
 * 根据键与内容查询翻译结果, 按优先级依次尝试多种匹配策略
 */
FString FLoaderUtils::GetTranslateString(const FString& QueryKey, const FString& QueryContent)
{
	// 0. 中文守卫: 仅在「外文 -> 中文」方向启用
	//    此方向下, 原文含中文说明已是译文, 原样返回;
	//    「中文 -> 外文」方向下, 中文是待翻译原文, 不能短路, 必须继续查字典
	if (RestoreDirection == ERestoreDirection::ForeignToChinese
		&& FValidatorUtils::ContainsChinese(QueryContent))
	{
		return QueryContent;
	}

	// 1. 检查内容是否仅由数字、标点和空白组成; 若是, 则无需翻译, 返回原内容 (两种方向都适用)
	bool bOnlyNumbersAndPunctuation = true;
	for (const TCHAR& Char : QueryContent)
	{
		// 只要出现一个非数字、非标点、非空白的字符, 就说明含有需翻译的文本
		if (!FChar::IsDigit(Char) && !FChar::IsPunct(Char) && !FChar::IsWhitespace(Char))
		{
			bOnlyNumbersAndPunctuation = false;
			break;
		}
	}
	// 仅当「全是数字/标点」且内容非空时才直接返回原内容
	if (bOnlyNumbersAndPunctuation && !QueryContent.IsEmpty())
	{
		return QueryContent;
	}

	// 2. 优先通过「键」在 AllKeyText 中查找匹配的翻译
	if (const FString* FoundValue = AllKeyText.Find(QueryKey))
	{
		return *FoundValue;
	}

	// 3. 再通过「内容」在 AllTextKey 中查找匹配的翻译
	if (const FString* FoundValue = AllTextKey.Find(QueryContent))
	{
		return *FoundValue;
	}

	// 4. 以上均未命中, 返回「未匹配」标记
	return UnmatchedMarker;
}

// 恢复编译器优化 (与文件顶部的 LQA_DISABLE_OPTIMIZATION 成对使用)
LQA_ENABLE_OPTIMIZATION