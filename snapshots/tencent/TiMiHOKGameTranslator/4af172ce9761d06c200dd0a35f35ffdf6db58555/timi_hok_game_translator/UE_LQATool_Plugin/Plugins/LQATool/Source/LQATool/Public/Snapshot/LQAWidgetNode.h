#pragma once

#include "CoreMinimal.h"
#include "Fonts/SlateFontInfo.h"
#include "Json.h"
#include "Layout/ArrangedWidget.h"
#include "Layout/Geometry.h"
#include "Templates/SharedPointer.h"

/**
 * LQA 支持的控件 (Widget) 类型枚举
 * 作用：把 Slate 底层各种控件类型, 归一映射为 LQA 工具内部统一识别的类型,
 *       便于后续按类型做差异化的数据采集 / JSON 序列化处理
 */
enum class ELQAWidgetType : uint8
{
	// ===== 文本类控件 =====
	LQA_TextBlock,                 // 普通文本块
	LQA_RichText,                  // 富文本
	LQA_EditableText,              // 单行可编辑文本
	LQA_EditableTextBox,           // 单行可编辑文本框
	LQA_MultilineEditableText,     // 多行可编辑文本
	LQA_MultilineEditableTextBox,  // 多行可编辑文本框
	LQA_TextScroller,              // 文本滚动控件
	LQA_ComboBoxStringText,        // 字符串下拉框 (内含文本)
	LQA_LEDRichText,               // LED 风格富文本
	LQA_InputKeySelector,          // 按键选择器

	// ===== 输入类控件 =====
	LQA_ProgressBar,               // 进度条
	LQA_Slider,                    // 滑动条
	LQA_SpinBox,                   // 数值微调框

	// ===== 视觉类控件 =====
	LQA_Image,                     // 图片
	LQA_Button,                    // 按钮
	LQA_CheckBox,                  // 复选框
	LQA_Throbber,                  // 线性加载指示器
	LQA_CircularThrobber,          // 环形加载指示器
	LQA_Spacer,                    // 占位空白

	// ===== 容器类控件 =====
	LQA_UserWidget,                // 用户自定义控件 (蓝图 UserWidget)
	LQA_Canvas,                    // 画布面板
	LQA_RetainerBox,               // 渲染缓存盒
	LQA_ScrollBox,                 // 滚动盒
	LQA_VerticalBox,               // 垂直布局盒
	LQA_HorizontalBox,             // 水平布局盒
	LQA_ScaleBox,                  // 缩放盒
	LQA_SafeZone,                  // 安全区
	LQA_WrapBox,                   // 自动换行盒
	LQA_SizeBox,                   // 尺寸约束盒
	LQA_GridPanel,                 // 网格面板
	LQA_UniformGridPanel,          // 均匀网格面板
	LQA_Overlay,                   // 叠加层
	LQA_Border,                    // 边框容器
	LQA_BackgroundBlur,            // 背景模糊
	LQA_WidgetSwitcher,            // 控件切换器
	LQA_StackBox,                  // 堆叠盒
	LQA_WindowTitleBarArea,        // 窗口标题栏区域
	LQA_MenuAnchor,                // 菜单锚点
	LQA_InvalidationBox,           // 失效缓存面板
	LQA_ScrollBar,                 // 滚动条
	LQA_PostBufferUpdate,          // 后处理缓冲更新
	LQA_DynamicEntryBox,           // 动态条目框
	LQA_ListView,                  // 列表视图
	LQA_TileView,                  // 平铺视图
	LQA_TreeView,                  // 树形视图
	LQA_ExpandableArea,            // 可展开区域

	// ===== Slate 根类型复用 (多个 UMG 控件共用同一个 Slate 实现根, 按 UMG 类区分) =====
	LQA_NamedSlot,                 // 命名插槽 (Slate 根为 SBox)
	LQA_NativeWidgetHost,          // 原生控件宿主 (Slate 根为 SBox)
	LQA_Viewport,                  // 视口控件 (Slate 根为 SBox, 暂未登记)

	// 项目自定义控件类型可在此处追加

	// 未定义 / 未知控件类型 (默认值)
	LQA_Undefined
};

