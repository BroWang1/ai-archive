#pragma once

#include "CoreMinimal.h"
#include "Json.h"
#include "Snapshot/LQAWidgetNode.h"

// 前向声明: Slot 转 Json 的接口类
// 这里只用到了它的指针类型, 无需包含完整头文件, 可减少编译依赖
class FSlot2JsonInterface;

/**
 * FSlot2JsonFactory —— Slot 转 Json 的工厂类
 *
 * 职责:
 *   根据 UI 控件节点 (FLQAWidgetNode) 所携带的 Slot 类型,
 *   选择并创建对应的序列化处理器, 再把该控件的 Slot (布局槽) 数据
 *   序列化为 JSON 对象
 *
 * 设计模式: 工厂模式 (Factory Pattern)
 *   - 将 “创建具体 Slot 处理器” 的逻辑集中在一处,
 *     调用方无需关心具体类型, 只需拿到最终的 JSON 结果
 */
class FSlot2JsonFactory
{
public:
	/**
	 * 将指定控件节点的 Slot 数据序列化为 JSON 对象 (对外统一入口)
	 * @param Widget 待序列化的控件节点 (共享指针)
	 * @return 序列化后的 JSON 对象; 若节点无效则返回空 JSON 对象
	 */
	static TSharedPtr<FJsonObject> Slot2Json(const TSharedPtr<FLQAWidgetNode>& Widget);

private:
	/**
	 * 根据控件节点的 Slot 类型创建对应的序列化处理器
	 * @param WidgetNode 控件节点 (共享指针)
	 * @return 对应类型的 Slot2Json 处理器; 若类型不支持或节点无效则返回 nullptr
	 */
	static TSharedPtr<FSlot2JsonInterface> MakeSlotData(const TSharedPtr<FLQAWidgetNode> WidgetNode);
};