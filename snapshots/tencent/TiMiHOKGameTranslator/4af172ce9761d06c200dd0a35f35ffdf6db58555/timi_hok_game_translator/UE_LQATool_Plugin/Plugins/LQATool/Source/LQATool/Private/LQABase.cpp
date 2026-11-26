// LQABase.cpp
// 与 LQABase.h 配套的源文件, 负责对头文件中声明的日志类别进行实际定义

// 引入本模块的基础头文件, 获取 LogLQATool 日志类别的声明
#include "LQABase.h"

// 定义 (实例化) 在 LQABase.h 中通过 DECLARE_LOG_CATEGORY_EXTERN 声明的日志类别
// 整个插件中该日志类别只能被定义一次, 否则会产生重复定义的链接错误
// 定义之后, 插件内任意包含了 LQABase.h 的文件即可使用该日志类别输出日志
DEFINE_LOG_CATEGORY(LogLQATool)