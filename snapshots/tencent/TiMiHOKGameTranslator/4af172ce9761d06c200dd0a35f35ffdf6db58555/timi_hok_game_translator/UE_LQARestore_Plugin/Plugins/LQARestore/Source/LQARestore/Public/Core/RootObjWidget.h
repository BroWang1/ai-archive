#pragma once

#include "Blueprint/UserWidget.h"
#include "Components/CanvasPanel.h"
#include "Components/Widget.h"
#include "CoreMinimal.h"

// 由 UHT (Unreal Header Tool) 自动生成的反射代码, 必须放在所有 include 的最后
#include "RootObjWidget.generated.h"

// 声明本模块专用的日志分类 LogLQARestoreRootObj (在 .cpp 中用 DEFINE_LOG_CATEGORY 定义)
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreRootObj, Log, All);

// 前置声明, 减少头文件依赖
class UCanvasPanel;
class UPaperSprite;

/**
 * LQA (Localization Quality Assurance, 本地化质量保证) 还原流程的根控件类
 * 职责：
 *   1. 动态管理控件层级 (纯 C++ 构建, 无需蓝图资源)
 *   2. 加载并管理媒体资源 (如背景图)
 *   3. 收集文本/图片控件信息并执行本地化质量检查
 */
UCLASS()
class URootObjWidget : public UUserWidget
{
	GENERATED_BODY()

protected:
	// ========================================================================
	// UUserWidget 接口重写
	// ========================================================================

	/** 纯 C++ 构建控件树 (不依赖任何蓝图资产), 在控件重建时调用 */
	virtual TSharedRef<SWidget> RebuildWidget() override;

public:
	// ========================================================================
	// LQA 检查相关数据
	// ========================================================================

	/** 需要在 LQA 检查中忽略的控件唯一 ID 列表 (如嵌入的 UserWidget 子控件) */
	TArray<int32> IgnoreUniqueIds;

	/** 需要进行 LQA 检查的文本控件 (使用弱引用, 避免阻止 GC 回收) */
	TArray<TWeakObjectPtr<UWidget>> CheckTextWidgets;

	/** 需要进行 LQA 检查的图片控件 (使用弱引用, 避免阻止 GC 回收) */
	TArray<TWeakObjectPtr<UWidget>> CheckImageWidgets;

	/** 与文本控件一一对应的 JSON 属性 (用于 LQA 校验, 下标与 CheckTextWidgets 对应) */
	TArray<TSharedPtr<FJsonObject>> TextProperty;

	/** 与图片控件一一对应的 JSON 属性 (用于 LQA 校验, 下标与 CheckImageWidgets 对应) */
	TArray<TSharedPtr<FJsonObject>> ImageProperty;

	// ========================================================================
	// 公有方法
	// ========================================================================

	/**
	 * 加载一张 PNG 图片并将其设置为全屏背景
	 * 内部会对每一步 (文件读取、解码、创建纹理) 进行校验并输出详细错误日志
	 * @param ImagePath - PNG 图片文件的绝对路径 (必须存在且为有效 PNG)
	 */
	void ProcessImageBackground(const FString& ImagePath);

	/**
	 * 将一个 UserWidget 添加到控件层级中, 并进行自定义定位与插槽配置
	 * @param UserWidgetInstance   - 要添加的 UserWidget 实例
	 * @param UserWidgetRootCanvas - 该 UserWidget 的根画布控件
	 * @param ParentPanel          - 要挂载到的父面板 (为空时默认使用 MainCanvas)
	 * @param AdditionalInfo       - 包含插槽配置与元数据的 JSON 对象
	 * @param ParentRootPosition   - 父控件的根位置偏移
	 * @param AbsolutePosition     - 控件要放置的绝对位置
	 * @param SlotSize             - 插槽尺寸
	 * @param DesiredSize          - UserWidget 的期望尺寸
	 * @param ZOrder               - 渲染层级 (Z 轴顺序)
	 * @param InPositionScale      - 位置缩放系数
	 * @param bShouldIgnore        - 为 true 时, 将该控件整个层级加入 LQA 忽略列表
	 */
	void AddUserWidget(UUserWidget* UserWidgetInstance, UWidget* UserWidgetRootCanvas, UPanelWidget* ParentPanel,
		TSharedPtr<FJsonObject> AdditionalInfo, FVector2D ParentRootPosition, FVector2D AbsolutePosition,
		FVector2D SlotSize, FVector2D DesiredSize, int32 ZOrder, int32 InPositionScale, bool bShouldIgnore);

