// 引入对应的头文件, 获取 LogLQARestore 日志分类的声明
#include "LQABase.h"

/**
 * 定义 (实例化) 在 LQABase.h 中声明的 LogLQARestore 日志分类
 *
 * DECLARE_LOG_CATEGORY_EXTERN 只是 “声明”, 而 DEFINE_LOG_CATEGORY 才真正
 * “定义” 该日志分类对应的全局对象, 两者必须成对出现:
 *   - 声明放在头文件中 (供多个源文件共享引用);
 *   - 定义放在某一个 .cpp 文件中 (且整个模块中只能定义一次),
 *     否则会导致链接期 “重复定义” 或 “未定义符号” 的错误
 */
DEFINE_LOG_CATEGORY(LogLQARestore)