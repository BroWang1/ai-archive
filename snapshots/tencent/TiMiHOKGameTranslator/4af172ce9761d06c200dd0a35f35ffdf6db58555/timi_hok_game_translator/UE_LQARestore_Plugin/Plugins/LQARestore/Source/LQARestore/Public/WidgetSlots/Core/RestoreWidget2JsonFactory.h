#pragma once

#include "CoreMinimal.h"
#include "Json.h"

// 由 UHT(UnrealHeaderTool) 自动生成的反射代码头文件, 必须放在所有 UCLASS/USTRUCT 之后、本文件头文件包含的最后一行
#include "RestoreWidget2JsonFactory.generated.h"

// 前置声明, 避免在头文件中引入完整定义, 减少编译依赖
class FWidget2JsonInterface;   // Widget 与 JSON 相互转换的接口类
class UWidget;                 // UMG 控件基类
class URestoreWindowProxy;     // 还原窗口的代理对象, 承载还原上下文

/**
 * 控件还原元数据结构体
 * 保存从 JSON 还原出来的控件实例及其布局属性 (位置、尺寸、层级、附加属性)
 * 作为 WidgetFromJson 系列函数的返回结果, 供上层逻辑摆放和配置控件使用
 */
USTRUCT()
struct FRestoreWidgetMeta
{
	GENERATED_BODY()

public:
	/** 还原得到的控件实例指针 (由工厂创建并填充属性) */
	UPROPERTY()
	UWidget* WidgetIns = nullptr;

	/** 控件在窗口中的位置 (左上角坐标, 单位: 像素) */
	FVector2D WidgetPosition;

	/** 控件的尺寸 (宽、高，单位: 像素) */
	FVector2D WidgetSize;

	/** 渲染层级 / Z 轴顺序, 数值越大越靠上层显示 */
	int32 ZOrder = 0;

	/** 控件的附加属性, 以 JSON 对象形式存储 (如文本内容、OCR 标记、对齐方式等) */
	TSharedPtr<FJsonObject> Property;
};

/**
 * 控件工厂类
 * 负责根据 JSON 数据创建并还原 UMG 控件对象,
 * 处理控件属性和布局信息的反序列化
 * 所有方法均为静态方法, 无需实例化即可使用
 */
class FWidget2JsonFactory
{
public:
	/**
	 * 从 JSON 数据还原一个控件, 并填充完整的元数据
	 * 会创建控件实例, 并计算其位置、尺寸、层级以及附加属性数据
	 *
	 * @param InJsonObj          - 包含控件类型与属性数据的 JSON 对象
	 * @param InWindowSize       - 窗口尺寸, 用于计算相对位置 / 坐标系转换
	 * @param RestoreWindowProxy - 控件还原上下文的代理对象
	 * @return 返回包含还原控件及其元数据的 FRestoreWidgetMeta
	 */
	static FRestoreWidgetMeta WidgetFromJson(const TSharedPtr<FJsonObject>& InJsonObj, const FVector2D& InWindowSize,
		URestoreWindowProxy* RestoreWindowProxy);

	/**
	 * 从 JSON 数据还原一个面板 (容器) 控件, 仅填充基础元数据
	 * 与 WidgetFromJson 类似, 但针对面板容器做了简化处理 (不解析文本/OCR 相关属性)
	 *
	 * @param InJsonObj          - 包含控件类型与属性数据的 JSON 对象
	 * @param InWindowSize       - 窗口尺寸, 用于计算相对位置
	 * @param RestoreWindowProxy - 控件还原上下文的代理对象
	 * @return 返回包含还原面板控件及其元数据的 FRestoreWidgetMeta
	 */
	static FRestoreWidgetMeta WidgetFromJsonForPanel(const TSharedPtr<FJsonObject>& InJsonObj, const FVector2D& InWindowSize,
		URestoreWindowProxy* RestoreWindowProxy);

	/**
	 * 从 JSON 根对象中解析窗口尺寸
	 *
	 * @param RootObj - 根 JSON 对象, 其中的 meta 字段应包含 sizeX 与 sizeY
	 * @param OutSize - 输出参数, 用于返回解析得到的窗口尺寸
	 * @return 成功解析返回 true, 否则返回 false
	 */
	static bool DeserializeWindowSize(const TSharedPtr<FJsonObject>& RootObj, FVector2D& OutSize);

private:
	/**
	 * 根据 JSON 中的控件类型 (WidgetType 字段) 创建对应的 Widget2Json 接口实现
	 *
	 * @param InWidgetData - 包含 WidgetType 字段的 JSON 对象
	 * @return 对应控件类型的 FWidget2JsonInterface 实现的共享指针; 类型未知时返回 nullptr
	 */
	static TSharedPtr<FWidget2JsonInterface> MakeWidgetData(const TSharedPtr<FJsonObject> InWidgetData);

	/**
	 * 移除 JSON 对象中的委托 (Delegate) 字段, 因为委托无法被还原
	 * @param InJsonObj - 待清理的 JSON 对象
	 */
	static void RemoveDelegateFields(const TSharedPtr<FJsonObject>& InJsonObj);

	/**
	 * 移除 ObjectData 中的 Slots 字段, 避免还原过程中产生冲突 (插槽由父容器单独处理)
	 * @param InJsonObj - 包含 ObjectData 的 JSON 对象
	 */
	static void RemoveSlotsFromObjectData(const TSharedPtr<FJsonObject>& InJsonObj);

	/**
	 * 清理 JSON 对象, 移除所有无法还原的字段 (委托字段与插槽字段)
	 * @param InJsonObj - 待清理的 JSON 对象
	 */
	static void CleanJsonObject(const TSharedPtr<FJsonObject>& InJsonObj);

	/** 从 JSON 数据中获取控件位置, 并将坐标系从左下角原点转换为左上角原点 */
	static FVector2D GetWidgetPos(const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize);

	/**
	 * 从 JSON 数据中获取控件尺寸
	 * @param bUseAbsoluteSize - 为 true 时根据四角坐标计算绝对尺寸 (图片/按钮等);
	 *                           为 false 时读取 LocalSize 相对尺寸 (文本等)
	 */
	static FVector2D GetWidgetSize(
		const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize, bool bUseAbsoluteSize);

	/** 从各种文本类控件中提取文本内容 */
	static FString GetText(UWidget* UI);

	/** 从 JSON 中解析一个二维坐标点, 并进行坐标系转换 (左下角 -> 左上角) */
	static FVector2D DeserializePoint(const TSharedPtr<FJsonObject> InPosData, const FVector2D& InWindowSize);
};