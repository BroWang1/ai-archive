#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Styling/SlateBrush.h"

/**
 * FSlateBrushUtils
 *
 * Slate 画刷(Brush)工具类
 * 提供一组静态辅助函数, 用于从 JSON 对象中解析数据并构建 FSlateBrush 实例,
 * 常用于将配置文件/序列化数据中的样式信息还原为运行时可用的 Slate 画刷
 */
class FSlateBrushUtils
{
public:
	/**
	 * 根据 JSON 对象创建一个 FSlateBrush
	 *
	 * @param JsonObject     包含画刷各字段配置的 JSON 对象 (如 ImageSize、Margin、TintColor 等)
	 * @param ResourceObject 画刷所引用的资源对象 (通常是纹理/材质), 可为空
	 * @return 解析并填充完成后的 FSlateBrush 实例; 未提供的字段将保留默认值
	 */
	static FSlateBrush CreateSlateBrushFromJson(const TSharedPtr<FJsonObject>& JsonObject, UObject* ResourceObject);

private:
	/**
	 * 从 JSON 中解析一个二维向量字段 (要求 JSON 中为长度为 2 的数组 [X, Y])
	 *
	 * @param JsonObject 源 JSON 对象
	 * @param FieldName  要解析的字段名
	 * @param OutVector  [输出] 解析成功时写入的二维向量
	 * @return 解析成功返回 true, 否则返回 false
	 */
	static bool ParseVector2D(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FVector2D& OutVector);

	/**
	 * 从 JSON 中解析一个边距 (Margin) 字段 (要求为包含 Left/Top/Right/Bottom 的子对象)
	 *
	 * @param JsonObject 源 JSON 对象
	 * @param FieldName  要解析的字段名
	 * @param OutMargin  [输出] 解析成功时写入的边距
	 * @return 解析成功返回 true, 否则返回 false
	 */
	static bool ParseMargin(const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FMargin& OutMargin);

	/**
	 * 从 JSON 中解析一个线性颜色 (FLinearColor) 字段 (要求为包含 R/G/B 的子对象, A 可选, 默认 1.0)
	 *
	 * @param JsonObject 源 JSON 对象
	 * @param FieldName  要解析的字段名
	 * @param OutColor   [输出] 解析成功时写入的线性颜色
	 * @return 解析成功返回 true, 否则返回 false
	 */
	static bool ParseLinearColor(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FLinearColor& OutColor);

	/**
	 * 从 JSON 中解析一个 Slate 颜色 (FSlateColor) 字段
	 * 内部复用 ParseLinearColor, 将解析得到的线性颜色包装为 FSlateColor
	 *
	 * @param JsonObject 源 JSON 对象
	 * @param FieldName  要解析的字段名
	 * @param OutColor   [输出] 解析成功时写入的 Slate 颜色
	 * @return 解析成功返回 true, 否则返回 false
	 */
	static bool ParseSlateColor(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FSlateColor& OutColor);

	/**
	 * 从 JSON 中解析一个枚举字段 (JSON 中以字符串形式存储枚举名)
	 * 通过模板 + if constexpr 支持多种 Slate 画刷相关枚举类型的字符串->枚举值映射
	 *
	 * @tparam EnumType 目标枚举类型 (如 ESlateBrushDrawType::Type 等)
	 * @param JsonObject 源 JSON 对象
	 * @param FieldName  要解析的字段名
	 * @param OutEnum    [输出] 解析成功时写入的枚举值
	 * @return 解析成功返回 true, 否则返回 false
	 */
	template <typename EnumType>
	static bool ParseEnum(const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, EnumType& OutEnum);
};