#pragma once

#include "Components/PanelSlot.h"	// UPanelSlot: UMG 面板槽的基类
#include "CoreMinimal.h"			// UE 核心基础类型 (FString、FName、TSharedPtr 等)
#include "Json.h"					// JSON 相关类型 (FJsonObject 等)

// 前向声明: Slot 与 JSON 相互转换的接口类, 具体定义在 Slot2JsonInterface.h 中
class FSlot2JsonInterface;

/**
 * 工厂类: 负责根据 JSON 数据创建并还原 UMG 面板槽 (Panel Slot) 对象
 * 处理各种面板类型 (Canvas、Grid、HorizontalBox 等) 槽属性的反序列化
 */
class FSlot2JsonFactory
{
public:
	/**
	 * 根据 JSON 数据中指定的槽类型 (SlotType), 创建对应的 Slot2Json 接口实例
	 *
	 * @param JsonData - 包含 "SlotType" 和 "Slot" 字段的 JSON 对象
	 * @return 指向对应 FSlot2JsonInterface 实现的共享指针; 若槽类型未知则返回 nullptr
	 */
	static TSharedPtr<FSlot2JsonInterface> MakeSlotData(const TSharedPtr<FJsonObject> JsonData);

	/**
	 * 从 JSON 数据中还原 UPanelSlot 的属性
	 *
	 * @param SlotJsonObj - 包含槽类型及属性数据的 JSON 对象
	 * @param PanelSlot   - 目标 UPanelSlot 实例, 用 JSON 中的数据填充它
	 * @return 若槽还原成功返回 true, 否则返回 false
	 */
	static bool SlotFromJson(const TSharedPtr<FJsonObject>& SlotJsonObj, UPanelSlot* PanelSlot);
};