#include "LQAManager.h"

#include "Components/Image.h"
#include "Engine/GameEngine.h"
#include "Framework/Application/SlateApplication.h"
#include "Snapshot/LQAWidgetNodeUtil.h"
#include "Utils/LQAExportUtil.h"

// 静态单例指针的定义与初始化 (声明在头文件中)
ULQAManager* ULQAManager::Instance = nullptr;

// 子系统初始化: 调用父类初始化后, 将就绪标志置为 true, 表示 LQA 系统可用
void ULQAManager::Initialize(FSubsystemCollectionBase& Collection)
{
	Super::Initialize(Collection);
	bIsLQAReady = true;
}

// 子系统反初始化: 先清理所有 LQA 组件, 再重置单例指针, 最后调用父类反初始化
void ULQAManager::Deinitialize()
{
	DeInitAll();
	Instance = nullptr;
	Super::Deinitialize();
}

// 获取 LQA 管理器单例
ULQAManager* ULQAManager::GetLQAManager(UObject* GameIns)
{
	// 若已缓存且有效, 直接返回, 避免重复查找
	if (Instance && IsValid(Instance))
	{
		return Instance;
	}

	// 优先从传入的 GameInstance 中获取子系统
	const UGameInstance* GameInstance = Cast<UGameInstance>(GameIns);
	if (GameInstance)
	{
		Instance = GameInstance->GetSubsystem<ULQAManager>();
		return Instance;
	}

#if WITH_EDITOR
	// 编辑器下的 PIE (Play In Editor, 编辑器内运行) 模式不被推荐使用, 直接返回空并给出警告
	if (GWorld && GWorld->IsPlayInEditor())
	{
		UE_LOG(LogLQATool, Warning, TEXT("PIE mode is not recommended, please use Standalone mode."));
		return nullptr;
	}
#endif

	// 若上述方式均未取得, 则尝试从全局 GameEngine 的 GameInstance 中获取
	if (const UGameEngine* GameEngine = Cast<UGameEngine>(GEngine))
	{
		if (GameEngine->GameInstance)
		{
			Instance = GameEngine->GameInstance->GetSubsystem<ULQAManager>();
			UE_LOG(LogLQATool, Warning, TEXT("ULQAManager Get From GameEngine!"));
			return Instance;
		}
	}

	// 所有途径都未找到, 返回 nullptr
	return nullptr;
}

// 初始化所有 LQA 组件
void ULQAManager::InitAll()
{
	// 创建并显示 LQA 面板
	InitLQAWidget();
	// 移除世界 Tick 开始的委托绑定, 避免在初始化完成后仍被重复触发
	FWorldDelegates::OnWorldTickStart.RemoveAll(this);
}

// 反初始化所有 LQA 组件: 移除面板
void ULQAManager::DeInitAll()
{
	RemoveLQAWidget();
}

// 导出视图数据 (高级版)
void ULQAManager::LQADumpViewAdvanced(bool bContainsTextures, bool bNeedObjectData) const
{
	// 获取当前时间, 作为本次导出的统一时间戳 (用于数据文件与截图文件命名关联)
	const FDateTime CurTime = FDateTime::Now();
	// 导出视图数据, 返回对应的 WBP (Widget Blueprint, 控件蓝图) 名称
	const FString WBPName = FLQAExportUtil::DumpViewAdvanced(CurTime, bContainsTextures, bNeedObjectData);
	// 基于同一时间戳与 WBP 名称进行截图, 保证截图与数据一一对应
	FLQAExportUtil::ScreenShot(CurTime, WBPName);
}

// 创建 LQA 控件并添加到视口
void ULQAManager::InitLQAWidget()
{
	UE_LOG(LogLQATool, Log, TEXT("ULQAManager::InitLQAWidget()"));

	// 若 LQA 系统尚未就绪, 则不创建面板并给出警告
	if (!bIsLQAReady)
	{
		UE_LOG(LogLQATool, Warning, TEXT("LQA Module Invalid!"));
		return;
	}

	// 若已存在旧的面板实例, 先从父级移除并置空, 避免重复叠加
	if (LQAWidget)
	{
		LQAWidget->RemoveFromParent();
		LQAWidget = nullptr;
	}

	// 以当前 GameInstance 为 Owner 创建 LQA 面板控件
	LQAWidget = CreateWidget<ULQABaseView>(GetGameInstance());

	if (LQAWidget)
	{
		// 使用极高的 ZOrder (层级) 添加到视口, 确保面板显示在所有其他 UI 之上
		LQAWidget->AddToViewport(5000000);
	}
	else
	{
		// 创建失败时记录错误日志
		UE_LOG(LogLQATool, Error, TEXT("Create LQA Widget Failed!"));
	}
}

// 从视口中移除 LQA 控件
void ULQAManager::RemoveLQAWidget()
{
	UE_LOG(LogLQATool, Log, TEXT("ULQAManager::RemoveLQAWidget()"));

	// 若面板存在, 则从父级移除并置空指针, 释放引用
	if (LQAWidget)
	{
		LQAWidget->RemoveFromParent();
		LQAWidget = nullptr;
	}
}