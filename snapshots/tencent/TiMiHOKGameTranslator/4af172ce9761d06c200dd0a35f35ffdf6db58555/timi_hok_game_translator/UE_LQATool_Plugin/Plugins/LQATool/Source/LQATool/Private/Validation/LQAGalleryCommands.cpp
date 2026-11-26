// ============================================================================
// LQAGalleryCommands.cpp
// 功能: 注册并实现控制台命令 "LQA.BuildGallery", 用于在运行时 (PIE/Game)
//       快速构造 LQA 验证画廊控件, 并将其添加到视口, 便于做本地化质量
//       验证 (LQA, Localization Quality Assurance)
// ============================================================================

#include "CoreMinimal.h"                 // UE 核心基础类型 (FString、TArray 等)
#include "LQABase.h"                      // 本插件基础定义, 包含日志分类 LogLQATool
#include "Blueprint/UserWidget.h"         // UUserWidget 及 CreateWidget 模板
#include "Engine/World.h"                 // UWorld 定义, 控件创建需要世界上下文
#include "HAL/IConsoleManager.h"          // 控制台命令管理器与自动注册类

// ----------------------------------------------------------------------------
// 根据引擎版本选择不同的画廊控件实现, 并统一别名为 FLQAGalleryClass,
// 使下方逻辑无需关心具体版本差异
// ----------------------------------------------------------------------------
#if ENGINE_MAJOR_VERSION >= 5
#include "Validation/LQAGalleryWidget_UE5.h"
using FLQAGalleryClass = ULQAGalleryWidget_UE5;   // UE5 及以上使用 UE5 版本控件
#else
#include "Validation/LQAGalleryWidget_UE4.h"
using FLQAGalleryClass = ULQAGalleryWidget_UE4;   // UE4 使用 UE4 版本控件
#endif

// 使用匿名命名空间, 将回调函数限制在当前编译单元内, 避免符号污染全局
namespace
{
/**
 * 控制台命令回调: 构造验证画廊并加入视口
 *
 * 可选参数 (Args[0], 大小写不敏感):
 *   (无)        控件区 + 布局区
 *   Widgets     仅构造控件区 (文本 / 输入 / 展示 / 动态)
 *   Layout      仅构造布局区 (也接受 Layouts)
 *   Bug         仅构造显示性质 BUG 示例区 (也接受 Bugs)
 *   Composite   全部内容 (画廊为纯 C++ 构建, 无独立 WBP 资产)
 *   All         全部内容
 *
 * @param Args  控制台传入的参数列表
 * @param World 命令执行时的世界上下文 (PIE/Game 下有效)
 */
void BuildGalleryCommand(const TArray<FString>& Args, UWorld* World)
{
	// 控件创建依赖有效的 World, 若在编辑器非运行态调用则直接返回并提示
	if (!World)
	{
		UE_LOG(LogLQATool, Warning, TEXT("[LQA.BuildGallery] Invalid World, run in PIE/Game."));
		return;
	}

	// 默认构造控件区与布局区
	bool bWidgets = true;
	bool bLayouts = true;
	bool bBugs = false;

	// 若带有参数, 则根据第一个参数决定构造范围
	if (Args.Num() > 0)
	{
		const FString Mode = Args[0].ToLower();   // 统一转小写, 做大小写不敏感匹配
		if (Mode == TEXT("widgets"))
		{
			bLayouts = false;                     // 仅控件: 关闭布局
		}
		else if (Mode == TEXT("layout") || Mode == TEXT("layouts"))
		{
			bWidgets = false;                     // 仅布局: 关闭控件
		}
		else if (Mode == TEXT("bug") || Mode == TEXT("bugs"))
		{
			bWidgets = false;
			bLayouts = false;
			bBugs = true;
		}
		else if (Mode == TEXT("composite") || Mode == TEXT("all"))
		{
			// 画廊为纯 C++ 构建, Composite 与 All 等价 (无独立 WBP 资产)
			bWidgets = true;
			bLayouts = true;
			bBugs = true;
		}
	}

	// 创建画廊控件实例, 使用 World 作为外部对象 (Outer) 与上下文
	FLQAGalleryClass* Gallery = CreateWidget<FLQAGalleryClass>(World, FLQAGalleryClass::StaticClass());
	if (!Gallery)
	{
		// 创建失败一般是类未正确加载或内存异常, 记录错误并返回
		UE_LOG(LogLQATool, Error, TEXT("[LQA.BuildGallery] Failed to create gallery widget."));
		return;
	}

	// 按照参数标志构建对应内容, 然后以较高的 ZOrder(10000) 添加到视口,
	// 确保画廊显示在大多数其他 UI 之上
	Gallery->BuildAll(bWidgets, bLayouts, bBugs);
	Gallery->AddToViewport(10000);

	// 输出构建结果日志, 便于确认实际构造了哪些部分
	UE_LOG(LogLQATool, Log, TEXT("[LQA.BuildGallery] Gallery added to viewport (Widgets=%d, Layouts=%d, Bugs=%d)."),
		bWidgets ? 1 : 0, bLayouts ? 1 : 0, bBugs ? 1 : 0);
}
}

// ----------------------------------------------------------------------------
// 静态全局对象: 在模块加载时自动向控制台注册 "LQA.BuildGallery" 命令,
// 在模块卸载 (对象析构) 时自动注销, 无需手动管理生命周期
//   - 第一个参数: 命令名称
//   - 第二个参数: 帮助说明 (在控制台中可查看)
//   - 第三个参数: 绑定到上面的静态回调函数的委托
// ----------------------------------------------------------------------------
static FAutoConsoleCommandWithWorldAndArgs GLQABuildGalleryCommand(
	TEXT("LQA.BuildGallery"),
	TEXT("构造 LQA 验证画廊 (全部常用控件与布局, 纯 C++), 可选参数: Widgets | Layout | Bug | Composite | All"),
	FConsoleCommandWithWorldAndArgsDelegate::CreateStatic(&BuildGalleryCommand));