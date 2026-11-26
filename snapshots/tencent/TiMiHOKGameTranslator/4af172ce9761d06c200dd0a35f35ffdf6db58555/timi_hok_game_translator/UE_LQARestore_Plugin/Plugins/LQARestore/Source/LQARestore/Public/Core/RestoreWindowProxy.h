#pragma once

#include "Components/CanvasPanel.h"
#include "Core/RestoreWindowUtils.h"
#include "CoreMinimal.h"
#include "Engine/TextureRenderTarget.h"
#include "Engine/TextureRenderTarget2D.h"
#include "WidgetSlots/Core/RestoreWidget2JsonFactory.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/SCompoundWidget.h"

#include "RestoreWindowProxy.generated.h"

// 前向声明: 根节点控件与 2D 纹理, 避免引入完整头文件以减少编译依赖
class URootObjWidget;
class UTexture2D;
class UWorld;
class INamedSlotInterface;

/**
 * LQA 还原窗口的代理 (Proxy) 类
 * 职责：管理还原窗口的整个生命周期以及控件 (Widget) 层级结构,
 *      包括窗口的创建、控件的递归添加以及相关资源的管理与释放
 */
UCLASS()
class URestoreWindowProxy : public UObject
{
	GENERATED_BODY()

public:
	// ========================================================================
	// 生命周期管理 (Lifecycle Management)
	// ========================================================================

	/**
	 * 初始化还原窗口代理, 传入窗口 ID 与游戏实例
	 * @param InWindowId      窗口的唯一标识 ID
	 * @param InGameInstance  游戏实例, 用于定时器 (Timer) 管理
	 */
	void Initialize(int32 InWindowId, UGameInstance* InGameInstance);

	/**
	 * 创建并显示还原窗口
	 * @param Size  屏幕空间下的窗口尺寸
	 */
	void CreateWindow(const FVector2D& Size);

	/** 销毁窗口并释放全部资源 */
	void DestroyWindow();

	// ========================================================================
	// 控件与面板管理 (Widget & Panel Management)
	// ========================================================================

	/**
	 * 根据 JSON 数据添加面板控件层级 (递归入口)
	 * @param OwningUserWidget              拥有当前面板的 UserWidget (顶层时为 nullptr)
	 * @param OwningUserWidgetParentPanel   该 UserWidget 的父面板
	 * @param OwningUserWidgetAdditionalInfo 该 UserWidget 的附加数据
	 * @param OwningUserWidgetMetaData      该 UserWidget 的元数据
	 * @param ParentPanel                   父面板控件 (用于 UNDEFINE 类型的继承)
	 * @param ParentPanelType               父面板类型
	 * @param ParentCorners                 父节点的四角坐标
	 * @param ParentScroll                  父节点是否可滚动
	 * @param ParentScrollCorners           父滚动框的四角坐标
	 * @param CurrentPanelJsonObject        当前面板的 JSON 数据
	 * @param WindowSize                    窗口尺寸
	 * @param RootPos                       根坐标偏移量
	 * @return 创建出的面板控件; 若失败则返回 nullptr
	 */
	UPanelWidget* AddPanel(UUserWidget* OwningUserWidget, UPanelWidget* OwningUserWidgetParentPanel,
		const TSharedPtr<FJsonObject>& OwningUserWidgetAdditionalInfo, FRestoreWidgetMeta OwningUserWidgetMetaData,
		UPanelWidget* ParentPanel, FString ParentPanelType, TArray<TSharedPtr<FJsonValue>> ParentCorners,
		bool ParentScroll, TArray<TSharedPtr<FJsonValue>> ParentScrollCorners,
		const TSharedPtr<FJsonObject>& CurrentPanelJsonObject, const FVector2D& WindowSize, FVector2D RootPos);

	// ========================================================================
	// 视觉更新 (Visual Updates)
	// ========================================================================

	/**
	 * 更新还原窗口的背景图片
	 * @param ImagePath  背景图片文件的路径
	 */
	void ProcessImageBackground(const FString& ImagePath);

	// ========================================================================
	// 校验与导出 (Validation & Export)
	// ========================================================================

	/**
	 * 生成用于校验的四角坐标检查数据
	 * @param CheckInfoFilePath   检查数据的输出文件路径
	 * @param CheckParentWidgets  需要校验的父控件列表
	 */
	void GenerateCheckCorners(FString CheckInfoFilePath, TArray<FString> CheckParentWidgets);

	// ========================================================================
	// 访问器 (Accessors)
	// ========================================================================

	/** 获取根控件, 通常用于截图捕获 */
	FORCEINLINE URootObjWidget* GetRootWidget() const
	{
		return RootObj;
	}

	/**
	 * 获取本次还原所依据的 dump session 目录
	 * 该目录下可能包含 Textures/<nameMD5>.png, 用于还原磁盘上不存在的运行时纹理
	 */
	FORCEINLINE const FString& GetSnapshotDirectory() const
	{
		return SnapshotDirectory;
	}

