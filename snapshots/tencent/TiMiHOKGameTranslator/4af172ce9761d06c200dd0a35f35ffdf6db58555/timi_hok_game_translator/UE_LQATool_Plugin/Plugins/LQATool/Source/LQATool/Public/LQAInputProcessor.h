#pragma once

// UE 核心最小头文件集, 提供基础类型 (如 float、TSharedRef 等)
#include "CoreMinimal.h"
// Slate 输入处理器接口, 自定义输入处理器必须继承该接口
#include "Framework/Application/IInputProcessor.h"
// LQA 导出工具类, 鼠标事件最终会转发给它处理
#include "Utils/LQAExportUtil.h"

/**
 * LQA 按键捕获功能的输入处理器
 *
 * 该类继承自 Slate 的 IInputProcessor 接口, 被注册到 FSlateApplication 后,
 * 能够在应用程序级别 (优先于普通控件) 拦截并处理输入事件
 * 主要用于捕获鼠标事件, 从而检测并上报用户与控件 (Widget) 的交互
 */
class FLQAInputProcessor : public IInputProcessor
{
public:
	// 使用默认虚析构函数, 确保通过基类指针释放时能正确析构派生类
	virtual ~FLQAInputProcessor() = default;

	/**
	 * 每帧调用一次, 用于更新输入处理器的状态
	 * @param DeltaTime 距离上一帧经过的时间 (秒)
	 * @param SlateApp  Slate 应用程序引用, 可用于访问应用级输入状态
	 * @param Cursor    光标接口引用, 可用于查询或控制鼠标光标
	 */
	virtual void Tick(const float DeltaTime, FSlateApplication& SlateApp, TSharedRef<ICursor> Cursor) override;

	/**
	 * 处理鼠标按键按下事件
	 * 在 Slate 将事件分发给普通控件之前被调用, 可用于全局拦截鼠标按下操作
	 * @param SlateApp   Slate 应用程序引用
	 * @param MouseEvent 鼠标事件数据, 包含按下的按键、屏幕坐标等信息
	 * @return 返回 true 表示事件已被本处理器消费 (不再向下传递); 返回 false 表示继续传递该事件
	 */
	virtual bool HandleMouseButtonDownEvent(FSlateApplication& SlateApp, const FPointerEvent& MouseEvent) override;
};