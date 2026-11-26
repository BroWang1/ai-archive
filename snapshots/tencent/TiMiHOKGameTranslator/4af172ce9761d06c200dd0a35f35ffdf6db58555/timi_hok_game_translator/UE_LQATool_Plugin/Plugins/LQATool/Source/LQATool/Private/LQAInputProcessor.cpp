#include "LQAInputProcessor.h"

/**
 * 每帧更新逻辑
 * 当前 LQA 输入处理器不需要逐帧处理任何内容, 因此函数体为空
 * 保留该重写是为了满足 IInputProcessor 接口的纯虚函数要求
 */
void FLQAInputProcessor::Tick(const float DeltaTime, FSlateApplication& SlateApp, TSharedRef<ICursor> Cursor)
{
	// 目前无需任何逐帧 (Tick) 处理逻辑
}

/**
 * 处理鼠标按键按下事件
 * 仅关心 "鼠标右键" 的按下: 当检测到右键按下时，将事件转发给
 * FLQAExportUtil::OnPointerDown 进行后续的控件检测与上报处理
 */
bool FLQAInputProcessor::HandleMouseButtonDownEvent(FSlateApplication& SlateApp, const FPointerEvent& MouseEvent)
{
	// 判断本次触发的按键是否为鼠标右键
	if (MouseEvent.GetEffectingButton() == EKeys::RightMouseButton)
	{
		// 将右键按下事件交给 LQA 导出工具处理 (例如定位并记录当前点击的控件)
		FLQAExportUtil::OnPointerDown(MouseEvent);

		// 返回 true: 表示该右键事件已被本处理器消费, 阻止其继续向下层控件传递
		return true;
	}

	// 非右键事件不做处理, 返回 false 让其正常传递给其他控件
	return false;
}