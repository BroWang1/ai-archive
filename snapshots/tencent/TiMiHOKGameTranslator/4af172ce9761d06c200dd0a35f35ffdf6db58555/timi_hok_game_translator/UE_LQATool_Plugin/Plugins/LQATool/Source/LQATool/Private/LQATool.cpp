#include "LQATool.h"

#include "Engine/GameEngine.h"   // 提供 GEngine、GameViewport 等引擎相关类型
#include "LQABase.h"             // LQA 基础定义 (如日志分类 LogLQATool 等)
#include "LQAManager.h"          // LQA 管理器, 负责具体的初始化/反初始化逻辑

// 定义本地化文本命名空间, 供 LOCTEXT 宏使用 (本文件作用域内有效)
#define LOCTEXT_NAMESPACE "FLQAToolModule"

// 初始化静态成员变量: Dump 延迟默认值为 0 秒 (即不延迟)
float FLQAToolModule::LQADumpDelay = 0.0f;

// 模块启动入口: 在模块被加载时由引擎自动调用
void FLQAToolModule::StartupModule()
{
	// 注册控制台命令, 使外部可通过控制台控制 LQA 工具
	RegisterConsoleCommands();
}

// 模块关闭入口: 在模块被卸载时由引擎自动调用 (此处暂无清理逻辑)
void FLQAToolModule::ShutdownModule()
{
}

// 获取当前的 Dump 延迟时间 (秒)
float FLQAToolModule::GetLQADumpDelay()
{
	return FLQAToolModule::LQADumpDelay;
}

// 设置 Dump 延迟时间 (秒), 并保证其不为负数
void FLQAToolModule::SetLQADumpDelay(float InDelay)
{
	// 使用 FMath::Max 将延迟钳制到 [0, +∞), 避免出现负值
	FLQAToolModule::LQADumpDelay = FMath::Max(0.0f, InDelay);
}

// 注册 LQA 相关的控制台命令
void FLQAToolModule::RegisterConsoleCommands() const
{
	// 注册 LQA 主控制台命令 "r.EnableLQATool"
	// 用途: 控制 LQA 按钮/功能的开关
	// 用法: r.EnableLQATool <0/1> [DelayInSeconds]
	//   第 1 个参数: 0 表示关闭, >=1 表示开启
	//   第 2 个参数 (可选): Dump 延迟时间, 单位秒
	IConsoleManager::Get().RegisterConsoleCommand(TEXT("r.EnableLQATool"),
		TEXT("Control the switch of LQA button. Usage: r.EnableLQATool <0/1> [DelayInSeconds]"),
		// 使用 Lambda 作为命令的回调委托, 接收命令行参数数组 Args
		FConsoleCommandWithArgsDelegate::CreateLambda(
			[this](const TArray<FString>& Args)
			{
				// ===== 第一步: 获取当前的 World (世界) 上下文 =====
				UWorld* CurrentWorld = nullptr;
				if (GEngine)
				{
					// 优先尝试获取当前 “正在游玩” 的 World (PIE 或运行时)
					if (GEngine->GetCurrentPlayWorld())
					{
						CurrentWorld = GEngine->GetCurrentPlayWorld();
					}
					// 若没有 Play World，则退而求其次, 使用 GameViewport 对应的 World
					else if (GEngine->GameViewport)
					{
						CurrentWorld = GEngine->GameViewport->GetWorld();
					}
				}

				// 若未能获取到有效的 World, 则记录警告并提前返回
				if (!CurrentWorld)
				{
					UE_LOG(LogLQATool, Warning, TEXT("Invalid world for r.EnableLQATool."));
					return;
				}

				// ===== 第二步: 获取 LQA 管理器实例 =====
				// 通过当前 World 获取 (或创建) 对应的 ULQAManager 单例对象
				ULQAManager* LQAManager = ULQAManager::GetLQAManager(CurrentWorld);
				if (!LQAManager)
				{
					// 获取失败时记录警告并返回
					UE_LOG(LogLQATool, Warning, TEXT("Failed to get ULQAManager instance."));
					return;
				}

				// ===== 第三步: 解析并处理命令行参数 =====
				// 只接受 1 个或 2 个参数的情况
				if (Args.Num() == 1 || Args.Num() == 2)
				{
					// 将第 1 个参数解析为整数开关值 (0=关, >=1=开)
					int32 Switch = FCString::Atoi(*Args[0]);

					// 处理可选的第 2 个参数: 延迟时间
					if (Args.Num() >= 2)
					{
						// 将第 2 个参数解析为浮点数 (秒)
						float Delay = FCString::Atof(*Args[1]);
						// 设置延迟 (内部会钳制为非负)
						FLQAToolModule::SetLQADumpDelay(Delay);
						UE_LOG(LogLQATool, Log, TEXT("Set LQA dump delay to %f seconds."), Delay);
					}

					// 根据开关值执行 “开启 / 关闭” 逻辑
					if (Switch == 0)
					{
						// 关闭: 反初始化所有 LQA 相关功能
						LQAManager->DeInitAll();
						UE_LOG(LogLQATool, Log, TEXT("LQA Tool Disabled."));
					}
					else if (Switch >= 1)
					{
						// 开启: 初始化所有 LQA 相关功能
						LQAManager->InitAll();
						UE_LOG(LogLQATool, Log, TEXT("LQA Tool Enabled."));
					}
				}
				else
				{
					// 参数数量不合法, 提示正确用法
					UE_LOG(LogLQATool, Warning,
						TEXT("Invalid argument count for r.EnableLQATool. Usage: r.EnableLQATool <0/1>."));
				}
			}),
		ECVF_Default); // 控制台变量标志: 使用默认行为
}

// 取消本地化文本命名空间定义 (与前面的 #define 成对出现)
#undef LOCTEXT_NAMESPACE

// 实现并注册该模块: 第 1 个参数为模块类, 第 2 个参数为模块名 (LQATool)
IMPLEMENT_MODULE(FLQAToolModule, LQATool)