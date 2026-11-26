#pragma once

#include "CoreMinimal.h"
#include "Layout/ArrangedWidget.h"   // 提供 FArrangedWidget (控件 + 其布局几何信息的组合)
#include "Snapshot/LQAWidgetNode.h"  // 控件节点类型 FLQAWidgetNode 的定义

/**
 * 控件节点 (idget Node) 操作工具类
 *
 * 该类用于在 LQA (本地化质量保证) 快照流程中,
 * 根据 Slate 控件的布局结果构建一棵 “控件节点树”,
 * 便于后续对界面控件进行遍历、分析与截图标注等操作
 *
 * 说明: 这是一个纯静态工具类, 不需要实例化
 */
class LQATOOL_API FLQAWidgetNodeUtil
{
public:
	/**
	 * 根据已排布的控件几何递归构建控件节点树。
	 *
	 * 子控件几何取自布局排布结果, 因此视口外 (被 ScrollBox 等裁剪) 的子树同样会被采集;
	 * 从未参与排布的子树 (Collapsed 控件、WidgetSwitcher 非活动页) 不采集。
	 *
	 * 从未参与绘制的控件会先按其排布几何补一次 Tick, 使其在 Tick 中构建的内容
	 * (虚拟化列表行、按需创建的子控件) 就位; 控件自身视口内从未构建的内容不采集。
	 *
	 * @param InWidgetGeometry 已排布的控件 (含控件引用与几何信息)
	 * @param Index            节点序号计数器 (构建过程中持续自增)
	 * @return 构建好的控件节点树
	 */
	static TSharedRef<FLQAWidgetNode> GetNodeFromTree(const FArrangedWidget& InWidgetGeometry, int32& Index);
};