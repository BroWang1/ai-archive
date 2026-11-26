#pragma once

#include "CoreMinimal.h"
#include "Json.h"          // UE 提供的 JSON 读写核心模块 (FJsonObject / FJsonValue 等)
#include "PaperSprite.h"   // Paper2D 精灵资源相关声明 (此处为依赖所需)

/**
 * FJsonUtils
 * JSON 序列化 / 反序列化工具类
 *
 * 该类所有成员均为静态函数，无需实例化即可调用，主要提供两类能力:
 *   1. 将常见数据类型 (Vector2D、bool、int、float、double、FString) 写入 JSON 对象;
 *   2. 从 JSON 对象中读取对应类型的数据;
 *   3. 基于 UE 反射系统 (UProperty) 对任意 UObject / UStruct 进行通用的序列化与反序列化
 */
class FJsonUtils
{
public:
	// 通用数据接口 (Common Data API)

	/**
	 * 利用反射遍历 UObject 的所有属性, 并序列化为 JSON 对象
	 * @param Object        待序列化的对象 (输入)
	 * @param OutJsonObject 用于接收序列化结果的 JSON 对象 (输出, 须为有效指针)
	 * @return 成功写入至少一个字段时返回 true, 否则返回 false
	 */
	static bool SerializeObject2Json(const UObject* Object, TSharedPtr<FJsonObject>& OutJsonObject);

	// 将 FVector2D 以 { "x":.., "y":.. } 的子对象形式写入 RootObj 的 EntryName 字段
	static bool SerializeData2Json(
		const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const FVector2D& InVector);
	// 将布尔值写入指定字段
	static bool SerializeData2Json(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const bool InBool);
	// 将 32 位整数写入指定字段 (JSON 中统一存为数值)
	static bool SerializeData2Json(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const int32 InNum);
	// 将单精度浮点数写入指定字段
	static bool SerializeData2Json(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const float InNum);
	// 将双精度浮点数写入指定字段
	static bool SerializeData2Json(
		const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const double InNum);
	// 将字符串写入指定字段
	static bool SerializeData2Json(
		const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const FString& InStr);

	// 从 JSON 对象读取 Vector2D, 字段不存在或无效时返回零向量
	static FVector2D DeserializeFromJson_Vector2D(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName);
	// 从 JSON 对象读取布尔值, 字段不存在时返回 false
	static bool DeserializeFromJson_Bool(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName);
	// 从 JSON 对象读取 int32, 字段不存在时返回 0
	static int32 DeserializeFromJson_Int32(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName);
	// 从 JSON 对象读取 float, 字段不存在时返回 0.0f
	static float DeserializeFromJson_Float(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName);
	// 从 JSON 对象读取字符串, 字段不存在时返回空串
	static FString DeserializeFromJson_FString(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName);

	/**
	 * 将单个 JSON 值写入对应的反射属性 (支持递归处理数组、结构体等)
	 * @param JsonValue 源 JSON 值
	 * @param Property  目标反射属性
	 * @param ValuePtr  目标属性在内存中的地址
	 * @return 转换成功返回 true; 类型不匹配或不支持返回 false
	 */
	static bool JsonValueToProperty(const TSharedPtr<FJsonValue>& JsonValue, FProperty* Property, void* ValuePtr);

	/**
	 * 修正 JSON 对象中字段名的大小写, 使其与目标结构体 (UStruct) 的反射属性名严格一致
	 * @param JsonObject       待修正的 JSON 对象 (原地修改)
	 * @param StructDefinition 目标结构体 / 类的反射定义
	 */
	static void StandardizeCaseForImport(const TSharedPtr<FJsonObject>& JsonObject, const UStruct* StructDefinition);

	/**
	 * 将 JSON 对象反序列化到指定的结构体 / 对象实例 (基于反射逐字段填充)
	 * @param JsonObject       源 JSON 对象
	 * @param StructDefinition 目标类型的反射定义 (UStruct / UClass)
	 * @param StructPtr        目标实例在内存中的地址
	 * @return 全部字段处理成功返回 true，中途失败返回 false
	 */
	static bool DeserializeFromJson_Object(
		const TSharedRef<FJsonObject>& JsonObject, UStruct* StructDefinition, void* StructPtr);

private:
};