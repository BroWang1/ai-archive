#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For DynamicEntryBox (动态条目框)
// --------------------------------------------------------------------
// 采集侧特点:
//   UDynamicEntryBox 的 Slate 根随 EntryBoxType 分别为 SHorizontalBox / SVerticalBox /
//   SWrapBox 等, 故 JSON 中 "WidgetType" 输出的是 Slate 根类型名,
//   真实 UMG 类型由 "WidgetClass": "DynamicEntryBox" 标识。
//
// 还原策略 (降级为等价布局容器):
//   UDynamicEntryBoxBase 继承自 UWidget 而非 UPanelWidget, 无法作为面板承载子控件;
//   而 Slate 根本身即标准布局容器。因此还原时按 EntryBoxType 降级为等价的
//   UPanelWidget 容器 (UHorizontalBox/UVerticalBox/UWrapBox/UOverlay):
//     - 视觉表现等价 (原控件渲染即由该 Slate 根完成);
//     - 可作为面板正常挂载 JSON 中采集到的动态条目子控件。
//   UWidget 通用属性 (Visibility/RenderOpacity 等) 由 ObjectData 反序列化继承。
class FLQA_DynamicEntryBox2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;
};
