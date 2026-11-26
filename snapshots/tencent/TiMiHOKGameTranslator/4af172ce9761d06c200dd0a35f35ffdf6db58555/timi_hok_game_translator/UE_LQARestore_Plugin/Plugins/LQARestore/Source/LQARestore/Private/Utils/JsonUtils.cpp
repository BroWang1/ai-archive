#include "Utils/JsonUtils.h"

#include "LQABase.h"   // 提供日志分类 LogLQARestore 的声明

#include "Json.h"
#include "JsonObjectConverter.h"   // 提供 FJsonObjectConverter, 可借助反射做属性与 JSON 的互转

//======================================================================
// 序列化: 各基础类型 -> JSON
//======================================================================

// 将 FVector2D 序列化为 { "x": X, "y": Y } 的 JSON 子对象, 并挂到 RootObj 的 EntryName 字段下
bool FJsonUtils::SerializeData2Json(
	const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const FVector2D& InVector)
{
	if (RootObj.IsValid())   // 校验根对象有效, 避免对空指针操作
	{
		// 新建一个子 JSON 对象用于存放 x / y 两个分量
		const TSharedPtr<FJsonObject> VectorObj = MakeShareable(new FJsonObject);
		VectorObj->SetNumberField(TEXT("x"), InVector.X);
		VectorObj->SetNumberField(TEXT("y"), InVector.Y);

		// 将子对象作为 EntryName 字段挂到根对象上
		RootObj->SetObjectField(EntryName, VectorObj);
		return true;
	}
	return false;   // 根对象无效, 序列化失败
}

// 将布尔值写入 EntryName 字段
bool FJsonUtils::SerializeData2Json(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const bool InBool)
{
	if (RootObj.IsValid())
	{
		RootObj->SetBoolField(EntryName, InBool);
		return true;
	}
	return false;
}

// 将 int32 写入 EntryName 字段 (JSON 中以数值类型存储)
bool FJsonUtils::SerializeData2Json(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const int32 InNum)
{
	if (RootObj.IsValid())
	{
		RootObj->SetNumberField(EntryName, InNum);
		return true;
	}
	return false;
}

// 将 float 写入 EntryName 字段
bool FJsonUtils::SerializeData2Json(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const float InNum)
{
	if (RootObj.IsValid())
	{
		RootObj->SetNumberField(EntryName, InNum);
		return true;
	}
	return false;
}

// 将 double 写入 EntryName 字段
bool FJsonUtils::SerializeData2Json(
	const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const double InNum)
{
	if (RootObj.IsValid())
	{
		RootObj->SetNumberField(EntryName, InNum);
		return true;
	}
	return false;
}

// 将字符串写入 EntryName 字段
bool FJsonUtils::SerializeData2Json(
	const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName, const FString& InStr)
{
	if (RootObj.IsValid())
	{
		RootObj->SetStringField(EntryName, InStr);
		return true;
	}
	return false;
}

//======================================================================
// 反序列化: JSON -> 各基础类型
//======================================================================

// 从 JSON 读取 Vector2D; 字段缺失、子对象无效时返回零向量; 缺少某个分量时该分量保持默认值 0
FVector2D FJsonUtils::DeserializeFromJson_Vector2D(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName)
{
	if (RootObj->HasField(EntryName))   // 先判断字段是否存在
	{
		const TSharedPtr<FJsonObject> VectorObj = RootObj->GetObjectField(EntryName);
		if (VectorObj.IsValid())
		{
			FVector2D DefaultVector = FVector2D::ZeroVector;
			if (VectorObj->HasField(TEXT("x")))
			{
				DefaultVector.X = VectorObj->GetNumberField(TEXT("x"));
			}
			if (VectorObj->HasField(TEXT("y")))
			{
				DefaultVector.Y = VectorObj->GetNumberField(TEXT("y"));
			}

			return DefaultVector;
		}
	}
	return FVector2D::ZeroVector;   // 未找到有效数据, 返回零向量
}

