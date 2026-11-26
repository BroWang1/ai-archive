#pragma once

#include "CoreMinimal.h"
#include "Http.h"					  // UE HTTP 核心类型 (IHttpRequest / IHttpResponse 等)
#include "HttpModule.h"				  // FHttpModule 模块单例, 用于创建请求
#include "Interfaces/IHttpResponse.h" // HTTP 响应接口定义
#include "Utils/HttpUtils/HttpRequestConfig.h" // HTTP 配置 (Host、Authorization、日志分类等)

// 声明「请求成功」委托, 携带一个 FHttpResponsePtr 参数 (服务器返回的响应体)
DECLARE_DELEGATE_OneParam(FOnRequestSuccess, FHttpResponsePtr);
// 声明「请求失败」委托, 无参数
DECLARE_DELEGATE(FOnRequestFail);

/**
 * HTTP 请求的用户自定义数据载体
 * 用于在异步请求发起到回调完成之间传递上下文信息
 */
struct FHttpRequestData
{
	FString DataId; // 本次请求关联的数据 ID, 回调时用于识别是哪条数据
};

/**
 * 底层 HTTP 请求辅助类
 * 提供基础的 HTTP 通信能力, 不维护任何业务状态 (无状态静态工具类)
 */
class LQARESTORE_API FHttpRequestHelper
{
public:
	/**
	 * 向服务器发送 dump 文件数据
	 * @param JsonData  - 需要发送的 JSON 格式数据
	 * @param ProjectId - 目标项目标识
	 */
	static void SendDumpFile(const FString& JsonData, const FString& ProjectId);

	/**
	 * 向服务器发送还原 (restore) 操作结果
	 * @param ProjectId         - 项目标识
	 * @param JobId             - 任务标识
	 * @param DataId            - 数据标识
	 * @param CheckInfoFilePath - 校验信息文件路径 (会作为文件内容上传)
	 * @param PngFilePaths      - 需要上传的 PNG 图片路径数组
	 * @param Language          - 语言设置
	 * @param Regression        - 回归测试标记
	 * @param CreateBug         - 是否创建 bug 的标记
	 * @param BugId             - bug 标识
	 * @param AISign            - AI 签名
	 */
	static void SendRestoreResult(const FString& ProjectId, const FString& JobId, const FString& DataId,
		const FString& CheckInfoFilePath, const TArray<FString>& PngFilePaths, const FString& Language,
		const FString& Regression, const FString& CreateBug, const FString& BugId, const FString& AISign);

	/**
	 * 从服务器获取 dump 数据
	 * @param DataId   - 要下载的数据标识
	 * @param FilePath - 服务器上的文件路径
	 */
	static void GetDumpData(const FString& DataId, const FString& FilePath);

	/**
	 * 从服务器获取项目信息
	 * @param ProjectId - 项目标识
	 */
	static void GetProjectInfo(const FString& ProjectId);

	/**
	 * 从服务器获取任务 (job) 数据
	 * @param JobId        - 任务标识
	 * @param IsRegression - 回归测试标记
	 * @param Language     - 语言设置
	 * @param Count        - 需要获取的条目数量
	 * @param MinId        - 分页用的最小 ID (起始游标)
	 * @param Modules      - 模块标识 (以下划线分隔, 内部会转换为逗号)
	 */
	static void GetJobData(const FString& JobId, const FString& IsRegression, const FString& Language,
		const FString& Count, const FString& MinId, const FString& Modules);

	// ===== 用于异步回调的静态委托 =====
	static FOnRequestSuccess OnRequestSuccess;				// 通用请求成功回调
	static FOnRequestSuccess OnRequestSuccessForDump;		// 获取 dump 数据成功回调
	static FOnRequestSuccess OnRequestSuccessForSendResult; // 发送结果成功回调
	static FOnRequestFail OnRequestFailForDump;				// 获取 dump 数据失败回调
	static FOnRequestFail OnRequestFailForSendResult;		// 发送结果失败回调

private:
	/**
	 * 创建 HTTP 请求对象并设置 URL 与请求方法
	 * @param URL  - 目标 URL
	 * @param Verb - HTTP 方法 (GET、POST 等)
	 * @return 线程安全的 HTTP 请求引用
	 */
	static TSharedRef<IHttpRequest, ESPMode::ThreadSafe> CreateRequest(const FString& URL, const FString& Verb);

	/**
	 * 统一处理 HTTP 响应, 根据结果分发到成功/失败委托
	 * @param Response        - HTTP 响应指针
	 * @param bSuccess        - 请求是否连接成功
	 * @param SuccessDelegate - 成功时调用的委托
	 * @param FailDelegate    - 失败时调用的委托
	 */
	static void HandleResponse(
		FHttpResponsePtr Response, bool bSuccess, FOnRequestSuccess& SuccessDelegate, FOnRequestFail& FailDelegate);

	// 通用请求完成回调 (SendDumpFile / GetProjectInfo / SendRestoreResult 使用)
	static void OnRequestResponseFinished(
		FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);

	// 获取 dump 数据请求完成回调 (携带 FHttpRequestData 用户数据)
	static void OnGetDataRequestResponseFinished(FHttpRequestPtr Request, FHttpResponsePtr Response,
		bool bConnectedSuccessfully, TSharedPtr<FHttpRequestData> UserData);

	// 获取任务数据请求完成回调
	static void OnGetJobDataRequestResponseFinished(
		FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully);
};