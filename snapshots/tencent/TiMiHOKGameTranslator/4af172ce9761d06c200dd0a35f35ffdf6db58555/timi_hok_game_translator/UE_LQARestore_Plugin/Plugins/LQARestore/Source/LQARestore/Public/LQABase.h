#pragma once

// 引入 Unreal Engine 核心最小依赖头文件,
// 包含了引擎开发中最常用的基础类型、宏与模板 (如 FString、TArray、日志宏等)
#include "CoreMinimal.h"

#if defined(UE_DISABLE_OPTIMIZATION)
#define LQA_DISABLE_OPTIMIZATION UE_DISABLE_OPTIMIZATION
#define LQA_ENABLE_OPTIMIZATION UE_ENABLE_OPTIMIZATION
#else
#define LQA_DISABLE_OPTIMIZATION PRAGMA_DISABLE_OPTIMIZATION
#define LQA_ENABLE_OPTIMIZATION PRAGMA_ENABLE_OPTIMIZATION
#endif

/**
 * 声明 LQA Restore 工具的通用日志分类 (Log Category)
 *
 * 使用 DECLARE_LOG_CATEGORY_EXTERN 在头文件中 “对外声明” 一个日志分类,
 * 以便本模块内任意源文件 include 该头文件后, 都能通过
 * UE_LOG(LogLQARestore, ...) 来输出日志
 *
 * 参数说明:
 *   - LogLQARestore : 日志分类名称 (在日志输出中作为前缀标识, 便于过滤与排查)
 *   - Log           : 默认的运行时日志级别 (低于该级别的日志默认不输出)
 *   - All           : 编译期允许的最高日志级别 (All 表示所有级别都会被编译保留)
 *
 * 说明: 该分类用于非特定子模块的通用日志记录
 */
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestore, Log, All)