#pragma once

#include "Blueprint/UserWidget.h"          // UUserWidget 基类
#include "Components/Button.h"              // UButton 按钮控件
#include "Components/CanvasPanel.h"         // UCanvasPanel 画布面板控件
#include "Components/TextBlock.h"           // UTextBlock 文本控件
#include "CoreMinimal.h"                    // UE 核心基础类型
#include "Runtime/Launch/Resources/Version.h" // 引擎版本宏 (ENGINE_MAJOR_VERSION 等)

#include "LQABaseView.generated.h"          // UHT 自动生成的反射代码, 必须放在最后

// 前向声明: 输入预处理器类, 用于捕获键盘输入 (头文件中仅声明, 减少编译依赖)
class FLQAInputProcessor;

/**
 * LQA 工具面板 —— LQA 工具的主 UI 控件
 * 以悬浮调试面板的形式, 提供 Dump (界面转储) 与 GetKey (按键捕获) 两大功能
 */
UCLASS()
class LQATOOL_API ULQABaseView : public UUserWidget
{
	GENERATED_BODY()

public:
	/**
	 * 构造函数
	 * @param ObjectInitializer UE 对象初始化器
	 */
	explicit ULQABaseView(const FObjectInitializer& ObjectInitializer);

	/**
	 * 析构函数 —— 确保对象销毁时正确清理 (注销输入预处理器)
	 */
	virtual ~ULQABaseView();

	/**
	 * 控件构造完成时调用
	 * 在此为按钮绑定点击事件、注册关卡移除委托
	 */
	virtual void NativeConstruct() override;

	/**
	 * 以代码方式重建控件结构
	 * 创建根画布面板以及各个按钮
	 * @return 根控件引用
	 */
	virtual TSharedRef<SWidget> RebuildWidget() override;

#if ENGINE_MAJOR_VERSION < 5
	/**
	 * [UE4] 当关卡从世界中被移除时调用 (虚函数重写)
	 * 用于在关卡卸载时清理输入预处理器, 防止悬空引用
	 * @param InLevel 被移除的关卡
	 * @param InWorld 包含该关卡的世界
	 */
	virtual void OnLevelRemovedFromWorld(ULevel* InLevel, UWorld* InWorld) override;
#else
	/**
	 * [UE5] 绑定到 FWorldDelegates::LevelRemovedFromWorld 的处理函数
	 * UE5 中该通知改为委托形式, 故需手动注册/注销
	 * @param InLevel 被移除的关卡
	 * @param InWorld 包含该关卡的世界
	 */
	void HandleLevelRemovedFromWorld(ULevel* InLevel, UWorld* InWorld);

	/**
	 * [UE5] 对象销毁时注销关卡移除委托, 避免委托回调访问已失效对象
	 */
	virtual void BeginDestroy() override;
#endif

protected:
	/**
	 * Dump View 按钮的点击事件处理函数
	 * 需用 UFUNCTION() 标记, 才能绑定到 OnClicked 动态委托
	 */
	UFUNCTION()
	void OnDumpViewClicked();

	/**
	 * Get Key 按钮的点击事件处理函数
	 * 需用 UFUNCTION() 标记, 才能绑定到 OnClicked 动态委托
	 */
	UFUNCTION()
	void OnGetKeyClicked();

	/**
	 * 执行实际的界面转储 (Dump) 操作
	 * 声明为 const, 表示不修改对象自身状态
	 */
	void HandleDumpViewClicked() const;

private:
	// ===== UI 布局常量 =====
	static constexpr float BUTTON_WIDTH = 120.0f;          // 普通按钮宽度
	static constexpr float BUTTON_HEIGHT = 120.0f;         // 按钮高度
	static constexpr float GETKEY_BUTTON_WIDTH = 150.0f;   // GetKey 按钮宽度 (略宽以容纳文本)
	static constexpr float BUTTON_ANCHOR_Y = 0.45f;        // 按钮在画布上的 Y 轴锚点 (屏幕中部偏上)
	static constexpr float GETKEY_BUTTON_OFFSET_X = 120.0f;// GetKey 按钮相对 X 偏移 (排在 Dump 按钮右侧)

	/**
	 * 创建并配置 Dump View 按钮
	 * @return 创建成功返回 true, 否则返回 false
	 */
	bool CreateDumpViewButton();

	/**
	 * 创建并配置 Get Key 按钮
	 * @return 创建成功返回 true, 否则返回 false
	 */
	bool CreateGetKeyButton();

	/**
	 * 根据当前状态更新 Get Key 按钮上的文本 (On / Off)
	 * @param bIsKeyEnabled 按键捕获当前是否已启用
	 */
	void UpdateGetKeyButtonText(bool bIsKeyEnabled);

	/**
	 * 启用或禁用按键捕获
	 * 启用时向 Slate 注册输入预处理器, 禁用时注销
	 * @param bEnable 是否启用按键捕获
	 */
	void SetKeyCapture(bool bEnable);

	/**
	 * 清理输入预处理器: 从 Slate 注销并释放, 重置状态标志
	 */
	void CleanupInputProcessor();

protected:
	/** 根画布面板, 所有子控件都挂载在其上 */
	UPROPERTY()
	UCanvasPanel* RootCanvasPanel;

	/** Dump View 按钮 */
	UPROPERTY()
	UButton* DumpViewBtn;

	/** Dump View 按钮上的文本 */
	UPROPERTY()
	UTextBlock* DumpViewBtnText;

	/** Get Key 按钮 */
	UPROPERTY()
	UButton* GetKeyBtn;

	/** Get Key 按钮上的文本 */
	UPROPERTY()
	UTextBlock* GetKeyBtnText;

	/** 用于按键捕获的输入预处理器 (共享指针, 非 UObject) */
	TSharedPtr<FLQAInputProcessor> InputProcessor;

	/** 按键转储 (捕获) 功能是否启用的状态标志 */
	bool bLQAEnableKeyDump = false;

#if ENGINE_MAJOR_VERSION >= 5
	/** [UE5] FWorldDelegates::LevelRemovedFromWorld 的委托句柄, 用于后续注销 */
	FDelegateHandle LevelRemovedFromWorldHandle;
#endif
};