	/**
	 * 将一个面板控件添加到另一个面板中, 并使用 JSON 配置插槽
	 * 若 JSON 插槽配置无效, 则回退为默认的画布插槽定位
	 * @param ParentPanel         父面板 (为空时默认使用 MainCanvas)
	 * @param ParentPanelType     父面板类型
	 * @param ParentRootPosition  父面板根位置偏移
	 * @param Panel               要添加的面板控件
	 * @param PanelType           被添加面板的类型
	 * @param PanelPosition       面板的屏幕位置
	 * @param PanelSize           面板尺寸
	 * @param UserWidgetInstance  UserWidget 实例 (若有值则直接返回, 因为 UserWidget 由 AddUserWidget 单独处理)
	 * @param PanelSlotInfo       包含插槽配置的 JSON 对象
	 * @param ZOrder              渲染层级
	 * @param InPositionScale     位置计算的缩放系数
	 */
	void AddPanel(UPanelWidget* ParentPanel, FString ParentPanelType, FVector2D ParentRootPosition, UPanelWidget* Panel,
		FString PanelType, FVector2D PanelPosition, FVector2D PanelSize, UUserWidget* UserWidgetInstance,
		TSharedPtr<FJsonObject> PanelSlotInfo, int32 ZOrder, int32 InPositionScale);

	/**
	 * 将一个子控件添加到指定面板中, 并进行相对定位
	 * 若子控件 JSON 属性中 needOCR 为真, 会将其注册到对应的 LQA 检查列表
	 * @param Panel        目标面板
	 * @param PanelPosition 父面板位置
	 * @param PanelType    面板类型标识
	 * @param Child        要添加的子控件
	 * @param ChildSlotInfo 子控件的 JSON 插槽配置
	 * @param ChildPosition 子控件的绝对位置
	 * @param ChildSize    子控件尺寸
	 * @param ChildZOrder  子控件渲染层级
	 * @param ChildProperty 用于 LQA 检查的 JSON 属性
	 * @param WorldInstance 当前 World 实例
	 */
	void AddWidgetInPanel(UPanelWidget* Panel, FVector2D PanelPosition, FString PanelType, UWidget* Child,
		TSharedPtr<FJsonValue> ChildSlotInfo, FVector2D ChildPosition, FVector2D ChildSize, int32 ChildZOrder,
		TSharedPtr<FJsonObject> ChildProperty, UWorld* WorldInstance);

	/**
	 * 计算控件在屏幕空间中的四个角点坐标
	 * 支持文本对齐方式, 以及图片基于 Alpha 通道的边缘裁剪
	 * @param Widget                控件对象
	 * @param WorldInstance         当前 World
	 * @param bIsText               为 true 时按文本方式计算并应用对齐
	 * @param Justification         水平对齐 (Left/Center/Right)
	 * @param VerticalJustification 垂直对齐 (Top/Center/Bottom)
	 * @return 四个角点: [左下, 左上, 右上, 右下]
	 */
	TArray<TSharedPtr<FJsonValue>> GetCorners(UWidget* Widget, UWorld* WorldInstance, bool bIsText,
		FString Justification = TEXT(""), FString VerticalJustification = TEXT(""));

private:
	/**
	 * 计算文本控件的角点坐标 (支持对齐方式)
	 * @return 计算成功返回 true
	 */
	bool CalculateTextCorners(UWidget* Widget, const FVector2D& PixelPos, const FVector2D& ViewportSize,
		const FString& Justification, const FString& VerticalJustification, FVector2D& OutLeftBottom,
		FVector2D& OutLeftUpper, FVector2D& OutRightUpper, FVector2D& OutRightBottom);

	/**
	 * 计算图片控件的角点坐标 (基于 Alpha 通道裁剪透明边缘)
	 * @return 计算成功返回 true
	 */
	bool CalculateImageCorners(UWidget* Widget, UWorld* WorldInstance, const FVector2D& ViewportSize,
		FVector2D& OutLeftBottom, FVector2D& OutLeftUpper, FVector2D& OutRightUpper, FVector2D& OutRightBottom);

	/**
	 * 针对 Texture2D 纹理, 根据 Alpha 边界对四个角点进行缩放裁剪
	 */
	void ApplyTextureAlphaScaling(UTexture2D* Texture, FVector2D& LeftBottom, FVector2D& LeftUpper,
		FVector2D& RightUpper, FVector2D& RightBottom);

	/**
	 * 针对 PaperSprite 精灵, 根据 Alpha 边界对四个角点进行缩放裁剪
	 */
	void ApplySpriteAlphaScaling(UPaperSprite* Sprite, FVector2D& LeftBottom, FVector2D& LeftUpper,
		FVector2D& RightUpper, FVector2D& RightBottom);

