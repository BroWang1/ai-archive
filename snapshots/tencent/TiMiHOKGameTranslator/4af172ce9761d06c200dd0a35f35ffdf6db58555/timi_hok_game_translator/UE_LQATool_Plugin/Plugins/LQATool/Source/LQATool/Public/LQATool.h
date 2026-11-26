#pragma once

#include "CoreMinimal.h"
#include "Modules/ModuleInterface.h"

/**
 * LQA 工具模块 (Language Quality Assurance, 语言质量保证)
 *
 * 该模块为虚幻引擎 (Unreal Engine) 项目提供语言质量保证相关功能,
 * 继承自 IModuleInterface, 是一个标准的 UE 插件模块入口类
 * 主要职责:
 *   - 在模块启动时注册控制台命令 (Console Command);
 *   - 维护一个全局的 “Dump 延迟时间” 配置, 供外部读写
 */
class FLQAToolModule : public IModuleInterface
{
public:
	/** ===== IModuleInterface 接口实现 ===== */

	/** 模块启动时调用: 用于执行初始化逻辑 (此处注册控制台命令) */
	virtual void StartupModule() override;

	/** 模块关闭时调用: 用于执行清理逻辑 (如注销命令、释放资源等) */
	virtual void ShutdownModule() override;

	/**
	 * 获取当前 LQA 的 Dump (数据导出) 延迟时间
	 * @return 当前延迟时间, 单位: 秒
	 */
	static float GetLQADumpDelay();

	/**
	 * 设置 LQA 的 Dump (数据导出) 延迟时间
	 * @param InDelay 延迟时间, 单位: 秒 (内部会被限制为 >= 0.0f, 负值会被钳制到 0)
	 */
	static void SetLQADumpDelay(float InDelay);

private:
	/**
	 * 注册 LQA 功能相关的控制台命令
	 * 声明为 const, 表示该函数不会修改当前对象的成员状态
	 */
	void RegisterConsoleCommands() const;

	/** 静态成员变量: 保存 Dump 延迟时间, 单位: 秒 (整个模块共享一份) */
	static float LQADumpDelay;
};