/**
 * LQA 支持的插槽 (Slot) 类型枚举
 * 插槽描述子控件在父容器中的布局方式; 此枚举把 Slate/UMG 的插槽类型
 * 归一为内部统一类型，便于识别并在数据中排除/标记特定插槽
 */
enum class ELQASlotType : uint8
{
	// ===== 标准插槽 =====
	LQA_ButtonSlot,                // 按钮插槽
	LQA_CanvasPanelSlot,           // 画布面板插槽
	LQA_ScrollBoxSlot,             // 滚动盒插槽
	LQA_VerticalBoxSlot,           // 垂直盒插槽
	LQA_HorizontalBoxSlot,         // 水平盒插槽
	LQA_ScaleBoxSlot,              // 缩放盒插槽
	LQA_SafeZoneSlot,              // 安全区插槽
	LQA_WrapBoxSlot,               // 换行盒插槽
	LQA_SizeBoxSlot,               // 尺寸盒插槽
	LQA_GridSlot,                  // 网格插槽
	LQA_UniformGridSlot,           // 均匀网格插槽
	LQA_OverlaySlot,               // 叠加层插槽
	LQA_BorderSlot,                // 边框插槽
	LQA_WidgetSwitcherSlot,        // 控件切换器插槽
	LQA_BackgroundBlurSlot,        // 背景模糊插槽
	LQA_StackBoxSlot,              // 堆叠盒插槽
	LQA_WindowTitleBarAreaSlot,    // 窗口标题栏区域插槽
	LQA_PanelSlot,                 // 单子容器内容插槽 (UPanelSlot 基类)

	// 项目自定义插槽类型可在此处追加

	// 未定义 / 未知插槽类型 (默认值)
	LQA_UndefinedSlot
};

/**
 * LQA 系统中的控件节点
 * 以树形结构表示 UI 控件层级, 携带控件的位置 (屏幕坐标)、类型、
 * 插槽类型以及源对象等信息, 是快照 (Snapshot) 数据采集的核心数据结构
 */
class LQATOOL_API FLQAWidgetNode
{
public:
	/**
	 * 构造函数: 从 "已排布的控件(ArrangedWidget)" 构建节点
	 * @param InWidgetGeometry 包含几何信息 (Geometry) 与控件引用 (Widget) 的已排布控件
	 */
	explicit FLQAWidgetNode(const FArrangedWidget& InWidgetGeometry);

	/**
	 * 添加一个子节点
	 * @param InChildNode 待添加的子节点
	 */
	void AddChildNode(TSharedRef<FLQAWidgetNode> InChildNode);

	/**
	 * 清空所有子节点
	 */
	void ClearChildNodes();

	/**
	 * 获取所有子节点
	 * @return 子节点数组 (常量引用)
	 */
	const TArray<TSharedRef<FLQAWidgetNode>>& GetChildNodes() const;

	/**
	 * 获取控件类型。
	 * @return 控件类型枚举
	 */
	ELQAWidgetType GetNodeType() const
	{
		return NodeType;
	}

	/**
	 * 获取插槽类型
	 * @return 插槽类型枚举
	 */
	ELQASlotType GetSlotType() const
	{
		return SlotType;
	}

	/**
	 * 为 "未定义类型" 控件填充通用 JSON 数据
	 * @param InObject 待填充的 JSON 对象
	 */
	void FillCommonDataForUndefinedWidget(TSharedPtr<FJsonObject> InObject) const;

	/**
	 * 填充控件的通用 JSON 数据
	 * @param InObject       待填充的 JSON 对象
	 * @param bNeedObjectData 是否需要附加源对象 (UObject) 的元数据
	 */
	void FillCommonData(TSharedPtr<FJsonObject> InObject, bool bNeedObjectData) const;

	/**
	 * 计算并设置 UI 的屏幕位置数据 (四角坐标、视口坐标、本地尺寸、包围盒等)
	 * @return 计算成功返回 true, 失败 (如 World 无效) 返回 false
	 */
	bool SetUIPosition();

	/**
	 * 设置节点唯一标识 (ID)
	 * @param Id 节点 ID
	 */
	void SetNodeId(int32 Id);

