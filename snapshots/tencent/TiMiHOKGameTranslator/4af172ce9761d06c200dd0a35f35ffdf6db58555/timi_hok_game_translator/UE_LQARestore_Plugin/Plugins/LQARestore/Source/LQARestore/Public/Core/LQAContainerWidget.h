#pragma once

// UUserWidget 基类所在头文件, 提供 UMG 用户控件的基础实现
#include "Blueprint/UserWidget.h"
// UE 核心最小依赖集合 (基础类型、宏、模板等)
#include "CoreMinimal.h"

// 由 UHT (UnrealHeaderTool) 生成的反射代码头文件, 必须放在所有包含的最后一行
#include "LQAContainerWidget.generated.h"

/**
 * LQA 还原过程中使用的「最小化具体 UserWidget」, 纯粹作为 C++ 层的容器使用
 *
 * 设计原因:
 *   UUserWidget 本身是抽象类 (abstract), 无法被直接实例化 (CreateWidget / NewObject 会失败)
 *   因此这里派生出一个不添加任何额外逻辑的最小子类, 仅用于在代码中创建可用的控件实例,
 *   充当承载 LQA 还原内容的容器
 */
UCLASS()
class ULQAContainerWidget : public UUserWidget
{
	// UE 反射系统所需的样板宏, 自动生成构造、序列化等支持代码
	GENERATED_BODY()
};