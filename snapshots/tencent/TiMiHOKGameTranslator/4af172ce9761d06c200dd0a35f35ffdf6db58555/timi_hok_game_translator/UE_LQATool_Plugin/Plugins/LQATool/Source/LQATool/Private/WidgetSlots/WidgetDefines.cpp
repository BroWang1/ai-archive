// WidgetDefines.cpp
// 该文件负责提供 WidgetDefines.h 中声明的日志分类的实际定义
// 注意: 各 Widget 类型的 FName 常量 (LQAWidgetNames 命名空间)
//       并不在此定义, 而是在 LQAWidgetNode.cpp 中集中定义

#include "WidgetSlots/WidgetDefines.h"

// 定义日志分类 LogLQAToolWidget, 与头文件中的 DECLARE_LOG_CATEGORY_EXTERN 相对应
// 整个工程中该宏只能出现一次, 否则会导致重复定义的链接错误
DEFINE_LOG_CATEGORY(LogLQAToolWidget);