#include "ToolPanel/LQABaseView.h"

#include "Blueprint/WidgetTree.h"           // WidgetTree: 用于以代码构造控件
#include "Components/CanvasPanelSlot.h"     // CanvasPanelSlot: 画布上子控件的布局槽
#include "Engine/Engine.h"
#include "Engine/GameInstance.h"            // UGameInstance
#include "Engine/LocalPlayer.h"             // ULocalPlayer
#include "Engine/World.h"                   // UWorld / 定时器管理
#include "LQAInputProcessor.h"              // 自定义输入预处理器
#include "LQAManager.h"                     // LQA 管理器, 负责实际 Dump 逻辑
#include "LQATool.h"                        // 模块类与日志分类
#include "Modules/ModuleManager.h"          // 模块管理器, 用于获取模块配置
#include "TimerManager.h"                   // 定时器

// 构造函数: 仅调用父类构造, 无额外初始化
ULQABaseView::ULQABaseView(const FObjectInitializer& ObjectInitializer) : Super(ObjectInitializer)
{
}

// 析构函数: 确保对象销毁时注销并释放输入预处理器
ULQABaseView::~ULQABaseView()
{
	CleanupInputProcessor();
}

// 以代码方式重建整个控件树
TSharedRef<SWidget> ULQABaseView::RebuildWidget()
{
	// WidgetTree 不存在时无法构造控件, 返回空控件
	if (!WidgetTree)
	{
		return SNullWidget::NullWidget;
	}

	// 创建根画布面板
	RootCanvasPanel = WidgetTree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("RootCanvasPanel"));
	if (!RootCanvasPanel)
	{
		return SNullWidget::NullWidget;
	}

	// 将根画布面板设置为控件树的根控件
	WidgetTree->RootWidget = RootCanvasPanel;

	// 创建各 UI 元素: 创建失败仅记录错误日志, 不中断整体构建
	if (!CreateDumpViewButton())
	{
		UE_LOG(LogLQATool, Error, TEXT("LQABaseView: Failed to create dump view button - UI may be incomplete"));
	}

	if (!CreateGetKeyButton())
	{
		UE_LOG(LogLQATool, Error, TEXT("LQABaseView: Failed to create get key button - UI may be incomplete"));
	}

	// 返回根画布面板对应的底层 Slate 控件
	return RootCanvasPanel->TakeWidget();
}

#if ENGINE_MAJOR_VERSION < 5
// [UE4] 关卡从世界移除时的虚函数重写: 清理输入预处理器
void ULQABaseView::OnLevelRemovedFromWorld(ULevel* InLevel, UWorld* InWorld)
{
	Super::OnLevelRemovedFromWorld(InLevel, InWorld);

	// 关卡被移除时清理输入预处理器, 避免悬空引用
	CleanupInputProcessor();
}
#else
// [UE5] 关卡从世界移除的委托回调: 清理输入预处理器
void ULQABaseView::HandleLevelRemovedFromWorld(ULevel* InLevel, UWorld* InWorld)
{
	// 关卡被移除时清理输入预处理器
	CleanupInputProcessor();
}

// [UE5] 对象销毁前注销关卡移除委托, 避免回调访问已失效对象
void ULQABaseView::BeginDestroy()
{
	if (LevelRemovedFromWorldHandle.IsValid())
	{
		FWorldDelegates::LevelRemovedFromWorld.Remove(LevelRemovedFromWorldHandle);
		LevelRemovedFromWorldHandle.Reset();
	}

	Super::BeginDestroy();
}
#endif

// 控件构造完成后的初始化: 注册委托、绑定按钮点击事件
void ULQABaseView::NativeConstruct()
{
	Super::NativeConstruct();

#if ENGINE_MAJOR_VERSION >= 5
	// [UE5] 注册关卡移除委托 (仅注册一次)
	if (!LevelRemovedFromWorldHandle.IsValid())
	{
		LevelRemovedFromWorldHandle = FWorldDelegates::LevelRemovedFromWorld.AddUObject(
			this, &ULQABaseView::HandleLevelRemovedFromWorld);
	}
#endif

	// 绑定 Dump 按钮点击事件
	if (DumpViewBtn)
	{
		DumpViewBtn->OnClicked.AddDynamic(this, &ULQABaseView::OnDumpViewClicked);
	}

	// 绑定 GetKey 按钮点击事件
	if (GetKeyBtn)
	{
		GetKeyBtn->OnClicked.AddDynamic(this, &ULQABaseView::OnGetKeyClicked);
	}
}