// 从 JSON 读取布尔值, 字段缺失返回 false
bool FJsonUtils::DeserializeFromJson_Bool(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName)
{
	if (RootObj->HasField(EntryName))
	{
		return RootObj->GetBoolField(EntryName);
	}
	return false;
}

//======================================================================
// 通用对象序列化: UObject -> JSON (基于反射)
//======================================================================

bool FJsonUtils::SerializeObject2Json(const UObject* Object, TSharedPtr<FJsonObject>& OutJsonObject)
{
	// 入参校验: 对象与输出 JSON 对象都必须有效
	if (!Object || !OutJsonObject.IsValid())
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to get Object"));
		return false;
	}

	// 二次校验输出对象 (冗余保护)
	if (!OutJsonObject.IsValid())
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to OutJsonObject"));
		return false;
	}

	UClass* Class = Object->GetClass();   // 获取对象的反射类信息

	// 使用属性迭代器遍历该类的所有 UProperty
	for (TFieldIterator<FProperty> PropIt(Class); PropIt; ++PropIt)
	{
		FProperty* Property = *PropIt;
		FString PropertyName = Property->GetName();
		// 获取该属性在对象实例中的内存地址
		const void* Value = Property->ContainerPtrToValuePtr<void>(Object);

		UE_LOG(LogLQARestore, Log, TEXT("111111:%s"), *PropertyName);   // 调试日志: 输出当前属性名
		if (!Value)
		{
			UE_LOG(LogLQARestore, Warning, TEXT("Failed to get value for property: %s"), *Property->GetName());
			continue;
		}
		// 跳过名为 Slots 的属性 (业务上单独处理, 不参与通用序列化)
		if (PropertyName == TEXT("Slots"))
		{
			continue;
		}

		// 跳过不应被序列化的属性: 实例化引用、瞬态、编辑器专用、已废弃、显式跳过序列化等
		if (Property->HasAnyPropertyFlags(CPF_InstancedReference | CPF_Transient | CPF_DuplicateTransient |
										  CPF_EditorOnly | CPF_Deprecated | CPF_SkipSerialization |
										  CPF_NonPIEDuplicateTransient))
		{
			UE_LOG(LogLQARestore, Warning, TEXT("Skipping Instanced property: %s"), *Property->GetName());
			continue;
		}

		// 跳过各类对象指针属性 (强引用 / 弱引用 / 软引用), 避免序列化指针地址
		if (Property->IsA<FObjectProperty>() || Property->IsA<FWeakObjectProperty>() ||
			Property->IsA<FSoftObjectProperty>())
		{
			UE_LOG(LogLQARestore, Warning, TEXT("Skipping pointer property: %s"), *Property->GetName());
			continue;
		}

		// 借助 UE 的转换器把属性值转为 JSON 值, 并写入输出对象
		TSharedPtr<FJsonValue> JsonValue = FJsonObjectConverter::UPropertyToJsonValue(Property, Value, 0, 0, nullptr);
		if (JsonValue.IsValid())
		{
			OutJsonObject->SetField(PropertyName, JsonValue);
		}
	}

	// 只要写入了任意字段即视为成功
	if (OutJsonObject->Values.Num())
		return true;

	return false;
}

// 从 JSON 读取 int32, 字段缺失返回 0
int32 FJsonUtils::DeserializeFromJson_Int32(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName)
{
	if (RootObj->HasField(EntryName))
	{
		return RootObj->GetNumberField(EntryName);
	}
	return 0;
}

// 从 JSON 读取 float, 字段缺失返回 0.0f
float FJsonUtils::DeserializeFromJson_Float(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName)
{
	if (RootObj->HasField(EntryName))
	{
		return RootObj->GetNumberField(EntryName);
	}
	return 0.0f;
}

// 从 JSON 读取字符串, 字段缺失返回空串
FString FJsonUtils::DeserializeFromJson_FString(const TSharedPtr<FJsonObject>& RootObj, const FString& EntryName)
{
	if (RootObj->HasField(EntryName))
	{
		return RootObj->GetStringField(EntryName);
	}
	return TEXT("");
}

