#pragma once

#include "CoreMinimal.h"

// 声明一个外部日志分类 LogLQAToolWidget, 供整个 LQA Widget 模块使用
// - 第二个参数 Log: 默认的日志详细级别 (Verbosity)
// - 第三个参数 All: 编译期允许的最高日志级别
// 真正的定义 (DEFINE_LOG_CATEGORY) 位于 WidgetDefines.cpp 中
DECLARE_LOG_CATEGORY_EXTERN(LogLQAToolWidget, Log, All);

// ============================================================
// Widget 序列化时使用的通用 JSON 字段名 (Key)
// 统一在此定义, 避免在各处硬编码字符串、减少拼写错误
// ============================================================

// 源字符串字段: 存放控件原始 (未翻译) 的文本内容
static FString SourceStringKey = TEXT("SourceString");
// 通用文本字段: 存放当前显示的文本字符串
static FString CommonStrKey = TEXT("textStr");
// 文本键字段: 存放本地化 Key (用于定位该文本在本地化表中的条目)
static FString CommonTextKey = TEXT("TextKey");
// 对象数据字段: 存放控件对应的对象/节点数据块
static FString CommonObjectKey = TEXT("ObjectData");

// 无效文本键常量: 当某个节点缺少有效的 TextKey 时, 使用该占位值标记为无效
static const TCHAR* InvalidTextKey = TEXT(",INVALIDKEY");

// ============================================================
// Widget 类型的 FName 常量声明
// 说明：
//   - 这些常量的实际定义位于 LQAWidgetNode.cpp 中的 LQAWidgetNames 命名空间
//   - 在此以 extern 方式声明, 使得所有翻译单元 (每个 LQA_*2Json.cpp)
//     都能引用到同一份常量, 避免重复定义导致的链接错误
//   - 使用 FName 而非字符串, 可获得更快的比较性能 (基于名字索引)
// ============================================================
namespace LQAWidgetNames
{
// ---- 文本类控件 ----
extern const FName LQA_TextBlock;                   // 普通文本块
extern const FName LQA_RichTextBlock;               // 富文本块 (支持内嵌标记)
extern const FName LQA_EditableText;                // 单行可编辑文本
extern const FName LQA_EditableTextBox;             // 带边框的单行可编辑文本框
extern const FName LQA_MultilineEditableText;       // 多行可编辑文本
extern const FName LQA_MultilineEditableTextBox;    // 带边框的多行可编辑文本框
extern const FName LQA_TextScroller;                // 滚动文本 (跑马灯)
extern const FName LQA_InputKeySelector;            // 输入按键选择器

// ---- 下拉选择类控件 ----
extern const FName LQA_ComboBox;                    // 下拉框 (通用)
extern const FName LQA_ComboBoxString;              // 字符串下拉框
extern const FName LQA_ComboBoxKey;                 // 按键下拉框
extern const FName LQA_LEDRichTextBlock;            // LED 风格富文本块 (自定义控件)

// ---- 基础显示/交互控件 ----
extern const FName LQA_Image;                       // 图片
extern const FName LQA_Button;                      // 按钮
extern const FName LQA_UserWidget;                  // 用户自定义控件 (UserWidget)

// ---- 布局/容器类控件 ----
extern const FName LQA_Canvas;                      // 画布面板 (绝对定位)
extern const FName LQA_RetainerBox;                 // 渲染缓存容器
extern const FName LQA_ScrollBox;                   // 滚动容器
extern const FName LQA_CommonHierarchicalScrollBox; // 分层滚动框 (CommonUI, Slate 根 SCommonHierarchicalScrollBox)
extern const FName LQA_VerticalBox;                 // 垂直排列容器
extern const FName LQA_HorizontalBox;               // 水平排列容器
extern const FName LQA_ScaleBox;                    // 缩放容器
extern const FName LQA_SafeZone;                    // 安全区容器 (适配不同屏幕边距)
extern const FName LQA_WrapBox;                     // 自动换行容器
extern const FName LQA_SizeBox;                     // 固定尺寸容器
extern const FName LQA_NamedSlot;                   // 具名插槽
extern const FName LQA_NativeWidgetHost;            // 原生 Slate 控件宿主

// ---- 勾选/网格类控件 ----
extern const FName LQA_CheckBox;                    // 复选框
extern const FName LQA_GridPanel;                   // 网格面板
extern const FName LQA_UniformGridPanel;            // 均匀网格面板
extern const FName LQA_Overlay;                     // 层叠面板 (控件重叠)
extern const FName LQA_Border;                      // 边框容器
extern const FName LQA_BackgroundBlur;              // 背景模糊

// ---- 进度/加载提示类控件 ----
extern const FName LQA_ProgressBar;                 // 进度条
extern const FName LQA_Throbber;                    // 加载指示器 (点状)
extern const FName LQA_CircularThrobber;            // 环形加载指示器

// ---- 数值输入类控件 ----
extern const FName LQA_Slider;                      // 滑块
extern const FName LQA_SpinBox;                     // 数值微调框
extern const FName LQA_SpinBoxFloat;                // 浮点数值微调框
extern const FName LQA_Spacer;                      // 占位空白控件

// ---- 切换/特殊功能类控件 ----
extern const FName LQA_WidgetSwitcher;              // 控件切换器 (多页切换)
extern const FName LQA_StackBox;                    // 堆叠容器
extern const FName LQA_WindowTitleBarArea;          // 窗口标题栏区域
extern const FName LQA_MenuAnchor;                  // 菜单锚点 (弹出菜单)
extern const FName LQA_InvalidationBox;             // 失效缓存容器 (性能优化)
extern const FName LQA_ScrollBar;                   // 滚动条
extern const FName LQA_PostBufferUpdate;            // 后处理缓冲更新控件

// ---- 列表/视图类控件 ----
extern const FName LQA_ObjectTableRow;              // 列表行控件的 Slate 根 (按 UserWidget 采集)
extern const FName LQA_ListView;                    // 列表视图
extern const FName LQA_TileView;                    // 平铺视图
extern const FName LQA_TreeView;                    // 树状视图
extern const FName LQA_ExpandableArea;              // 可展开/折叠区域
}