// Dump 按钮点击响应: 根据配置的延迟, 立即或延迟执行界面转储
void ULQABaseView::OnDumpViewClicked()
{
	float Delay = 0.0f;

	// 从模块配置中读取转储延迟时间
	if (FModuleManager::Get().IsModuleLoaded(TEXT("LQATool")))
	{
		FLQAToolModule& LQAToolModule = FModuleManager::GetModuleChecked<FLQAToolModule>(TEXT("LQATool"));
		Delay = LQAToolModule.GetLQADumpDelay();
	}

	// 没有有效世界则无法设置定时器, 直接返回
	UWorld* World = GetWorld();
	if (!World)
	{
		return;
	}

	// 延迟 <= 0 立即执行; 否则通过定时器延迟执行
	// 延迟的意义: 便于操作者先把游戏界面切换到目标状态, 再捕获
	if (Delay <= 0.f)
	{
		HandleDumpViewClicked();
	}
	else
	{
		FTimerHandle TimerHandle;
		World->GetTimerManager().SetTimer(TimerHandle, [this]() { HandleDumpViewClicked(); }, Delay, false);
	}
}

// GetKey 按钮点击响应: 切换按键捕获开关, 并同步更新按钮文本与捕获状态
void ULQABaseView::OnGetKeyClicked()
{
	bLQAEnableKeyDump = !bLQAEnableKeyDump;      // 翻转开关状态
	UpdateGetKeyButtonText(bLQAEnableKeyDump);    // 更新按钮文本 (On/Off)
	SetKeyCapture(bLQAEnableKeyDump);             // 启用/禁用输入捕获
}

// 执行实际的界面转储操作: 通过 LQAManager 导出当前界面层级与属性
void ULQABaseView::HandleDumpViewClicked() const
{
	// 逐级获取 LocalPlayer -> GameInstance -> LQAManager, 任一为空则放弃
	ULocalPlayer* LocalPlayer = GetOwningLocalPlayer();
	if (!LocalPlayer)
	{
		return;
	}

	UGameInstance* GameInstance = LocalPlayer->GetGameInstance();
	if (!GameInstance)
	{
		return;
	}

	ULQAManager* LQAManager = ULQAManager::GetLQAManager(GameInstance);
	if (!LQAManager)
	{
		return;
	}

	// 执行高级转储: 同时导出控件层级结构 (true) 与属性 (true)
	LQAManager->LQADumpViewAdvanced(true, true);
}

// 创建并配置 Dump View 按钮
bool ULQABaseView::CreateDumpViewButton()
{
	// 依赖的控件树或根画布缺失时直接失败
	if (!WidgetTree || !RootCanvasPanel)
	{
		return false;
	}

	// 创建按钮及其文本控件
	DumpViewBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("DumpView_Btn"));
	DumpViewBtnText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("TextBlock_Dump"));

	if (!DumpViewBtn || !DumpViewBtnText)
	{
		return false;
	}

	// 设置按钮文本并作为按钮子控件
	DumpViewBtnText->SetText(FText::FromString(TEXT("Dump")));
	DumpViewBtn->AddChild(DumpViewBtnText);

	// 将按钮加入画布, 并配置其布局 (锚点、对齐、位置、尺寸)
	UCanvasPanelSlot* CanvasSlot = RootCanvasPanel->AddChildToCanvas(DumpViewBtn);
	if (CanvasSlot)
	{
		CanvasSlot->SetAutoSize(false);                                               // 关闭自动尺寸, 使用固定尺寸
		CanvasSlot->SetAnchors(FAnchors(0.f, BUTTON_ANCHOR_Y, 0.f, BUTTON_ANCHOR_Y)); // 锚定到屏幕左侧中部
		CanvasSlot->SetAlignment(FVector2D(0.f, BUTTON_ANCHOR_Y));                     // 对齐方式
		CanvasSlot->SetPosition(FVector2D(0.f, 0.f));                                 // 位置: 最左侧
		CanvasSlot->SetSize(FVector2D(BUTTON_WIDTH, BUTTON_HEIGHT));                   // 固定尺寸
	}

	return true;
}