	/**
	 * 将四个角点坐标转换为 JSON 数值数组
	 */
	TArray<TSharedPtr<FJsonValue>> CornersToJsonArray(const FVector2D& LeftBottom, const FVector2D& LeftUpper,
		const FVector2D& RightUpper, const FVector2D& RightBottom);

public:
	/**
	 * 将二维向量位置转换为 JSON 对象格式
	 * @param InPos - 要转换的位置
	 * @return 包含 "x" 和 "y" 字段的 JSON 对象
	 */
	TSharedPtr<FJsonObject> ConvertPos2Json(const FVector2D& InPos);

	/**
	 * 收集所有已注册文本控件的 LQA 检查信息
	 * @param WorldInstance      - 当前 World 实例
	 * @param CheckParentWidgets - 用于过滤的父控件名列表 (为空时检查全部)
	 * @return 包含文本控件信息与角点坐标的 JSON 对象数组
	 */
	TArray<TSharedPtr<FJsonValue>> GetTextCheckInfo(UWorld* WorldInstance, TArray<FString> CheckParentWidgets);

	/**
	 * 收集所有已注册图片控件的 LQA 检查信息
	 * @param WorldInstance      - 当前 World 实例
	 * @param CheckParentWidgets - 用于过滤的父控件名列表 (为空时检查全部)
	 * @return 包含图片控件信息与角点坐标的 JSON 对象数组
	 */
	TArray<TSharedPtr<FJsonValue>> GetImageCheckInfo(UWorld* WorldInstance, TArray<FString> CheckParentWidgets);

	/**
	 * 校验文本是否存在常见的 LQA 缺陷, 并将错误码写入 TextInfo
	 * 检查项包括: 行高过小、HTML 标签不匹配、Hash 标签（#标记）不匹配
	 * @param TextInfo - 包含待校验文本属性的 JSON 对象
	 */
	void CheckTextBugs(TSharedPtr<FJsonObject> TextInfo);

	/**
	 * 初始化画布缩放, 以保证正确渲染
	 * 根据画布几何信息计算并存储位置缩放系数
	 */
	void InitScale();

	/**
	 * 获取当前位置缩放系数
	 * @return 位置缩放值 (默认为 1)
	 */
	int32 GetPositionScale() const
	{
		return PositionScale;
	}

	/** 作为根容器的主画布面板 (在 C++ 中动态创建) */
	UPROPERTY(Transient)
	UCanvasPanel* MainCanvas;

private:
	/**
	 * 从 JSON 配置 UserWidget 的插槽布局; 若配置不可用则应用默认画布定位
	 * @param UserWidgetInstance  要配置的 UserWidget
	 * @param AdditionalInfo      包含插槽配置的 JSON 对象
	 * @param ParentPanel         包含该控件的父面板
	 * @param ParentRootPosition  父控件根位置偏移
	 * @param AbsolutePosition    绝对屏幕位置
	 * @param SlotSize            插槽尺寸
	 * @param ZOrder              渲染层级
	 * @param InPositionScale     位置缩放系数
	 */
	void ConfigureUserWidgetSlot(UUserWidget* UserWidgetInstance, const TSharedPtr<FJsonObject>& AdditionalInfo,
		UPanelWidget* ParentPanel, const FVector2D& ParentRootPosition, const FVector2D& AbsolutePosition,
		const FVector2D& SlotSize, int32 ZOrder, int32 InPositionScale);

	/**
	 * 当 JSON 插槽配置不可用时, 应用默认的画布面板插槽配置
	 * @param PanelSlot           要配置的插槽 (必须是 UCanvasPanelSlot)
	 * @param ParentPanel         父画布面板
	 * @param ParentRootPosition  父控件根位置偏移
	 * @param AbsolutePosition    绝对屏幕位置
	 * @param SlotSize            插槽尺寸
	 * @param ZOrder              渲染层级
	 * @param InPositionScale     位置缩放系数
	 */
	void ApplyDefaultCanvasSlot(UPanelSlot* PanelSlot, UPanelWidget* ParentPanel, const FVector2D& ParentRootPosition,
		const FVector2D& AbsolutePosition, const FVector2D& SlotSize, int32 ZOrder, int32 InPositionScale);

	/**
	 * 收集 UserWidget 层级中所有控件的唯一 ID, 用于 LQA 忽略列表
	 * @param UserWidgetInstance 需要收集其层级 ID 的 UserWidget
	 */
	void CollectIgnoredWidgets(UUserWidget* UserWidgetInstance);

	// ========================================================================
	// 私有属性
	// ========================================================================

	/** 控件定位时使用的位置缩放系数 (默认为 1) */
	int32 PositionScale = 1;
};