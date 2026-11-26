#pragma once

#include "CoreMinimal.h"
#include "Internationalization/TextLocalizationManager.h" // 文本本地化管理器, 用于获取命名空间/键等本地化信息
#include "Json.h"                                          // UE 的 JSON 基础类型 (FJsonObject 等)
#include "JsonObjectConverter.h"                           // JSON 与 UStruct/UObject 互转的工具类
#include "Snapshot/LQAWidgetNode.h"                        // LQA 控件节点定义 (FLQAWidgetNode)
#include "WidgetDefines.h"                                 // 公共常量定义 (如 CommonStrKey、CommonTextKey 等字段名)

// 声明本模块专用的日志分类: LogLQAToolWidget2Json
// 用于在 Widget 转 JSON 过程中输出日志, 便于调试与问题定位
DECLARE_LOG_CATEGORY_EXTERN(LogLQAToolWidget2Json, Log, All);

// 前向声明: 仅在接口中以指针/引用形式使用这些类型, 无需包含完整头文件, 可降低编译依赖
class UWidget;              // UMG 控件基类
class SWidget;              // Slate 控件基类
class FLQAWidgetNode;       // LQA 控件节点
struct FSlateColor;         // Slate 颜色结构
class UTexture;             // 纹理资源
class URestoreWindowProxy;  // 窗口还原代理

/**
 * 将控件 (Widget) 转换为 JSON 的接口基类
 * 提供文本本地化处理与对象转换等通用能力, 供各类具体控件转换器继承实现
 */
class FWidget2JsonInterface
{
public:
	/** 默认构造函数 */
	FWidget2JsonInterface() = default;

	/** 虚析构函数, 保证通过基类指针删除派生类对象时能正确释放资源 */
	virtual ~FWidget2JsonInterface() = default;

	/**
	 * 将一段文本 (FText) 写入 JSON, 并附带本地化信息 (源字符串与本地化键)
	 * @param JsonObj             目标 JSON 对象
	 * @param Text                源文本
	 * @param TextEntryName       显示文本的字段名 (默认: CommonStrKey)
	 * @param TextKeyName         本地化键的字段名 (默认: CommonTextKey)
	 * @param SourceStringKeyName 源字符串的字段名 (默认: SourceStringKey)
	 */
	static void WriteTextEntry_ToJson(const TSharedPtr<FJsonObject>& JsonObj, const FText& Text,
		const FString& TextEntryName = CommonStrKey, const FString& TextKeyName = CommonTextKey,
		const FString& SourceStringKeyName = SourceStringKey);

	/**
	 * 收集列表控件 (ListView/TileView/TreeView) 的条目文本
	 * 列表条目是运行时动态生成的 UserWidget, 其数据层 (ListItems 为 Transient) 不会随对象反射导出,
	 * 因此只能从已生成的条目控件树里抽取。这里剥掉 Slate 内部包装层 (SHorizontalBox/SVerticalBox/SListPanel),
	 * 逐条目提取第一个文本节点, 作为 ListItems 数组元素 (字段与普通文本节点一致: textStr/TextKey/SourceString)。
	 *
	 * @param InWidget     列表控件节点
	 * @param OutListItems 输出: 每个条目文本对应的 JSON 对象
	 */
	static void CollectListEntryTexts(
		const TSharedPtr<FLQAWidgetNode>& InWidget, TArray<TSharedPtr<FJsonValue>>& OutListItems);

	/**
	 * 从本地化文本中提取命名空间 (Namespace) 与键 (Key)
	 * @param Text         源文本
	 * @param OutNamespace 输出参数: 命名空间
	 * @param OutKey       输出参数: 键
	 */
	static void GetTextNamespaceAndKey(const FText& Text, FString& OutNamespace, FString& OutKey);

	/**
	 * 将控件节点转换为 JSON (纯虚函数, 必须由派生类实现)
	 * @param InWidget         待转换的控件节点
	 * @param OutJsonObject    输出的目标 JSON 对象
	 * @param SharedTextureMap 共享纹理缓存, 用于复用已处理过的纹理, 避免重复转换
	 */
	virtual void ToJson(const TSharedPtr<FLQAWidgetNode> InWidget, const TSharedPtr<FJsonObject> OutJsonObject,
		TMap<FString, UTexture*>& SharedTextureMap) = 0;

	/**
	 * 将 JSON 数据反序列化为一个 UObject 实例
	 * @tparam T        要创建的对象类型
	 * @param JsonData  源 JSON 数据
	 * @param StructData 目标类型对应的 UStruct 定义
	 * @return 创建成功返回对象指针; 失败返回 nullptr
	 */
	template <class T>
	T* GetAsObject(const TSharedPtr<FJsonObject>& JsonData, const UStruct* StructData)
	{
		// 入参校验: JSON 数据无效或缺少类型定义时直接返回空
		if (!JsonData.IsValid() || !StructData)
		{
			return nullptr;
		}

		// 在临时包 (Transient Package) 中创建对象, 表示该对象不会被保存到磁盘
		T* ObjIns = NewObject<T>(GetTransientPackage());

		// 转换时需要跳过/特殊处理的属性标志位 (这些属性在 JSON<->UObject 转换中需被忽略)
		constexpr int64 ConversionFlags = CPF_BlueprintAssignable | CPF_BlueprintCallable | CPF_BlueprintAuthorityOnly |
										  CPF_TextExportTransient | CPF_InstancedReference;

		// 执行 JSON -> UStruct 的填充, 成功则返回已填充的对象
		if (FJsonObjectConverter::JsonObjectToUStruct(JsonData.ToSharedRef(), StructData, ObjIns, 0, ConversionFlags))
		{
			return ObjIns;
		}

		// 转换失败返回空指针
		return nullptr;
	}
};