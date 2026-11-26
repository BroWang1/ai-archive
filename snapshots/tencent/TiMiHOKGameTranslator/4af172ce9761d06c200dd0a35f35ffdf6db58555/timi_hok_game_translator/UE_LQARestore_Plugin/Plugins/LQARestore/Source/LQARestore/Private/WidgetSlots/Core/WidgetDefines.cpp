#include "WidgetSlots/Core/WidgetDefines.h"

// =============================================================
// 在实现文件 (.cpp) 中为头文件声明的常量提供唯一定义
// -------------------------------------------------------------
// 与头文件中的 extern 声明相对应:
//  - 头文件负责 “声明” (告诉编译器这些常量存在);
//  - 本文件负责 “定义” (为常量分配实际存储并赋值)
// 这样可确保全工程只有一处字符串实例, 既节省内存,
// 又避免多重定义的链接冲突
//
// 使用 TEXT() 宏可确保字符串字面量在不同平台/字符集下
// 都以 UE 所需的 TCHAR 宽字符形式存储
// =============================================================
namespace LQAWidgetConstants
{
// “源字符串” 键名, 与 JSON 字段 "SourceString" 一一对应
const FString SourceStringKey = TEXT("SourceString");

// “通用字符串” 键名, 与 JSON 字段 "textStr" 一一对应
const FString CommonStrKey = TEXT("textStr");

// “通用文本键”键名, 与 JSON 字段 "TextKey" 一一对应
const FString CommonTextKey = TEXT("TextKey");

// “通用对象” 键名, 与 JSON 字段 "ObjectData" 一一对应
const FString CommonObjectKey = TEXT("ObjectData");
}