	/** 设置 dump session 目录 (通常为 dump json 文件所在的目录) */
	FORCEINLINE void SetSnapshotDirectory(const FString& InDirectory)
	{
		SnapshotDirectory = InDirectory;
	}

	// ========================================================================
	// 公有属性 (Public Properties)
	// ========================================================================

	/** 延迟初始化控件所使用的定时器句柄 */
	FTimerHandle TimerHandle;

	/** 控件渲染所用的共享纹理缓存 (键为路径, 值为纹理) */
	UPROPERTY()
	TMap<FString, UTexture2D*> SharedTextureMap;

private:
	// ========================================================================
	// 控件生命周期回调 (Widget Lifecycle Callbacks)
	// ========================================================================

	/** 初始化延迟结束、控件系统就绪后触发的回调 */
	UFUNCTION()
	void OnWidgetSystemReady();

	// ========================================================================
	// 控件与面板管理 (Widget & Panel Management)
	// ========================================================================

	/**
	 * 根据面板类型与父节点滚动状态, 判定当前的滚动上下文
	 * @param PanelType            当前面板控件类型
	 * @param PanelJsonObject      面板 JSON 数据
	 * @param ParentScroll         父节点是否可滚动
	 * @param ParentScrollCorners  父滚动框四角坐标
	 * @param OutIsScroll          输出: 当前面板是否可滚动
	 * @param OutScrollCorners     输出: 滚动框四角坐标
	 */
	void DetermineScrollContext(const FString& PanelType, const TSharedPtr<FJsonObject>& PanelJsonObject,
		bool ParentScroll, const TArray<TSharedPtr<FJsonValue>>& ParentScrollCorners, bool& OutIsScroll,
		TArray<TSharedPtr<FJsonValue>>& OutScrollCorners);

	/**
	 * 处理控件实际为 UserWidget (而非面板容器) 的情况
	 * 负责准备 UserWidget 的元数据 (插槽、尺寸、视频路径、四角坐标等)
	 * @param UserWidgetAsWidget          需要转换为 UserWidget 的控件
	 * @param UserWidgetJsonObject        UserWidget 的 JSON 数据
	 * @param UserWidgetParentPanel       该 UserWidget 的父面板
	 * @param ParentCorners               父节点四角坐标
	 * @param UserWidgetMetaData          UserWidget 元数据
	 * @param OutUserWidget               输出: UserWidget 实例
	 * @param OutUserWidgetParentPanel    输出: 父面板
	 * @param OutUserWidgetAdditionalData 输出: 附加数据 (插槽、尺寸、视频、四角等)
	 * @param OutUserWidgetMetaData       输出: 控件元数据
	 */
	void HandleUserWidget(UWidget* UserWidgetAsWidget, const TSharedPtr<FJsonObject>& UserWidgetJsonObject,
		UPanelWidget* UserWidgetParentPanel, const TArray<TSharedPtr<FJsonValue>>& ParentCorners,
		const FRestoreWidgetMeta& UserWidgetMetaData, UUserWidget*& OutUserWidget, UPanelWidget*& OutUserWidgetParentPanel,
		TSharedPtr<FJsonObject>& OutUserWidgetAdditionalData, FRestoreWidgetMeta& OutUserWidgetMetaData);

	/**
	 * 将 UserWidget 添加到根对象, 并进行可见性校验
	 * @param ParentUserWidget          包含该嵌套 UserWidget 的父 UserWidget
	 * @param CurrentPanel              来自嵌套 UserWidget 的面板
	 * @param ParentPanel               控件层级中的父面板
	 * @param UserWidgetAdditionalInfo  UserWidget 元数据 (尺寸、视频、四角等)
	 * @param CurrentPanelAdditionalInfo 当前面板的 JSON 数据
	 * @param UserWidgetMetaData        控件元数据 (位置、尺寸、ZOrder)
	 */
	void AddUserWidget(UUserWidget* ParentUserWidget, UPanelWidget* CurrentPanel, UPanelWidget* ParentPanel,
		const TSharedPtr<FJsonObject>& UserWidgetAdditionalInfo,
		const TSharedPtr<FJsonObject>& CurrentPanelAdditionalInfo, const FRestoreWidgetMeta& UserWidgetMetaData);

	// ========================================================================
	// JSON 处理工具 (JSON Processing Utilities)
	// ========================================================================

	/**
	 * 递归解包 UNDEFINE 占位节点, 向下寻找真正有效的节点
	 * @param NodeJson  面板节点 JSON
	 * @return 解包后的 JSON 对象; 若无效则返回 nullptr
	 */
	TSharedPtr<FJsonObject> UnwrapUndefinedNode(TSharedPtr<FJsonObject> NodeJson);

	/**
	 * 将某个字段从源 JSON 拷贝到目标 JSON
	 * @param Source     源 JSON
	 * @param Target     目标 JSON
	 * @param FieldName  需要拷贝的字段名
	 */
	void CopyJsonField(
		const TSharedPtr<FJsonObject>& Source, TSharedPtr<FJsonObject>& Target, const FString& FieldName);

