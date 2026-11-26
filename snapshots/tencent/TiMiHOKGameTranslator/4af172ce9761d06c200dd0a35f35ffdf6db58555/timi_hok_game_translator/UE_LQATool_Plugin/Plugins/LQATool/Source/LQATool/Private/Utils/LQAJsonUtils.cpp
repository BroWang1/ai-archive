#include "Utils/LQAJsonUtils.h"

#include "JsonObjectConverter.h" // 提供 FJsonObjectConverter::UPropertyToJsonValue 等反射转换接口

// 定义 (实现) 头文件中声明的日志分类, 整个工程中只能定义一次
DEFINE_LOG_CATEGORY(LogLQAToolJsonUtils);

// ========== 私有辅助方法 ==========

// 校验传入的 JSON 对象指针是否有效, 作为各方法的统一前置检查
bool FLQAJsonUtils::IsValidJsonObject(const TSharedPtr<FJsonObject>& JsonObject)
{
	if (!JsonObject.IsValid())
	{
		// 指针无效 (空指针), 记录警告并返回 false
		UE_LOG(LogLQAToolJsonUtils, Warning, TEXT("Invalid JSON object passed"));
		return false;
	}
	return true;
}

// 判断 JSON 对象是否有效, 并且包含指定的字段 Key
bool FLQAJsonUtils::HasValidField(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key)
{
	// 先校验对象本身有效性
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	// 再检查字段是否存在
	if (!JsonObject->HasField(Key))
	{
		// 字段不存在属正常情况, 用 Verbose 级别记录 (默认不输出, 便于调试时开启)
		UE_LOG(LogLQAToolJsonUtils, Verbose, TEXT("JSON object does not have field: %s"), *Key);
		return false;
	}

	return true;
}

// ========== 序列化方法 ==========

// 将 FVector2D 写入 JSON: 生成一个含 X、Y 两个数值字段的子对象
bool FLQAJsonUtils::SerializeToJson(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FVector2D& Value)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	// 创建子对象并分别写入 X / Y 分量
	TSharedPtr<FJsonObject> VectorObject = MakeShareable(new FJsonObject);
	VectorObject->SetNumberField(TEXT("X"), Value.X);
	VectorObject->SetNumberField(TEXT("Y"), Value.Y);

	// 以 Key 作为字段名, 将子对象挂到父 JSON 对象上
	JsonObject->SetObjectField(Key, VectorObject);
	return true;
}

// 将 bool 值写入 JSON
bool FLQAJsonUtils::SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, bool Value)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	JsonObject->SetBoolField(Key, Value);
	return true;
}

// 将 int32 写入 JSON (JSON 内部统一以 number 存储)
bool FLQAJsonUtils::SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, int32 Value)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	JsonObject->SetNumberField(Key, Value);
	return true;
}

// 将 float 写入 JSON
bool FLQAJsonUtils::SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, float Value)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	JsonObject->SetNumberField(Key, Value);
	return true;
}

// 将 double 写入 JSON
bool FLQAJsonUtils::SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, double Value)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	JsonObject->SetNumberField(Key, Value);
	return true;
}

// 将 FString 写入 JSON
bool FLQAJsonUtils::SerializeToJson(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FString& Value)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	JsonObject->SetStringField(Key, Value);
	return true;
}

// 通过反射遍历 UObject 的所有属性, 并逐一序列化到 JSON 对象中
bool FLQAJsonUtils::SerializeObjectToJson(const TSharedPtr<FJsonObject>& JsonObject, UObject* Object)
{
	// 校验待序列化的对象非空
	if (!Object)
	{
		UE_LOG(LogLQAToolJsonUtils, Warning, TEXT("Null object passed for serialization"));
		return false;
	}

	// 校验目标 JSON 对象有效
	if (!IsValidJsonObject(JsonObject))
	{
		return false;
	}

	// 定义序列化时需要跳过的属性标记 (这些属性不应被持久化):
	// 实例化引用、瞬态、复制瞬态、仅编辑器、已废弃、显式跳过序列化、
	// 非 PIE 复制瞬态、文本导出瞬态等
	constexpr int64 SkipFlags = CPF_InstancedReference | CPF_Transient | CPF_DuplicateTransient | CPF_EditorOnly |
								CPF_Deprecated | CPF_SkipSerialization | CPF_NonPIEDuplicateTransient |
								CPF_TextExportTransient;

	// 使用属性迭代器遍历该类 (含父类) 的全部反射属性
	for (TFieldIterator<FProperty> PropertyIterator(Object->GetClass()); PropertyIterator; ++PropertyIterator)
	{
		FProperty* Property = *PropertyIterator;
		// 属性为空, 或命中任一跳过标记, 则忽略该属性
		if (!Property || Property->HasAnyPropertyFlags(static_cast<EPropertyFlags>(SkipFlags)))
		{
			continue;
		}

		// 取得该属性在对象实例中的内存地址 (值指针)
		const void* PropertyValue = Property->ContainerPtrToValuePtr<void>(Object);
		if (!PropertyValue)
		{
			continue;
		}

		// 借助 UE 的转换器, 将单个属性值转换为对应的 JSON 值
		TSharedPtr<FJsonValue> JsonValue =
			FJsonObjectConverter::UPropertyToJsonValue(Property, PropertyValue, 0, SkipFlags, nullptr);

		// 转换成功则以属性名作为字段名写入
		if (JsonValue.IsValid())
		{
			JsonObject->SetField(Property->GetName(), JsonValue);
		}
	}

	// 清理空键, 保持输出整洁
	RemoveEmptyKeysRecursively(JsonObject);
	// 只要至少写入了一个字段即视为成功
	return JsonObject->Values.Num() > 0;
}

