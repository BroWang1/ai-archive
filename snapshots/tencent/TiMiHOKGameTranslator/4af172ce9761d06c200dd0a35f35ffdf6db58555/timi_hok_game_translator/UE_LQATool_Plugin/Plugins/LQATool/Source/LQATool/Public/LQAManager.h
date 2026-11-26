#pragma once

#include "CoreMinimal.h"
#include "LQABase.h"
#include "Subsystems/GameInstanceSubsystem.h"
#include "ToolPanel/LQABaseView.h"

#include "LQAManager.generated.h"

/**
 * ULQAManager —— LQA (本地化质量保证 / Localization Quality Assurance) 工具的核心管理类
 *
 * 继承自 UGameInstanceSubsystem (游戏实例子系统), 其生命周期与 GameInstance 绑定:
 * 游戏实例创建时自动创建, 游戏实例销毁时自动销毁, 全局唯一
 * 主要职责: 管理 LQA 工具面板 UI 的创建/移除, 以及对外提供视图数据导出 (Dump) 功能
 */
UCLASS()
class LQATOOL_API ULQAManager : public UGameInstanceSubsystem
{
	GENERATED_BODY()

public:
	/**
	 * 初始化 LQA 管理器子系统 (由引擎在子系统创建时自动调用)
	 * @param Collection 子系统集合, 用于声明子系统之间的依赖关系
	 */
	virtual void Initialize(FSubsystemCollectionBase& Collection) override;

	/**
	 * 反初始化 LQA 管理器子系统 (由引擎在子系统销毁时自动调用), 用于释放资源
	 */
	virtual void Deinitialize() override;

	/**
	 * 获取 LQA 管理器单例实例
	 * @param GameIns 游戏实例对象 (可选); 传入时优先从该实例获取子系统
	 * @return ULQAManager 实例指针; 若未找到则返回 nullptr
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA")
	static ULQAManager* GetLQAManager(UObject* GameIns = nullptr);

	/**
	 * 初始化所有 LQA 组件 (主要是创建并显示 LQA 工具面板)
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA")
	void InitAll();

	/**
	 * 反初始化所有 LQA 组件 (主要是移除 LQA 工具面板)
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA")
	void DeInitAll();

	/**
	 * 导出 (Dump) 当前视图数据, 并支持高级选项
	 * @param bContainsTextures 是否一并导出纹理 (贴图) 数据
	 * @param bNeedObjectData   是否导出对象的元数据 (Object Metadata)
	 */
	UFUNCTION(BlueprintCallable, Category = "LQA")
	void LQADumpViewAdvanced(bool bContainsTextures = false, bool bNeedObjectData = false) const;

private:
	/**
	 * 创建 LQA 控件 (Widget) 并添加到视口 (Viewport) 中
	 */
	void InitLQAWidget();

	/**
	 * 从视口中移除 LQA 控件 (Widget)
	 */
	void RemoveLQAWidget();

	/** LQA 主控件 (面板 UI) 实例, 使用 UPROPERTY 标记以纳入 GC 管理, 防止被垃圾回收 */
	UPROPERTY()
	ULQABaseView* LQAWidget = nullptr;

	/** LQA 系统是否已就绪的标志位; 仅当为 true 时才允许创建面板 */
	bool bIsLQAReady = false;

	/** 单例实例指针, 便于通过静态方法 GetLQAManager 全局访问 */
	static ULQAManager* Instance;
};