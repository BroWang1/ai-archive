#pragma once

#include "CoreMinimal.h"
#include "Json.h"

// 声明本模块专用的日志分类 LogLQAToolJsonUtils
// 参数含义: 分类名、默认日志级别 (Log)、编译期允许的最高级别 (All)
// 用于在 .cpp 中通过 UE_LOG(LogLQAToolJsonUtils, ...) 输出 JSON 相关日志
DECLARE_LOG_CATEGORY_EXTERN(LogLQAToolJsonUtils, Log, All);

/**
 * JSON 序列化 / 反序列化工具类
 * 全部成员均为静态方法, 无需实例化即可调用, 作为纯工具集合使用
 * 封装了基础类型与 UObject 的 JSON 读写, 统一做了空指针/有效性校验
 */
class LQATOOL_API FLQAJsonUtils
{
public:
	// ========== 序列化 (对象/数据 -> JSON) ==========

	/** 通过 UE 反射机制, 将 UObject 的属性序列化写入 JSON 对象 */
	static bool SerializeObjectToJson(const TSharedPtr<FJsonObject>& JsonObject, UObject* Object);

	/** 将基础类型以指定 Key 写入 JSON 对象 (函数重载, 支持常用类型) */
	// FVector2D: 会写成 { "X": .., "Y": .. } 的子对象
	static bool SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FVector2D& Value);
	// 布尔值
	static bool SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, bool Value);
	// 32 位整型
	static bool SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, int32 Value);
	// 单精度浮点
	static bool SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, float Value);
	// 双精度浮点
	static bool SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, double Value);
	// 字符串
	static bool SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FString& Value);

	// ========== 反序列化 (JSON -> 数据) ==========

	/** 从 JSON 中按 Key 读取基础类型; 字段不存在或无效时返回传入的默认值 */
	// 读取 FVector2D (期望值是包含 X/Y 的子对象)
	static FVector2D DeserializeVector2D(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key,
		const FVector2D& DefaultValue = FVector2D::ZeroVector);
	// 读取布尔值
	static bool DeserializeBool(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, bool DefaultValue = false);
	// 读取 32 位整型
	static int32 DeserializeInt32(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, int32 DefaultValue = 0);
	// 读取单精度浮点
	static float DeserializeFloat(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, float DefaultValue = 0.0f);
	// 读取字符串
	static FString DeserializeString(
		const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FString& DefaultValue = TEXT(""));

	// ========== 通用工具方法 ==========

	/** 递归移除 JSON 中所有「键名为空」的字段 (含嵌套对象与数组内的对象) */
	static void RemoveEmptyKeysRecursively(TSharedPtr<FJsonObject> JsonObject);

	/** 判断 JSON 对象是否有效且包含指定字段 Key */
	static bool HasValidField(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key);

private:
	/** 校验 JSON 对象指针是否有效 (内部统一校验入口, 无效时打警告日志) */
	static bool IsValidJsonObject(const TSharedPtr<FJsonObject>& JsonObject);
};