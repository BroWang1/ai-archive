#pragma once

#include "CoreMinimal.h"

// =============================================================
// LQAWidgetConstants 命名空间
// -------------------------------------------------------------
// 集中声明 LQA (本地化质量保证) 控件在解析 JSON 数据时
// 所使用的公共键名 (Key) 常量
//
// 设计说明:
//  - 这里只做 extern 声明, 真正的字符串值定义放在对应的
//    .cpp 实现文件中 (WidgetDefines.cpp)
//  - 使用 extern 可避免在多个翻译单元 (.cpp) 中重复定义
//    同名全局变量而导致的链接错误 (重定义), 同时保证
//    整个工程共享同一份常量实例
//  - 将 JSON 键名统一收敛为常量, 便于集中维护、避免魔法
//    字符串散落各处造成的拼写不一致问题
// =============================================================
namespace LQAWidgetConstants
{
// JSON 中 “源字符串” 字段对应的键名, 表示原始 (未翻译) 文本内容
extern const FString SourceStringKey;

// JSON 中 “通用字符串” 字段对应的键名, 表示普通文本字符串数据
extern const FString CommonStrKey;

// JSON 中 “通用文本键” 字段对应的键名, 表示文本条目的唯一标识 Key
extern const FString CommonTextKey;

// JSON 中 “通用对象” 字段对应的键名, 表示嵌套的对象/结构化数据
extern const FString CommonObjectKey;
}