// ========== 反序列化方法 ==========

// 从 JSON 读取 FVector2D; 字段缺失或无效时返回默认值
FVector2D FLQAJsonUtils::DeserializeVector2D(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FVector2D& DefaultValue)
{
	// 字段不存在则直接返回默认值
	if (!HasValidField(JsonObject, Key))
	{
		return DefaultValue;
	}

	// 取出该字段对应的子对象 (期望为 { X, Y } 结构)
	const TSharedPtr<FJsonObject> VectorObject = JsonObject->GetObjectField(Key);
	if (!IsValidJsonObject(VectorObject))
	{
		return DefaultValue;
	}

	// 以默认值为基础, 逐分量覆盖; 缺失的分量保留默认值
	FVector2D Result = DefaultValue;
	if (VectorObject->HasField(TEXT("X")))
	{
		Result.X = VectorObject->GetNumberField(TEXT("X"));
	}
	if (VectorObject->HasField(TEXT("Y")))
	{
		Result.Y = VectorObject->GetNumberField(TEXT("Y"));
	}

	return Result;
}

// 从 JSON 读取 bool, 缺失时返回默认值 (三元运算符简写)
bool FLQAJsonUtils::DeserializeBool(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, bool DefaultValue)
{
	return HasValidField(JsonObject, Key) ? JsonObject->GetBoolField(Key) : DefaultValue;
}

// 从 JSON 读取 int32 (JSON 数值为 double, 需显式转换), 缺失时返回默认值
int32 FLQAJsonUtils::DeserializeInt32(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, int32 DefaultValue)
{
	return HasValidField(JsonObject, Key) ? static_cast<int32>(JsonObject->GetNumberField(Key)) : DefaultValue;
}

// 从 JSON 读取 float (同样由 double 转换), 缺失时返回默认值
float FLQAJsonUtils::DeserializeFloat(const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, float DefaultValue)
{
	return HasValidField(JsonObject, Key) ? static_cast<float>(JsonObject->GetNumberField(Key)) : DefaultValue;
}

// 从 JSON 读取字符串, 缺失时返回默认值
FString FLQAJsonUtils::DeserializeString(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& Key, const FString& DefaultValue)
{
	return HasValidField(JsonObject, Key) ? JsonObject->GetStringField(Key) : DefaultValue;
}

// ========== 通用工具方法 ==========

// 递归移除 JSON 中键名为空字符串的字段, 并深入嵌套对象/数组继续清理
void FLQAJsonUtils::RemoveEmptyKeysRecursively(TSharedPtr<FJsonObject> JsonObject)
{
	if (!IsValidJsonObject(JsonObject))
	{
		return;
	}

	// 先收集需要删除的空键, 再统一删除 (避免遍历容器时边遍历边删除导致迭代器失效)
	// 注意: UE5.8+ 中 FJsonObject::Values 的键类型由 FString 变更为 UE::FSharedString
	// 这里按引擎版本拆分实现, 使每个分支都使用其目标引擎上原生、经过充分测试的 API:
	//   - UE4 : 键为 FString, 直接使用 TMap::Remove(const FString&)
	//   - UE5+: 键为 UE::FSharedString, 改用 FSetElementId 删除, 避免直接依赖键类型
#if ENGINE_MAJOR_VERSION < 5
	// —— UE4 分支: 按键值收集并删除 ——
	TArray<FString> EmptyKeys;
	for (const auto& Pair : JsonObject->Values)
	{
		if (Pair.Key.IsEmpty())
		{
			EmptyKeys.Add(Pair.Key);
		}
	}

	for (const FString& Key : EmptyKeys)
	{
		JsonObject->Values.Remove(Key);
	}
#else
	// —— UE5+ 分支: 按元素 Id 收集并删除 ——
	TArray<FSetElementId> EmptyKeyIds;
	for (auto It = JsonObject->Values.CreateConstIterator(); It; ++It)
	{
		if (It->Key.IsEmpty())
		{
			EmptyKeyIds.Add(It.GetId());
		}
	}

	for (const FSetElementId Id : EmptyKeyIds)
	{
		JsonObject->Values.Remove(Id);
	}
#endif

	// 递归处理剩余字段中的嵌套对象与数组
	for (const auto& Pair : JsonObject->Values)
	{
		const TSharedPtr<FJsonValue>& Value = Pair.Value;
		if (!Value.IsValid())
		{
			continue;
		}

		switch (Value->Type)
		{
			case EJson::Object:
				// 嵌套对象: 直接递归清理
				RemoveEmptyKeysRecursively(Value->AsObject());
				break;

			case EJson::Array:
				// 数组: 遍历元素, 仅对其中的对象元素递归清理
				for (const TSharedPtr<FJsonValue>& ArrayElement : Value->AsArray())
				{
					if (ArrayElement.IsValid() && ArrayElement->Type == EJson::Object)
					{
						RemoveEmptyKeysRecursively(ArrayElement->AsObject());
					}
				}
				break;

			default:
				// 其它基础类型无需处理
				break;
		}
	}
}