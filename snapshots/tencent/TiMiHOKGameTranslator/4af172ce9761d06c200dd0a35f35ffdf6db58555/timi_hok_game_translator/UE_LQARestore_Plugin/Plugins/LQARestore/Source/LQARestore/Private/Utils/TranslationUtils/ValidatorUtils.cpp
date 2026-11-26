#include "Utils/TranslationUtils/ValidatorUtils.h"

// 引入虚幻引擎国际化模块下的正则表达式支持 (FRegexPattern / FRegexMatcher)
#include "Internationalization/Regex.h"

// 检测字符串中是否包含中文字符
bool FValidatorUtils::ContainsChinese(const FString& Text)
{
	// 逐个遍历字符串中的每个字符
	for (const TCHAR& Char : Text)
	{
		// 判断字符是否落在「CJK 统一表意文字」基本区间 (U+4E00 ~ U+9FFF)
		// 该区间覆盖了绝大多数常用汉字
		if (Char >= 0x4E00 && Char <= 0x9FFF)
		{
			// 一旦发现中文字符即可提前返回, 无需继续遍历
			return true;
		}
	}
	// 遍历结束仍未发现中文字符, 返回 false
	return false;
}

// 检测字符串中是否包含英文字母
bool FValidatorUtils::ContainsEn(const FString& Text)
{
	// 使用索引遍历字符串中的每个字符
	for (int32 i = 0; i < Text.Len(); ++i)
	{
		TCHAR Char = Text[i];
		// 判断字符是否为大写字母 (A-Z) 或小写字母 (a-z)
		if ((Char >= 'A' && Char <= 'Z') || (Char >= 'a' && Char <= 'z'))
		{
			// 发现英文字母即提前返回
			return true;
		}
	}
	// 未发现任何英文字母, 返回 false
	return false;
}

// 从输入字符串中提取 HTML 开标签、闭标签以及所有标签
void FValidatorUtils::ExtractHtmlTags(
	const FString& Input, TArray<FString>& OutOpenTags, TArray<FString>& OutCloseTags, TArray<FString>& OutAllTags)
{
	// 先清空输出数组, 防止外部传入的数组携带脏数据
	OutOpenTags.Reset();
	OutCloseTags.Reset();
	OutAllTags.Reset();

	// 匹配开标签的正则表达式:
	//   - (?!/)       : 负向先行断言, 排除以 '/' 开头的闭标签;
	//   - [^>...]+    : 匹配标签内容, 并排除 '>' 以及若干 Unicode 区间
	//                   (中文、日文假名、韩文、泰文等), 避免把普通文本误判为标签
	FString OpenTagPatternStr = TEXT(R"(<(?!/)[^>\\u4E00-\\u9FFF\\u3040-\\u30FF\\uAC00-\\uD7AF\\u0E00-\\u0E7F]+>)");
	FRegexPattern OpenTagPattern(OpenTagPatternStr);
	FRegexMatcher OpenTagMatcher(OpenTagPattern, Input);

	// 循环查找所有匹配到的开标签
	while (OpenTagMatcher.FindNext())
	{
		// 获取整个匹配结果 (捕获组 0), 并统一转为小写以便后续比较
		FString Match = OpenTagMatcher.GetCaptureGroup(0).ToLower();
		OutOpenTags.Add(Match);
	}

	// 匹配闭标签 "</>" 的正则表达式:
	//   - (^|[^<]) : 要求 "</>" 前面是字符串开头或非 '<' 字符 (捕获组 1);
	//   - (</>)    : 实际要匹配的闭标签本身 (捕获组 2);
	//   - (?!>)    : 负向先行断言, 确保其后不紧跟 '>'
	FString CloseTagPatternStr = TEXT(R"((^|[^<])(</>)(?!>))");
	FRegexPattern CloseTagPattern(CloseTagPatternStr);
	FRegexMatcher CloseTagMatcher(CloseTagPattern, Input);

	// 循环查找所有匹配到的闭标签
	while (CloseTagMatcher.FindNext())
	{
		// 取捕获组 2, 即 "</>" 本身 (捕获组 1 仅用于定位前缀, 不需要)
		FString Match = CloseTagMatcher.GetCaptureGroup(2);
		OutCloseTags.Add(Match);
	}

	// 对开标签与闭标签数组进行排序, 使标签集合的比较与顺序无关
	OutOpenTags.Sort();
	OutCloseTags.Sort();
}

// 比较两个字符串的 HTML 标签集合是否一致
bool FValidatorUtils::AreHtmlTagSetsEqual(
	const FString& S1, const FString& S2, TArray<FString>& OutTags1, TArray<FString>& OutTags2)
{
	// 分别用于存放两个字符串提取出的开标签与闭标签
	TArray<FString> Open1, Close1;
	TArray<FString> Open2, Close2;

	// 分别从 S1、S2 中提取 HTML 标签
	ExtractHtmlTags(S1, Open1, Close1, OutTags1);
	ExtractHtmlTags(S2, Open2, Close2, OutTags2);

	// 由于提取时已排序, 可直接用 == 比较开标签集合与闭标签集合
	bool bOpenEqual = Open1 == Open2;
	bool bCloseEqual = Close1 == Close2;

	// 只有开标签与闭标签集合都相等时, 才认为两者标签结构一致
	return bOpenEqual && bCloseEqual;
}

// 从输入字符串中提取形如 #tag# 的哈希标签
void FValidatorUtils::ExtractHashTags(const FString& Input, TArray<FString>& OutHashTags)
{
	// 清空输出数组, 避免脏数据
	OutHashTags.Reset();

	// 匹配哈希标签的正则表达式: 以 '#' 开头和结尾,
	// 中间由字母、数字、下划线或中文字符组成 (#...#)
	FRegexPattern HashTagPattern(TEXT(R"(#[A-Za-z0-9_\\u4e00-\\u9fa5]+#)"));
	FRegexMatcher Matcher(HashTagPattern, Input);

	// 循环查找所有匹配到的哈希标签
	while (Matcher.FindNext())
	{
		// 获取整个匹配结果 (捕获组 0), 并统一转为小写便于后续比较
		FString Match = Matcher.GetCaptureGroup(0).ToLower();
		OutHashTags.Add(Match);
	}

	// 排序, 使集合比较与顺序无关
	OutHashTags.Sort();
}

// 比较两个字符串的哈希标签集合是否一致
bool FValidatorUtils::AreHashTagSetsEqual(
	const FString& S1, const FString& S2, TArray<FString>& OutTags1, TArray<FString>& OutTags2)
{
	// 分别从 S1、S2 中提取哈希标签 (提取函数内部已排序)
	ExtractHashTags(S1, OutTags1);
	ExtractHashTags(S2, OutTags2);

	// 直接比较两个已排序的哈希标签集合是否完全相等
	return OutTags1 == OutTags2;
}