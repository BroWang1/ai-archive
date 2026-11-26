#pragma once

#include "CoreMinimal.h"

/**
 * 声明一个专用于 LQARestore 插件 HTTP 模块的日志分类 (Log Category)
 *   - LogLQARestoreHttp: 日志分类名称, 使用 UE_LOG 时作为第一个参数
 *   - Log: 默认 (编译期) 日志详细级别, 低于该级别的日志会被编译掉
 *   - All: 运行期允许输出的最高详细级别 (不做运行期限制)
 * EXTERN 版本只做 `声明`, 真正的 `定义` 在 .cpp 中通过 DEFINE_LOG_CATEGORY 完成
 */
DECLARE_LOG_CATEGORY_EXTERN(LogLQARestoreHttp, Log, All);

/**
 * HttpRequestConfig 命名空间
 * ------------------------------------------------------------------
 * 集中管理 HTTP 请求所需的全局配置 (服务器地址、鉴权信息)
 * 这些配置从插件目录下的 Config/LQARestore.ini 文件读取,
 * 供插件内发起 HTTP 请求的各处统一复用
 */
namespace HttpRequestConfig
{
/** 从配置文件 (LQARestore.ini) 中加载 Host 与 Authorization, 需在使用前调用一次 */
void Initialize();

/**
 * 服务器主机地址 (已拼接 "http://" 前缀), 例如 "http://127.0.0.1:8080/api-pro"
 * 用于 API 接口 (拉任务 / 传结果), 可带网关路径前缀
 * 使用 LQARESTORE_API 导出宏, 保证跨模块可访问; extern 表示定义在 .cpp 中
 */
extern LQARESTORE_API FString Host;

/**
 * 文件下载基址 (已拼接 "http://" 前缀), 例如 "http://127.0.0.1:8080"
 * 专用于下载 dump 文件: 任务返回的 file_path 是域名根下的绝对路径 (/media/...),
 * 不带 API 网关前缀, 故与 Host 分开配置; 为空时回退使用 Host
 */
extern LQARESTORE_API FString FileHost;

/** HTTP 请求头使用的鉴权令牌 (Authorization),同样在 .cpp 中定义 */
extern LQARESTORE_API FString Authorization;
}