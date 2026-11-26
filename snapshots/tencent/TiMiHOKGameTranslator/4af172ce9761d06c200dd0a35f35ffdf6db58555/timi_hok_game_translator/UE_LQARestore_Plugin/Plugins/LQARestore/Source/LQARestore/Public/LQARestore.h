#pragma once

// UE 用户控件基类头文件 (UMG), 用于后续创建/引用蓝图 UserWidget
#include "Blueprint/UserWidget.h"
// UE 核心最小化头文件, 包含引擎最基础、最常用的类型与宏定义
#include "CoreMinimal.h"
// 模块管理器头文件, 提供 IModuleInterface 接口及模块注册相关宏 (如 IMPLEMENT_MODULE)
#include "Modules/ModuleManager.h"

/**
 * FLQARestoreModule
 * LQARestore 插件的主模块类
 * 继承自 IModuleInterface，是本插件在引擎中加载/卸载时的入口类
 * 引擎在加载该模块时会实例化此类, 并自动回调 Startup/Shutdown 生命周期函数
 */
class FLQARestoreModule : public IModuleInterface
{
public:
	/** IModuleInterface 接口实现 */

	// 模块启动时调用: 在此进行各类初始化工作 (如资源加载、配置读取、注册回调等)
	virtual void StartupModule() override;

	// 模块关闭时调用: 在此进行清理工作 (如释放资源、注销回调等), 与 StartupModule 对应
	virtual void ShutdownModule() override;
};