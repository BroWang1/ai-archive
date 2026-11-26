#pragma once

#include "CoreMinimal.h"

/**
 * 翻译校验工具类 (FValidatorUtils)
 *
 * 提供一组与「翻译规则校验」和「文本处理」相关的静态工具函数, 主要用于:
 *   1. 检测文本中是否包含中文 / 英文字符;
 *   2. 提取并比较原文与译文中的 HTML 标签, 确保翻译前后标签一致;
 *   3. 提取并比较 #tag# 形式的占位符 (哈希标签), 确保翻译未破坏占位符
 *
 * 本类所有成员均为静态函数, 无需实例化即可直接通过 FValidatorUtils::XXX 调用
 */
class FValidatorUtils
{
public:
	/**
	 * 检测字符串中是否包含中文字符
	 *
	 * @param Text 待检测的字符串
	 * @return 若包含中文字符返回 true, 否则返回 false
	 */
	static bool ContainsChinese(const FString& Text);

	/**
	 * 检测字符串中是否包含英文字母 (A-Z 或 a-z)
	 *
	 * @param Text 待检测的字符串
	 * @return 若包含英文字母返回 true, 否则返回 false
	 */
	static bool ContainsEn(const FString& Text);

	/**
	 * 从输入字符串中提取 HTML 标签: 包括开标签、闭标签以及所有匹配到的标签
	 *
	 * @param Input        待分析的输入字符串
	 * @param OutOpenTags  输出参数：提取到的开标签数组 (已转小写并排序)
	 * @param OutCloseTags 输出参数：提取到的闭标签数组 (已转小写并排序)
	 * @param OutAllTags   输出参数：提取到的所有标签数组 (已转小写并排序)
	 */
	static void ExtractHtmlTags(
		const FString& Input, TArray<FString>& OutOpenTags, TArray<FString>& OutCloseTags, TArray<FString>& OutAllTags);

	/**
	 * 比较两个输入字符串中提取出的 HTML 标签集合是否相等
	 *
	 * 常用于校验原文 (S1) 与译文 (S2) 的标签结构是否保持一致,
	 * 避免翻译过程中误删、误改或打乱了 HTML 标签
	 *
	 * @param S1       第一个输入字符串 (通常为原文)
	 * @param S2       第二个输入字符串 (通常为译文)
	 * @param OutTags1 输出参数: 从第一个字符串提取到的所有标签
	 * @param OutTags2 输出参数: 从第二个字符串提取到的所有标签
	 * @return 当两者的开标签集合与闭标签集合均相等时返回 true, 否则返回 false
	 */
	static bool AreHtmlTagSetsEqual(
		const FString& S1, const FString& S2, TArray<FString>& OutTags1, TArray<FString>& OutTags2);

	/**
	 * 从输入字符串中提取形如 #tag# 的哈希标签 (占位符)
	 *
	 * @param Input       待分析的输入字符串
	 * @param OutHashTags 输出参数：提取到的哈希标签数组 (已转小写并排序)
	 */
	static void ExtractHashTags(const FString& Input, TArray<FString>& OutHashTags);

	/**
	 * 比较两个输入字符串中提取出的哈希标签集合是否相等
	 *
	 * 常用于校验原文与译文中的 #tag# 占位符是否保持一致,
	 * 防止翻译时丢失或改动了占位符
	 *
	 * @param S1       第一个输入字符串 (通常为原文)
	 * @param S2       第二个输入字符串 (通常为译文)
	 * @param OutTags1 输出参数: 从第一个字符串提取到的哈希标签
	 * @param OutTags2 输出参数: 从第二个字符串提取到的哈希标签
	 * @return 当两者的哈希标签集合相等时返回 true, 否则返回 false
	 */
	static bool AreHashTagSetsEqual(
		const FString& S1, const FString& S2, TArray<FString>& OutTags1, TArray<FString>& OutTags2);
};