//======================================================================
// 字段名大小写对齐: 让采集端写出的 camelCase 字段能被还原端的反射查找命中
//======================================================================

namespace
{
	// 为嵌套 USTRUCT 补上反射期望的字段名别名, 使两种写法都能命中同一个 JSON 值
	void AddReflectionFieldAliasesRecursive(
		const TSharedPtr<FJsonObject>& JsonObject, const UStruct* StructDefinition)
	{
		if (!JsonObject.IsValid() || !StructDefinition)
		{
			return;
		}

		for (TFieldIterator<FProperty> It(StructDefinition); It; ++It)
		{
			const FProperty* Property = *It;
			const FString ExpectedName = StructDefinition->GetAuthoredNameForField(Property);

			// 优先采用反射名称对应的字段
			TSharedPtr<FJsonValue> JsonValue = JsonObject->TryGetField(ExpectedName);

			if (!JsonValue.IsValid())
			{
				// 复用导出端所用的同一套变换生成候选名, 保证与写出端完全对称
				const FString ExportedName = FJsonObjectConverter::StandardizeCase(ExpectedName);
				if (ExportedName != ExpectedName)
				{
					JsonValue = JsonObject->TryGetField(ExportedName);
					if (JsonValue.IsValid())
					{
						JsonObject->SetField(ExpectedName, JsonValue);
					}
				}
			}

			if (!JsonValue.IsValid())
			{
				continue;
			}

			const FStructProperty* StructProperty = CastField<FStructProperty>(Property);
			if (!StructProperty || JsonValue->Type != EJson::Object)
			{
				continue;
			}

			AddReflectionFieldAliasesRecursive(JsonValue->AsObject(), StructProperty->Struct);
		}
	}
}

void FJsonUtils::StandardizeCaseForImport(const TSharedPtr<FJsonObject>& JsonObject, const UStruct* StructDefinition)
{
	AddReflectionFieldAliasesRecursive(JsonObject, StructDefinition);
}

//======================================================================
// 通用对象反序列化: JSON -> UStruct / UObject (基于反射)
//======================================================================

bool FJsonUtils::DeserializeFromJson_Object(
	const TSharedRef<FJsonObject>& JsonObject, UStruct* StructDefinition, void* StructPtr)
{
	// 先把字段名大小写对齐到目标的反射属性名, 否则 camelCase 的嵌套字段会被静默跳过
	FJsonUtils::StandardizeCaseForImport(JsonObject, StructDefinition);

	// 遍历目标类型的全部反射属性
	for (TFieldIterator<FProperty> It(StructDefinition); It; ++It)
	{
		FProperty* Property = *It;
		FString PropertyName = Property->GetName();

		// 检查 JSON 中是否存在同名字段
		if (!JsonObject->HasField(PropertyName))
		{
			continue;  // 不存在对应字段则跳过该属性
		}

		// 取出该字段对应的 JSON 值
		TSharedPtr<FJsonValue> JsonValue = JsonObject->TryGetField(PropertyName);
		if (!JsonValue.IsValid())
		{
			continue;
		}

		// 定位属性在目标实例中的内存地址
		void* ValuePtr = Property->ContainerPtrToValuePtr<void>(StructPtr);
		UE_LOG(LogLQARestore, Warning, TEXT("property:%s"), *PropertyName);
		// 将 JSON 值写入该属性, 失败则整体反序列化终止
		if (!JsonValueToProperty(JsonValue, Property, ValuePtr))
		{
			UE_LOG(LogLQARestore, Warning, TEXT("Failed to convert JSON field %s to property"), *PropertyName);
			return false;
		}
	}

	return true;
}

