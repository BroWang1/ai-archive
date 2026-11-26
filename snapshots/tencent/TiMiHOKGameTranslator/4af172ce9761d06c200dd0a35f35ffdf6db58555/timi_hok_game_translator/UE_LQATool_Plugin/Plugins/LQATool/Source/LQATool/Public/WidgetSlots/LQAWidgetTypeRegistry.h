#pragma once

#include "CoreMinimal.h"
#include "Snapshot/LQAWidgetNode.h"   // ELQAWidgetType 枚举定义所在
#include "Templates/SubclassOf.h"     // TSubclassOf<> 智能类指针

// 前置声明: 此处只需用到 UWidget 作为类型约束的基类, 无需包含其完整定义
class UWidget;

/**
 * 控件类型登记项 (单条映射规则)
 *
 * 作用:
 *   描述一条 "Slate 类型名 + UMG 类约束 → LQA 控件类型枚举" 的映射规则
 *   采集端在遍历控件树时, 拿到运行时的 Slate 类型名与来源 UObject,
 *   逐条比对本结构体, 命中后即可得到对应的 LQA 控件类型
 *
 * 为什么需要 UMG 类约束 (WidgetClass):
 *   部分 UMG 控件在 Slate 层共用同一个实现根 (例如 USizeBox / UNamedSlot /
 *   UNativeWidgetHost 的 Slate 根都是 SBox), 此时仅凭 Slate 名无法区分,
 *   必须额外用 UMG 类做二次约束, 这类场景称为 "Slate 根类型复用",
 *   每个 UMG 类各登记一条并填写 WidgetClass; 一对一 (1:1) 的类型则留空
 */
struct FLQAWidgetTypeDesc
{
	/**
	 * Slate 层类型名, 即 SWidget::GetType() 的返回值
	 * 例如 "SBox"、"STextBlock", 带模板参数的类型配合 bPrefixMatch 使用
	 */
	FName SlateTypeName;

	/**
	 * UMG 类约束
	 *   - 为空 (nullptr): 仅按 Slate 名匹配, 用于 1:1 类型;
	 *   - 非空: 参与精确类 / IsA 匹配, 用于区分共用 Slate 根的多个控件
	 */
	TSubclassOf<UWidget> WidgetClass;

	/** 命中本条规则后对外返回的 LQA 控件类型枚举 (默认未定义) */
	ELQAWidgetType WidgetType = ELQAWidgetType::LQA_Undefined;

	/**
	 * 写入 JSON 的 UMG 侧标识 (对应 JSON 的 WidgetClass 字段)
	 * 仅在 "Slate 根类型复用" 时填写, 用于在导出数据中区分同根的不同控件;
	 * 1:1 类型无需填写, 保持 NAME_None
	 */
	FName WidgetClassTag;

	/**
	 * Slate 名是否按 "前缀" 匹配 (默认精确匹配)
	 * 用于带模板实参的 Slate 类型, 其运行时名字不固定,
	 * 例如 "SComboBox<FName>"、"SSpinBox<float>"
	 * 置 true 后, 只要运行时 Slate 名以 SlateTypeName 为前缀即视为命中
	 */
	bool bPrefixMatch = false;
};

/**
 * LQA 控件类型注册表 (全局唯一登记处)
 *
 * 作用:
 *   作为 "Slate 类型名 + UMG 类 → LQA 控件类型" 的唯一数据源,
 *   供采集端在识别控件类型时统一查询, 避免映射规则散落各处
 *
 * 使用规范:
 *   1. 新增控件类型只需修改 GetEntries() 中的登记表, 不要再另建映射表;
 *   2. "Slate 根类型复用" 的同名条目必须全部填写 WidgetClass,
 *      禁止保留一条无约束的同名兜底条目 (否则会被它抢先命中);
 *   3. 同一 Slate 名存在继承关系时, 依赖匹配算法 "精确类优先" 的特性保证正确性,
 *      因此条目之间的书写顺序不敏感;
 *   4. Slate 类型名带模板参数时 (如 SComboBox<FName>), 登记其前缀并置
 *      bPrefixMatch = true
 */
class LQATOOL_API FLQAWidgetTypeRegistry
{
public:
	/**
	 * 获取全部登记项
	 * 内部使用函数内 static 数组, 首次调用时构建一次并常驻, 后续直接复用
	 * @return 登记项数组的常量引用 (只读)
	 */
	static const TArray<FLQAWidgetTypeDesc>& GetEntries();

	/**
	 * 尝试为给定控件查找对应的类型登记项
	 *
	 * 匹配顺序 (优先级由高到低):
	 *   1) 精确类匹配: SourceObject 的类与 WidgetClass 完全相等;
	 *   2) IsA 匹配:   SourceObject 是 WidgetClass 的子类 (覆盖蓝图 WBP 子类);
	 *   3) 无约束条目: WidgetClass 为空, 仅按 Slate 名匹配 (1:1 类型)
	 *
	 * @param SlateTypeName Slate 层类型名 (SWidget::GetType())
	 * @param SourceObject  反射元数据中的来源对象 (通常是 UWidget), 可为空
	 * @return 命中的登记项指针; 未命中返回 nullptr
	 */
	static const FLQAWidgetTypeDesc* TryGetWidgetTypeDesc(const FName& SlateTypeName, const UObject* SourceObject);
};