// 包含本模块对应的头文件
#include "LQARestore.h"

// 包含 HTTP 请求配置工具类, 用于初始化插件的网络请求相关配置
#include "Utils/HttpUtils/HttpRequestConfig.h"

// 定义本地化文本的命名空间, 供 LOCTEXT 等本地化宏使用
// 使用后需在文件末尾用 #undef 取消定义, 避免影响其他文件
#define LOCTEXT_NAMESPACE "FLQARestoreModule"

/**
 * 模块启动入口
 * 引擎在加载本插件模块时自动调用, 用于执行初始化逻辑
 */
void FLQARestoreModule::StartupModule()
{
	// 从配置文件初始化 HTTP 请求配置 (如服务器地址、超时时间、请求头等)
	HttpRequestConfig::Initialize();
}

/**
 * 模块关闭入口
 * 引擎在卸载本插件模块 (或引擎退出) 时调用, 用于执行清理逻辑
 */
void FLQARestoreModule::ShutdownModule()
{
	// 该函数可能在关闭阶段被调用, 用于清理本模块占用的资源
	// 当前无需额外清理操作, 故留空
}

// 取消本地化文本命名空间的定义, 与前面的 #define 配对使用
#undef LOCTEXT_NAMESPACE

// 向引擎注册并实现本模块
// 第一个参数为模块类名, 第二个参数为模块名 (需与 .uplugin / .Build.cs 中的模块名一致)
// 该宏会生成模块的工厂函数, 使引擎能够正确创建并加载 FLQARestoreModule 实例
IMPLEMENT_MODULE(FLQARestoreModule, LQARestore)