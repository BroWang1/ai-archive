#pragma once

#include "CoreMinimal.h"
#include "Engine/Texture.h"
#include "Json.h"

// UHT (虚幻头文件工具) 自动生成的反射代码, 必须作为最后一个 include
#include "Widget2JsonFactory.generated.h"

// 前向声明: 仅用到指针/引用, 无需包含完整头文件, 可减少编译依赖、加快编译
class FWidget2JsonInterface;  // 控件 -> JSON 转换器的通用接口
class UWidget;                // UMG 控件基类
class FLQAWidgetNode;         // LQA 快照系统中的控件节点 (封装了控件及其附加信息)
class UTexture2D;             // 2D 纹理
class URestoreWindowProxy;    // 还原窗口的代理对象

/**
 * @brief 控件元数据结构体, 用于存储单个控件的核心信息
 *
 * 包含控件实例、位置、尺寸以及 Z 层级 (Z-order),
 * 便于正确处理控件的层级关系与布局排版
 */
USTRUCT()
struct FWidgetMeta
{
	GENERATED_BODY()

public:
	/** 控件实例引用 (由 UPROPERTY 标记, 纳入 GC 管理, 避免被意外回收) */
	UPROPERTY()
	UWidget* WidgetIns = nullptr;

	/** 控件在二维空间中的位置 (默认零向量) */
	FVector2D WidgetPos = FVector2D::ZeroVector;

	/** 控件的尺寸 (宽、高，默认零向量) */
	FVector2D WidgetSize = FVector2D::ZeroVector;

	/** Z 层级, 用于深度排序 (数值越大越靠前显示) */
	int32 ZOrder = 0;
};

/**
 * @brief 控件转 JSON 的工厂类
 *
 * 该工厂提供一系列静态方法, 用于把各种类型的控件转换为对应的 JSON 表示,
 * 同时处理「已定义(支持的)」与「未定义(不支持的)」两类控件
 */
class FWidget2JsonFactory
{
public:
	/**
	 * @brief 将「未定义(不支持的)」控件转换为 JSON
	 * @param InWidget 待转换的控件节点
	 * @return 表示该未定义控件的 JSON 对象 (WidgetType 标记为 "UNDEFINE")
	 */
	static TSharedPtr<FJsonObject> UndefineWidget2Json(const TSharedPtr<FLQAWidgetNode>& InWidget);

	/**
	 * @brief 将控件转换为 JSON, 可选择是否附带对象数据
	 * @param InWidget 待转换的控件节点
	 * @param SharedTextureMap 共享纹理映射表, 用于复用纹理、减少冗余 (按引用传入以便回写)
	 * @param bNeedObjectData 是否在转换结果中包含对象数据
	 * @return 表示该控件的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> Widget2Json(const TSharedPtr<FLQAWidgetNode>& InWidget,
		TMap<FString, UTexture*>& SharedTextureMap, const bool bNeedObjectData);

private:
	/**
	 * @brief 根据控件类型创建对应的控件数据转换接口
	 * @param InWidgetNode 待分析的控件节点
	 * @return 指向相应控件转换器的共享指针; 若类型不支持则返回 nullptr
	 */
	static TSharedPtr<FWidget2JsonInterface> MakeWidgetData(const TSharedPtr<FLQAWidgetNode> InWidgetNode);

	/**
	 * @brief 从 JSON 数据中提取控件位置
	 * @param InWidgetData 源 JSON 控件数据
	 * @param InWindowSize 参考窗口尺寸, 用于坐标计算/换算
	 * @return 控件位置 (二维向量)
	 */
	static FVector2D GetWidgetPos(const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize);

	/**
	 * @brief 从 JSON 数据中提取控件尺寸
	 * @param InWidgetData 源 JSON 控件数据
	 * @param InWindowSize 参考窗口尺寸, 用于计算
	 * @param bUseAbsoluteSize 是否使用绝对尺寸 (true: 由四角点计算; false: 使用本地尺寸 LocalSize)
	 * @return 控件尺寸 (二维向量)
	 */
	static FVector2D GetWidgetSize(
		const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize, bool bUseAbsoluteSize);

	/**
	 * @brief 从 JSON 数据反序列化出一个坐标点, 并进行坐标系换算
	 * @param InPosData 包含位置数据的 JSON 对象
	 * @param InWindowSize 参考窗口尺寸, 用于坐标系换算 (Y 轴翻转)
	 * @return 反序列化后的坐标点 (二维向量)
	 */
	static FVector2D DeserializePoint(const TSharedPtr<FJsonObject> InPosData, const FVector2D& InWindowSize);
};