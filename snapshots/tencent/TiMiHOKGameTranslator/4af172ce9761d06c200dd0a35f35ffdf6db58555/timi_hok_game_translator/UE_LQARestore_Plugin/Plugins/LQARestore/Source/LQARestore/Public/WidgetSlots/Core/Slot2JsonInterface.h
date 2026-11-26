#pragma once

#include "Components/PanelSlot.h"       // UPanelSlot: 控件在父面板中的布局槽基类
#include "CoreMinimal.h"                // UE 核心最小依赖集合
#include "Json.h"                       // JSON 数据结构 (FJsonObject 等)
#include "JsonObjectConverter.h"        // JSON 与 UStruct/UObject 互转工具
#include "WidgetSlots/Core/WidgetDefines.h"  // 本模块控件相关的公共定义

// 声明一个专用于 Slot 转 JSON 的日志分类 (在 .cpp 中通过 DEFINE_LOG_CATEGORY 定义)
// 参数依次为: 日志分类名、默认日志级别(Log)、编译期允许的最高级别(All)
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreSlot2Json, Log, All);

/**
 * FSlot2JsonInterface
 * Slot 与 JSON 相互转换的抽象接口基类
 * 负责把 JSON 中记录的布局数据还原 (反序列化) 到 UPanelSlot 上,
 * 具体不同类型的 Slot (如 CanvasPanelSlot、HorizontalBoxSlot 等)
 * 由派生类实现各自的 FromJson 逻辑
 */
class FSlot2JsonInterface
{
public:
	// 默认构造函数 (无特殊初始化)
	FSlot2JsonInterface()
	{
	}

	// 虚析构函数: 保证通过基类指针删除派生类对象时能正确释放资源
	virtual ~FSlot2JsonInterface()
	{
	}

	/**
	 * 根据 JSON 数据设置面板槽 (PanelSlot) 的属性
	 * 这是一个通用实现: 利用反射把 JSON 字段批量映射到 Slot 的 UPROPERTY
	 * @param InJsonData - 包含槽属性数据的 JSON 对象
	 * @param PanelSlot  - 目标 UPanelSlot 实例 (将被写入属性)
	 * @return 成功设置属性返回 true, 否则返回 false
	 */
	bool SetPanelSlotProperties(const TSharedPtr<FJsonObject> InJsonData, UPanelSlot* PanelSlot);

	/**
	 * 从 JSON 对象构建/还原 Slot (纯虚函数, 必须由派生类实现)
	 * 不同类型的 Slot 布局字段不同, 派生类在此实现各自的解析与应用逻辑
	 * @param JsonData  - 源 JSON 对象
	 * @param PanelSlot - 目标 UPanelSlot 实例
	 * @return 还原成功返回 true, 否则返回 false
	 */
	virtual bool FromJson(const TSharedPtr<FJsonObject> JsonData, UPanelSlot* PanelSlot) = 0;
};