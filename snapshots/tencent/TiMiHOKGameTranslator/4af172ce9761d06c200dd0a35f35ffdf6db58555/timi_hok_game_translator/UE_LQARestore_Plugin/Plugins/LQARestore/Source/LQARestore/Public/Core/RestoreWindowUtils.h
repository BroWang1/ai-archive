#pragma once

#include "CoreMinimal.h"
#include "Engine/Texture2D.h"
#include "Json.h"
#include "Materials/MaterialInstanceConstant.h"
#include "PaperSprite.h"
#include "Styling/SlateBrush.h"

// 前置声明, 避免头文件间的循环依赖, 减少编译耦合
class UCanvasPanel;           // 画布面板控件
class UWidget;                // 所有 UMG 控件的基类
class URestoreWindowProxy;    // 窗口代理, 提供窗口创建与渲染相关 API
class UImage;                 // 图片控件

// 声明一个单播/多播委托: 当还原窗口被销毁时广播, 参数为窗口的 int32 标识
DECLARE_MULTICAST_DELEGATE_OneParam(FOnRestoreWindowDestroyed, int32);

/**
 * LQA 纹理的元数据结构
 * 用于记录某张纹理在图集中的 UV 坐标与尺寸信息
 */
struct FLQATextureMeta
{
	int32 TextureIndex;       // 纹理索引 (在纹理数组/图集中的序号)
	FVector2D TextureUV;      // 纹理在图集中的 UV 偏移坐标
	FVector2D TextureSize;    // 纹理的尺寸 (宽、高)
};

/**
 * UI 还原与校验的工具类
 * 提供窗口创建、控件还原以及 UI 树分析等一系列静态工具函数
 * 该类为纯工具类, 所有成员均为静态, 不需要实例化
 */
class FRestoreWindowUtils
{
public:
	// ========================================
	// 窗口创建与构建
	// ========================================

	/**
	 * 从 dump 文件创建并构建还原窗口
	 * @param DumpFilePath  dump 文件 (UI 数据快照) 的路径
	 * @param WindowProxy   窗口代理, 提供渲染相关 API
	 * @return 窗口是否成功创建
	 */
	static bool CreateWindow(const FString& DumpFilePath, URestoreWindowProxy* WindowProxy);

	/**
	 * 根据 dump 数据与基础 UI 数据构建窗口
	 * @param DumpFilePath   dump 文件路径
	 * @param WindowProxy    用于渲染的窗口代理
	 * @param BaseUIDataObj  基础 UI 数据的 JSON 对象 (可为空)
	 * @return 是否构建成功
	 */
	static bool BuildWindow(
		const FString& DumpFilePath, URestoreWindowProxy* WindowProxy, TSharedPtr<FJsonObject> BaseUIDataObj);

	/**
	 * 从 JSON 根对象中反序列化出窗口尺寸
	 * @param RootObj  包含窗口元数据的 JSON 根对象
	 * @param OutSize  输出参数：解析得到的窗口尺寸
	 * @return 反序列化是否成功
	 */
	static bool DeserializeWindowSize(const TSharedPtr<FJsonObject>& RootObj, FVector2D& OutSize);

	/**
	 * 在 JSON 节点树中查找并替换基础数据
	 * @param Node               待搜索与替换的 JSON 节点
	 * @param MatchParentWidget  需要匹配的父控件名称
	 * @param MatchWidgetName    需要匹配的控件名称
	 * @param ReplaceText        要替换成的文本内容
	 * @param ReplaceKey         要替换成的文本 Key
	 * @return 是否成功执行了替换
	 */
	static bool ReplaceBaseData(const TSharedPtr<FJsonObject>& Node, const FString& MatchParentWidget,
		const FString& MatchWidgetName, const FString& ReplaceText, const FString& ReplaceKey);

	// ========================================
	// 控件类型检测
	// ========================================

	/**
	 * 检查节点是否包含任意可显示控件 (文本或图片)
	 * @param JsonObject  待检查的 JSON 对象
	 * @return 若 (递归地) 包含文本或图片控件则返回 true
	 */
	static bool ContainsDisplayableWidget(const TSharedPtr<FJsonObject>& JsonObject);

	/**
	 * 检查节点是否仅包含文本控件 (不含图片)
	 * @param JsonObject  待检查的 JSON 对象
	 * @return 若 (递归地) 只包含纯文本控件则返回 true
	 */
	static bool ContainsOnlyTextWidget(const TSharedPtr<FJsonObject>& JsonObject);

	// ========================================
	// 校验与导出
	// ========================================

	/**
	 * 生成用于校验的 JSON 文件
	 * @param WindowProxy   包含控件数据的窗口代理
	 * @param ResultDirPath 输出目录路径
	 */
	static void GenerateCheckJson(URestoreWindowProxy* WindowProxy, const FString& ResultDirPath);

	// ========================================
	// 公有委托
	// ========================================

	// 还原窗口被销毁时触发的委托（携带窗口标识）
	static FOnRestoreWindowDestroyed OnRestoreWindowDestroyed;

private:
	// ========================================
	// 私有辅助函数
	// ========================================

	/**
	 * 反序列化 dump 数据并还原 UI 控件
	 * @param RootObj             JSON 根对象
	 * @param WindowProxy         提供渲染 API 的窗口代理
	 * @param InWindowSize        窗口尺寸
	 * @param RestoreWindowProxy  还原窗口代理实例
	 * @param ObjectParentWidget  父控件名称过滤条件 (默认空字符串表示不过滤)
	 */
	static void DeserializeData(const TSharedPtr<FJsonObject>& RootObj, URestoreWindowProxy* WindowProxy,
		const FVector2D& InWindowSize, URestoreWindowProxy* RestoreWindowProxy,
		const FString& ObjectParentWidget = TEXT(""));

	/**
	 * 检查节点是否包含指定类型列表中的任意控件类型
	 * @param JsonObject  待检查的 JSON 对象
	 * @param TypeList    要匹配的控件类型名称列表
	 * @return 若 (递归地) 找到任意匹配类型则返回 true
	 */
	static bool ContainsWidgetType(const TSharedPtr<FJsonObject>& JsonObject, const TArray<FName>& TypeList);

	/**
	 * 处理十六进制数据表示的背景图片
	 * @param HexData  表示 PNG 数据的十六进制字符串
	 * @return 保存后的背景图片文件路径 (失败时返回空字符串)
	 */
	static FString ProcessBackgroundImage(const FString& HexData);

	// ========================================
	// 私有静态数据
	// ========================================

	/** 纯文本控件类型集合 (不包含图片控件) */
	static const TArray<FName> PureTextWidgetTypes;

	/** 文本与图片控件类型集合 (包含所有可显示的 UI 元素) */
	static const TArray<FName> TextAndImageWidgetTypes;

	/** 用于校验的父控件名称列表 */
	static TArray<FString> AllCheckParentWidgets;
};