// 创建并配置 Get Key 按钮
bool ULQABaseView::CreateGetKeyButton()
{
	if (!WidgetTree || !RootCanvasPanel)
	{
		return false;
	}

	// 创建按钮及其文本控件
	GetKeyBtn = WidgetTree->ConstructWidget<UButton>(UButton::StaticClass(), TEXT("GetKey_Btn"));
	GetKeyBtnText = WidgetTree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), TEXT("GetKeyBtn_Text"));

	if (!GetKeyBtn || !GetKeyBtnText)
	{
		return false;
	}

	// 根据当前捕获状态初始化按钮文本, 并作为按钮子控件
	UpdateGetKeyButtonText(bLQAEnableKeyDump);
	GetKeyBtn->AddChild(GetKeyBtnText);

	// 将按钮加入画布并配置布局, X 方向偏移使其位于 Dump 按钮右侧
	UCanvasPanelSlot* CanvasSlot = RootCanvasPanel->AddChildToCanvas(GetKeyBtn);
	if (CanvasSlot)
	{
		CanvasSlot->SetAutoSize(false);
		CanvasSlot->SetAnchors(FAnchors(0.f, BUTTON_ANCHOR_Y, 0.f, BUTTON_ANCHOR_Y));
		CanvasSlot->SetAlignment(FVector2D(0.f, BUTTON_ANCHOR_Y));
		CanvasSlot->SetPosition(FVector2D(GETKEY_BUTTON_OFFSET_X, 0.f));              // X 偏移, 避免与 Dump 按钮重叠
		CanvasSlot->SetSize(FVector2D(GETKEY_BUTTON_WIDTH, BUTTON_HEIGHT));
	}

	return true;
}

// 根据按键捕获状态更新 Get Key 按钮文本
void ULQABaseView::UpdateGetKeyButtonText(bool bIsKeyEnabled)
{
	if (!GetKeyBtnText)
	{
		return;
	}

	// 启用显示 [On], 禁用显示 [Off]
	const FText ButtonText =
		bIsKeyEnabled ? FText::FromString(TEXT("GetKey\n   [On]")) : FText::FromString(TEXT("GetKey\n   [Off]"));
	GetKeyBtnText->SetText(ButtonText);
}

// 启用或禁用按键捕获: 向 Slate 注册/注销输入预处理器
void ULQABaseView::SetKeyCapture(bool bEnable)
{
	// Slate 未初始化时无法操作输入预处理器
	if (!FSlateApplication::IsInitialized())
	{
		UE_LOG(
			LogLQATool, Error, TEXT("LQABaseView: SlateApplication is not initialized - cannot manage input processor"));
		return;
	}

	FSlateApplication& SlateApp = FSlateApplication::Get();

	if (bEnable)
	{
		// 启用: 若尚未创建则创建输入预处理器, 然后向 Slate 注册
		if (!InputProcessor.IsValid())
		{
			InputProcessor = MakeShared<FLQAInputProcessor>();
			if (!InputProcessor.IsValid())
			{
				UE_LOG(LogLQATool, Error, TEXT("LQABaseView: Failed to create input processor"));
				return;
			}
		}
		SlateApp.RegisterInputPreProcessor(InputProcessor);
	}
	else
	{
		// 禁用: 若已存在则从 Slate 注销并释放
		if (InputProcessor.IsValid())
		{
			SlateApp.UnregisterInputPreProcessor(InputProcessor);
			InputProcessor.Reset();
		}
	}
}

// 清理输入预处理器: 注销、释放并复位状态标志 (供析构与关卡移除时调用)
void ULQABaseView::CleanupInputProcessor()
{
	if (InputProcessor.IsValid() && FSlateApplication::IsInitialized())
	{
		FSlateApplication::Get().UnregisterInputPreProcessor(InputProcessor);
		InputProcessor.Reset();
		bLQAEnableKeyDump = false;
	}
}