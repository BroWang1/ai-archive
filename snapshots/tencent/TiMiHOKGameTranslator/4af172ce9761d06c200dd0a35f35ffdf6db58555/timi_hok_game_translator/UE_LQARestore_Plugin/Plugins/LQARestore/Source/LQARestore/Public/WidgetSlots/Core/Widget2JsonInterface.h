#pragma once

#include "CoreMinimal.h"
#include "Internationalization/TextLocalizationManager.h" // 文本本地化管理器, 用于处理多语言文本
#include "Json.h"                                          // UE JSON 基础类型 (FJsonObject 等)
#include "Utils/JsonUtils.h"                               // 字段名大小写对齐工具 (修复嵌套字段被静默跳过)
#include "JsonObjectConverter.h"                           // JSON 与 UStruct/UObject 之间的转换工具
#include "WidgetSlots/Core/WidgetDefines.h"                // Widget 相关的常量与枚举定义 (如 ELQAWidgetType、各类 Key 名)
#include "WidgetTree/LQAWidgetNode.h"                       // LQA Widget 节点定义

// 声明一个专用于 "Widget 转 JSON" 模块的日志分类, 便于在输出日志中过滤定位
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreWidget2Json, Log, All);

// 前置声明, 避免在头文件中引入完整头文件, 减少编译依赖
class UWidget;
class URestoreWindowProxy;

/**
 * FWidget2JsonInterface
 * --------------------------------------------------------------------
 * Widget 与 JSON 相互转换的抽象接口基类
 * 各种具体类型的 Widget (如文本、图片、按钮等) 应派生此类，
 * 并实现 FromJson / GetType, 以完成「从 JSON 数据还原出对应 UWidget」的逻辑
 */
class FWidget2JsonInterface
{
public:
	// 默认构造函数 (无额外初始化逻辑)
	FWidget2JsonInterface()
	{
	}

	// 虚析构函数, 确保通过基类指针删除派生类对象时能正确释放资源
	virtual ~FWidget2JsonInterface()
	{
	}

	/**
	 * 从 JSON 数据中提取并解析文本, 返回经过翻译处理后的 FText
	 *
	 * @param JsonData            包含文本信息的 JSON 对象
	 * @param TextEntryName       文本条目的字段名 (默认使用通用字符串 Key)
	 * @param TextKeyName         文本 Key 的字段名 (用于定位翻译表中的条目)
	 * @param SourceStringKeyName 源字符串 (原文) 的字段名
	 * @return                    解析并翻译后的文本
	 */
	static FText GetTextFromJson(const TSharedPtr<FJsonObject> JsonData,
		const FString& TextEntryName = LQAWidgetConstants::CommonStrKey,
		const FString& TextKeyName = LQAWidgetConstants::CommonTextKey,
		const FString& SourceStringKeyName = LQAWidgetConstants::SourceStringKey);

	/**
	 * 根据 JSON 对象创建 (还原) 对应的 Widget
	 * 这是纯虚函数, 必须由派生类实现具体的创建逻辑
	 *
	 * @param JsonData            包含 Widget 数据的 JSON 对象
	 * @param RestoreWindowProxy  还原上下文 (提供还原过程中所需的环境/窗口信息)
	 * @return                    创建成功返回对应的 Widget 指针, 失败返回 nullptr
	 */
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) = 0;

	/**
	 * 获取当前接口对应的 Widget 类型
	 * 基类默认返回「未定义」类型, 派生类应重写以返回具体类型
	 */
	virtual ELQAWidgetType GetType()
	{
		return ELQAWidgetType::LQA_Undefined;
	}

	/**
	 * 模板方法: 将 JSON 对象反序列化为指定类型 T 的 UObject 实例
	 *
	 * @tparam T          目标对象类型 (需为 UObject 派生类)
	 * @param InJsonData  待反序列化的 JSON 对象
	 * @param InStructData 目标类型对应的结构描述 (UStruct),用于指导字段映射
	 * @return            反序列化成功返回新建对象指针, 失败返回 nullptr
	 */
	template <class T>
	T* GetAsObject(const TSharedPtr<FJsonObject> InJsonData, const UStruct* InStructData)
	{
		// 先校验输入参数的有效性, 避免在无效输入时进行不必要的对象分配
		if (!InJsonData.IsValid() || !InStructData)
		{
			return nullptr;
		}

		// 创建目标类型的新对象实例
		T* ObjIns = NewObject<T>();

		// 将 JSON 数据按 InStructData 的结构映射填充到新对象中
		// 字段名大小写对齐到目标结构的反射属性名:
		FJsonUtils::StandardizeCaseForImport(InJsonData, InStructData);

		if (FJsonObjectConverter::JsonObjectToUStruct(InJsonData.ToSharedRef(), InStructData, ObjIns, 0, 0))
		{
			return ObjIns;
		}

		// 反序列化失败: 此处不手动销毁, ObjIns 会在后续由垃圾回收 (GC) 机制自动清理
		return nullptr;
	}
};