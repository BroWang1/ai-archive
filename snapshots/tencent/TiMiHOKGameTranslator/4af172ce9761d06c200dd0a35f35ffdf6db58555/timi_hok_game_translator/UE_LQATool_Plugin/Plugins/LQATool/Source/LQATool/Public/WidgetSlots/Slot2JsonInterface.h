#pragma once

#include "CoreMinimal.h"
#include "Json.h"                       // UE 的 JSON 核心类型 (FJsonObject、FJsonValue 等)
#include "JsonObjectConverter.h"        // 提供 JSON 与 UStruct/UObject 相互转换的工具类
#include "Snapshot/LQAWidgetNode.h"     // LQA 控件节点定义, 承载控件及其 Slot 布局信息

// 声明一个日志分类 LogLQAToolSlot2Json, 供本模块的 Slot 转 JSON 流程输出日志
// 参数依次为: 日志分类名、默认日志级别(Log)、编译期允许的最高日志级别(All)
DECLARE_LOG_CATEGORY_EXTERN(LogLQAToolSlot2Json, Log, All);

/**
 * 控件 Slot 转 JSON 的接口 (抽象基类)
 *
 * 作用: 将控件的布局与定位信息 (即 Slot 数据) 序列化为 JSON,
 *       以便做快照存储、数据传输或后续反序列化还原
 * 说明: 这是一个纯虚接口, 不同类型的 Slot (如 CanvasSlot、HorizontalBoxSlot 等)
 *       应派生此类并实现各自的 ToJson 逻辑
 */
class FSlot2JsonInterface
{
public:
	/** 默认构造函数 (使用编译器生成的默认实现) */
	FSlot2JsonInterface() = default;

	/** 虚析构函数: 保证通过基类指针删除派生对象时能正确释放资源 */
	virtual ~FSlot2JsonInterface() = default;

	/**
	 * 将控件的 Slot 信息转换为 JSON
	 * @param InWidget      包含 Slot 信息的控件节点 (输入)
	 * @param OutJsonObject 用于接收转换结果的目标 JSON 对象 (输出)
	 * 注意: 纯虚函数, 必须由派生类实现具体的序列化逻辑
	 */
	virtual void ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject) = 0;

	/**
	 * 将 JSON 数据反序列化为指定类型的 UObject 实例
	 * @tparam T           要创建的目标对象类型 (需为 UObject 派生类)
	 * @param InJsonData   作为数据来源的 JSON 对象
	 * @param InStructData 描述目标类型字段布局的 UStruct 定义
	 * @return             转换成功返回新建对象指针; 失败返回 nullptr
	 */
	template <class T>
	T* GetAsObject(const TSharedPtr<FJsonObject>& InJsonData, const UStruct* InStructData)
	{
		// 先创建一个目标类型的空实例, 后续把 JSON 字段填充进去
		T* ObjIns = NewObject<T>();

		// 仅当 JSON 数据有效且结构定义存在时才执行转换
		if (InJsonData.IsValid() && InStructData)
		{
			// 转换标志位: 指定在 JSON -> UStruct 转换过程中需要一并处理的属性类别
			// - CPF_BlueprintAssignable    : 可在蓝图中绑定的 (多播委托) 属性
			// - CPF_BlueprintCallable      : 可在蓝图中调用的属性
			// - CPF_BlueprintAuthorityOnly : 仅在网络权威端有效的属性
			// - CPF_TextExportTransient    : 文本导出时视为瞬态 (不导出) 的属性
			// - CPF_InstancedReference     : 实例化引用 (子对象) 属性
			constexpr int64 ConversionFlags = CPF_BlueprintAssignable | CPF_BlueprintCallable |
											  CPF_BlueprintAuthorityOnly | CPF_TextExportTransient |
											  CPF_InstancedReference;

			// 执行实际的 JSON -> UStruct(UObject) 转换
			// 参数: 源 JSON 的共享引用、结构定义、目标对象指针、CheckFlags(0)、SkipFlags(ConversionFlags)
			if (FJsonObjectConverter::JsonObjectToUStruct(
					InJsonData.ToSharedRef(), InStructData, ObjIns, 0, ConversionFlags))
			{
				// 转换成功, 返回填充好的对象
				return ObjIns;
			}
		}

		// 数据无效或转换失败, 返回空指针
		return nullptr;
	}
};