	/**
	 * 判断 JSON 对象是否含有子节点
	 * @param JsonObject  待检查的 JSON 对象
	 * @return 存在子节点时返回 true
	 */
	bool HasChildNodes(const TSharedPtr<FJsonObject>& JsonObject) const;

	/**
	 * 还原命名插槽容器 (INamedSlotInterface, 如 UExpandableArea) 的各命名插槽内容
	 * 命名插槽容器不是 UPanelWidget, 其内容需通过 SetContentForSlot 挂载
	 * @param NamedSlotContainer  命名插槽容器控件
	 * @param ChildNodes          命名插槽子节点 JSON 数组 (每个子节点带 SlotName 字段)
	 * @param WindowSize          窗口尺寸
	 * @param WorldInstance       当前 World 实例
	 */
	void RestoreNamedSlotChildren(INamedSlotInterface* NamedSlotContainer,
		const TArray<TSharedPtr<FJsonValue>>& ChildNodes, const FVector2D& WindowSize, UWorld* WorldInstance);

	/**
	 * 递归还原命名插槽内容子树, 返回根控件及其元数据
	 * @param JsonObject    命名插槽内容节点的 JSON
	 * @param WindowSize    窗口尺寸
	 * @param WorldInstance 当前 World 实例
	 * @return 还原得到的控件元数据 (WidgetIns 为根控件)
	 */
	FRestoreWidgetMeta RestoreNamedSlotContent(
		const TSharedPtr<FJsonObject>& JsonObject, const FVector2D& WindowSize, UWorld* WorldInstance);

	/**
	 * 通过 Slate 反射元数据获取当前 World 实例
	 * @return 当前 World 实例; 失败返回 nullptr
	 */
	UWorld* GetWorldInstance() const;

	/**
	 * 拷贝子控件插槽数据, 并将其挂载到指定面板
	 * @param Panel            目标面板
	 * @param PanelPosition    面板位置
	 * @param PanelType        面板类型
	 * @param ChildJsonObject  子控件 JSON (含 Slot/SlotType 字段)
	 * @param ChildMeta        子控件还原元数据
	 * @param WorldInstance    当前 World 实例
	 */
	void AddChildToPanel(UPanelWidget* Panel, const FVector2D& PanelPosition, const FString& PanelType,
		const TSharedPtr<FJsonObject>& ChildJsonObject, const FRestoreWidgetMeta& ChildMeta, UWorld* WorldInstance);

	// ========================================================================
	// 文本与翻译处理 (Text & Translation Processing)
	// ========================================================================

	/**
	 * 处理叶子节点的文本与翻译数据
	 * 负责执行翻译，并从 objectData 中提取正文文本 (Text) 与提示文本 (HintText)
	 * @param LeafNodeJsonObject  叶子节点 JSON (会被就地修改)
	 */
	void ProcessLeafNodeTextData(TSharedPtr<FJsonObject>& LeafNodeJsonObject);

	// ========================================================================
	// 校验工具 (Validation Utilities)
	// ========================================================================

	/**
	 * 校验子控件是否与滚动框存在重叠
	 * @param ChildWidgetCorners  子控件四角坐标
	 * @param ScrollBoxCorners    滚动框四角坐标
	 * @param ChildWidgetName     控件名称 (用于日志输出)
	 * @return 子控件与滚动框存在重叠时返回 true
	 */
	bool ValidateScrollBoxOverlap(const TArray<TSharedPtr<FJsonValue>>& ChildWidgetCorners,
		const TArray<TSharedPtr<FJsonValue>>& ScrollBoxCorners, const FString& ChildWidgetName) const;

	/**
	 * 计算 UserWidget 与父容器的重叠比例, 判断是否应当忽略该控件
	 * @param UserWidgetPanelJsonObject  UserWidget 面板 JSON
	 * @param PanelJsonObject            当前面板 JSON
	 * @return 当重叠比例低于阈值时返回 true (表示应忽略)
	 */
	bool ShouldIgnoreUserWidget(
		const TSharedPtr<FJsonObject>& UserWidgetPanelJsonObject, const TSharedPtr<FJsonObject>& PanelJsonObject) const;

	// ========================================================================
	// 私有属性 (Private Properties)
	// ========================================================================

	/** 承载窗口内容的主画布面板 */
	UPROPERTY()
	UCanvasPanel* WindowPanel = nullptr;

	/** 承载整个 UI 层级结构的根对象控件 */
	UPROPERTY()
	URootObjWidget* RootObj = nullptr;

	/** 缓存的游戏实例, 用于定时器管理 */
	UPROPERTY()
	UGameInstance* CachedGameInstance = nullptr;

	/** 当前窗口的唯一标识 ID */
	int32 WindowId = 0;

	/**
	 * 本次还原所依据的 dump session 目录 (即 dump json 所在目录)
	 * 其中的 Textures/<nameMD5>.png 用于在资源路径无法加载时兜底还原运行时生成的纹理
	 */
	UPROPERTY()
	FString SnapshotDirectory;

	/** 标记控件是否已准备好可以进行绘制 */
	bool bIsReadyToDraw = false;
};