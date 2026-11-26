// LQABase.h
// LQA (Localization Quality Assurance, 本地化质量保证) 工具插件的基础定义头文件
// 本文件集中声明插件中通用的日志类别, 供插件内其他模块引用

#pragma once

// 引入虚幻引擎最核心的基础头文件,
// 提供基础类型、宏、容器、日志系统等最常用的核心功能
#include "CoreMinimal.h"

/**
 * LQA 基础定义 (LQA Base Definitions)
 * 包含 LQA 工具插件所需的通用日志功能及基础功能定义
 */

// 声明一个外部 (extern) 日志类别, 供插件内多个 .cpp 文件共享使用
//   - LogLQATool: 日志类别名称, 使用时通过 UE_LOG(LogLQATool, ...) 输出日志
//   - Log       : 默认日志级别 (编译期), 低于该级别的日志将被编译器剔除
//   - All       : 运行时允许输出的最高详细级别 (即不做额外限制, 全部可输出)
// 该宏只做 “声明”, 真正的 “定义” 需在对应的 .cpp 中使用 DEFINE_LOG_CATEGORY
DECLARE_LOG_CATEGORY_EXTERN(LogLQATool, Log, All);