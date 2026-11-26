#include "WidgetSlots/Slot2JsonInterface.h"   // 本接口对应的头文件

#include "Snapshot/LQAWidgetNode.h"           // 控件节点定义 (ToJson 中会用到)
#include "Styling/SlateColor.h"               // Slate 颜色类型, Slot 序列化时可能涉及

// 定义 (实例化) 在头文件中声明的日志分类 LogLQAToolSlot2Json
// DECLARE_LOG_CATEGORY_EXTERN 负责声明, DEFINE_LOG_CATEGORY 负责在某个 .cpp 中定义, 二者需配对
DEFINE_LOG_CATEGORY(LogLQAToolSlot2Json);