// 将单个 JSON 值按属性的实际类型写入内存, 支持数值 / 布尔 / 字符串 / 数组 / 结构体 / 枚举, 并对数组与结构体做递归处理
bool FJsonUtils::JsonValueToProperty(const TSharedPtr<FJsonValue>& JsonValue, FProperty* Property, void* ValuePtr)
{
	// —— 整数属性 ——
	if (FIntProperty* IntProp = CastField<FIntProperty>(Property))
	{
		if (JsonValue->Type == EJson::Number)   // JSON 必须是数值类型
		{
			int32 IntValue = static_cast<int32>(JsonValue->AsNumber());
			IntProp->SetPropertyValue(ValuePtr, IntValue);
			return true;
		}
	}
	// —— 浮点属性 ——
	else if (FFloatProperty* FloatProp = CastField<FFloatProperty>(Property))
	{
		if (JsonValue->Type == EJson::Number)
		{
			float FloatValue = static_cast<float>(JsonValue->AsNumber());
			FloatProp->SetPropertyValue(ValuePtr, FloatValue);
			return true;
		}
	}
	// —— 布尔属性 ——
	else if (FBoolProperty* BoolProp = CastField<FBoolProperty>(Property))
	{
		if (JsonValue->Type == EJson::Boolean)
		{
			bool bBoolValue = JsonValue->AsBool();
			BoolProp->SetPropertyValue(ValuePtr, bBoolValue);
			return true;
		}
	}
	// —— 字符串属性 ——
	else if (FStrProperty* StrProp = CastField<FStrProperty>(Property))
	{
		if (JsonValue->Type == EJson::String)
		{
			FString StrValue = JsonValue->AsString();
			StrProp->SetPropertyValue(ValuePtr, StrValue);
			return true;
		}
	}
	// —— 数组属性 —— 逐元素递归转换
	else if (FArrayProperty* ArrayProp = CastField<FArrayProperty>(Property))
	{
		if (JsonValue->Type == EJson::Array)
		{
			const TArray<TSharedPtr<FJsonValue>>& JsonArray = JsonValue->AsArray();
			// FScriptArrayHelper 用于在反射层面安全地操作 TArray 内存
			FScriptArrayHelper Helper(ArrayProp, ValuePtr);
			Helper.Resize(JsonArray.Num());   // 按 JSON 数组长度调整容器大小

			for (int32 i = 0; i < JsonArray.Num(); ++i)
			{
				void* ElemPtr = Helper.GetRawPtr(i);   // 取第 i 个元素的地址
				// ArrayProp->Inner 为元素类型, 递归转换每个元素
				if (!JsonValueToProperty(JsonArray[i], ArrayProp->Inner, ElemPtr))
				{
					return false;
				}
			}
			return true;
		}
	}
	// —— 结构体属性 —— 递归调用对象反序列化
	else if (FStructProperty* StructProp = CastField<FStructProperty>(Property))
	{
		if (JsonValue->Type == EJson::Object)
		{
			TSharedPtr<FJsonObject> SubObject = JsonValue->AsObject();
			if (!DeserializeFromJson_Object(SubObject.ToSharedRef(), StructProp->Struct, ValuePtr))
			{
				return false;
			}
			return true;
		}
	}
	// —— 枚举属性 —— 支持按名称字符串或底层整数两种写法
	else if (FEnumProperty* EnumProp = CastField<FEnumProperty>(Property))
	{
		if (JsonValue->Type == EJson::String)   // 以枚举名字符串表示
		{
			FString EnumName = JsonValue->AsString();
			UEnum* Enum = EnumProp->GetEnum();
			int64 EnumValue = Enum->GetValueByNameString(EnumName);
			if (EnumValue == INDEX_NONE)   // 名称无法匹配到任何枚举项
			{
				return false;
			}
			void* EnumValuePtr = EnumProp->ContainerPtrToValuePtr<void>(ValuePtr);
			// 通过底层整型属性写入枚举的实际数值
			EnumProp->GetUnderlyingProperty()->SetIntPropertyValue(EnumValuePtr, EnumValue);
			return true;
		}
		else if (JsonValue->Type == EJson::Number)   // 直接以底层整数表示
		{
			int64 EnumValue = static_cast<int64>(JsonValue->AsNumber());
			void* EnumValuePtr = EnumProp->ContainerPtrToValuePtr<void>(ValuePtr);
			EnumProp->GetUnderlyingProperty()->SetIntPropertyValue(EnumValuePtr, EnumValue);
			return true;
		}
	}

	// 其余类型暂不支持
	return false;
}