	/**
	 * 递归地为当前节点及其子节点设置包围盒 (BoxSize) 尺寸
	 */
	void SetBoxSize();

public:
	// ===== 控件与几何数据 =====
	/** 缓存的 Slate 控件引用 */
	TSharedPtr<SWidget> CachedWidget;

	/** 节点唯一标识 */
	int32 NodeId = -1;

	/** 控件名称 */
	FName WidgetName;

	/** 源 UObject 的弱引用 (通常为对应的 UWidget) */
	TWeakObjectPtr<UObject> SourceObject;

	/** Slate 根类型复用组内的 UMG 侧类标识 (如 "NamedSlot"), 1:1 类型为 None */
	FName WidgetClassTag;

	/** 缓存的几何信息 */
	FGeometry CachedGeometry;

	/** 图层 ID */
	int32 LayerId = -1;

	// ===== 位置数据 (屏幕坐标系) =====
	/** 左下角坐标 */
	FVector2D LeftBottomPos = FVector2D::ZeroVector;

	/** 左上角坐标 */
	FVector2D LeftUpperPos = FVector2D::ZeroVector;

	/** 右上角坐标 */
	FVector2D RightUpperPos = FVector2D::ZeroVector;

	/** 右下角坐标 */
	FVector2D RightBottomPos = FVector2D::ZeroVector;

	/** 视口坐标 */
	FVector2D ViewportPos = FVector2D::ZeroVector;

	/** 本地尺寸 */
	FVector2D LocalSize = FVector2D::ZeroVector;

	/** 包围盒 (2D) */
	FBox2D BoxSize = FBox2D(FVector2D::ZeroVector, FVector2D::ZeroVector);

	/** 包围盒是否有效 */
	bool bBoxIsValid = false;

	/** 基础插槽类型 (原始类名字符串) */
	FString BaseSlotType;

	/** 命名插槽名称 */
	FName SlotName;

	/** 基础控件类型 (原始类名字符串) */
	FString BaseWidgetType;

private:
	/**
	 * 处理控件类型识别与元数据提取 (构造时调用的核心逻辑)
	 * @param InWidget 待处理的 Slate 控件
	 */
	void HandleWidget(const TSharedRef<SWidget>& InWidget);


	/**
	 * 将插槽类型名 (字符串) 转换为枚举
	 * @param SlotTypeName 插槽类型名
	 * @return 插槽类型枚举(未匹配则返回 LQA_UndefinedSlot)
	 */
	static ELQASlotType GetSlotType(const FName& SlotTypeName);

	/**
	 * 获取四个角点坐标组成的 JSON 数组
	 * @return 角点坐标 JSON 数组
	 */
	TArray<TSharedPtr<FJsonValue>> GetCornerPosition() const;

	/**
	 * 获取包围盒尺寸组成的 JSON 数组
	 * @return 包围盒 JSON 数组
	 */
	TArray<TSharedPtr<FJsonValue>> GetBoxSizePosition() const;

	/**
	 * 将视口坐标转换为 JSON 对象
	 * @return 包含视口坐标的 JSON 对象
	 */
	TSharedPtr<FJsonObject> ConvertViewportPos2Json() const;

	/**
	 * 将本地尺寸转换为 JSON 对象
	 * @return 包含本地尺寸的 JSON 对象
	 */
	TSharedPtr<FJsonObject> ConvertLocalSize2Json() const;

	/**
	 * 将二维坐标转换为 JSON 对象
	 * @param InPos 待转换的坐标
	 * @return 包含坐标数据的 JSON 对象
	 */
	TSharedPtr<FJsonObject> ConvertPos2Json(const FVector2D& InPos) const;

	/**
	 * 判断当前节点是否为用户自定义控件 (UserWidget)
	 * @return 是则返回 true
	 */
	bool CheckNodeIsUserWidget() const;

private:
	/** 子控件节点数组 */
	TArray<TSharedRef<FLQAWidgetNode>> ChildNodes;

	/** 控件类型 (枚举) */
	ELQAWidgetType NodeType = ELQAWidgetType::LQA_Undefined;

	/** 插槽类型 (枚举) */
	ELQASlotType SlotType = ELQASlotType::LQA_UndefinedSlot;
};