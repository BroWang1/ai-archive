#include "Utils/HttpUtils/HttpRequestHelper.h"

#include "LQABase.h"
#include "Misc/FileHelper.h" // FFileHelper: 文件读取为字节数组
#include "Misc/Paths.h"		 // FPaths: 文件路径与存在性判断

// 关闭编译器优化 (通常用于调试, 便于单步跟踪 HTTP 组包逻辑)
LQA_DISABLE_OPTIMIZATION

// ===== 静态委托成员定义 (在头文件中声明, 此处分配存储空间) =====
FOnRequestSuccess FHttpRequestHelper::OnRequestSuccess;
FOnRequestSuccess FHttpRequestHelper::OnRequestSuccessForDump;
FOnRequestSuccess FHttpRequestHelper::OnRequestSuccessForSendResult;
FOnRequestFail FHttpRequestHelper::OnRequestFailForDump;
FOnRequestFail FHttpRequestHelper::OnRequestFailForSendResult;

// 创建并初始化一个 HTTP 请求对象
TSharedRef<IHttpRequest, ESPMode::ThreadSafe> FHttpRequestHelper::CreateRequest(const FString& URL, const FString& Verb)
{
	// 通过 HTTP 模块单例创建请求实例
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = FHttpModule::Get().CreateRequest();
	Request->SetURL(URL);	// 设置目标地址
	Request->SetVerb(Verb); // 设置请求方法 (GET/POST 等)
	// 记录请求日志, 便于排查
	UE_LOG(LogLQARestoreHttp, Log, TEXT("%s: %s"), *Verb, *URL);
	return Request;
}

// 统一的响应处理: 成功则触发成功委托, 否则记录警告并触发失败委托
void FHttpRequestHelper::HandleResponse(
	FHttpResponsePtr Response, bool bSuccess, FOnRequestSuccess& SuccessDelegate, FOnRequestFail& FailDelegate)
{
	// 连接成功且响应有效
	if (bSuccess && Response.IsValid())
	{
		if (SuccessDelegate.IsBound()) // 仅在委托已绑定时执行, 避免空调用
		{
			SuccessDelegate.Execute(Response);
		}
	}
	else
	{
		// 请求失败 (网络错误或响应无效)
		UE_LOG(LogLQARestoreHttp, Warning, TEXT("Request failed"));
		if (FailDelegate.IsBound())
		{
			FailDelegate.Execute();
		}
	}
}

// 发送 dump 文件数据到服务器
void FHttpRequestHelper::SendDumpFile(const FString& JsonData, const FString& ProjectId)
{
	// 拼接接口地址: {Host}/data/project/{ProjectId}/create
	const FString URL = HttpRequestConfig::Host + TEXT("/data/project/") + ProjectId + TEXT("/create");
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = CreateRequest(URL, TEXT("POST"));
	// 以表单编码方式提交
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/x-www-form-urlencoded"));
	Request->SetContentAsString(JsonData); // 设置请求体为 JSON 字符串
	// 绑定完成回调并发起异步请求
	Request->OnProcessRequestComplete().BindStatic(&FHttpRequestHelper::OnRequestResponseFinished);
	Request->ProcessRequest();
}

// 获取项目信息
void FHttpRequestHelper::GetProjectInfo(const FString& ProjectId)
{
	// 拼接接口地址, format=SDK 表示以 SDK 格式返回
	const FString URL = HttpRequestConfig::Host + TEXT("/project/project_info/") + ProjectId + TEXT("?format=SDK");
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = CreateRequest(URL, TEXT("GET"));
	Request->OnProcessRequestComplete().BindStatic(&FHttpRequestHelper::OnRequestResponseFinished);
	Request->ProcessRequest();
}

// 获取任务数据 (带查询参数拼接)
void FHttpRequestHelper::GetJobData(const FString& JobId, const FString& IsRegression, const FString& Language,
	const FString& Count, const FString& MinId, const FString& Modules)
{
	// 组织查询参数键值对
	TMap<FString, FString> Params = {{TEXT("job_id"), JobId}, {TEXT("regression"), IsRegression},
		{TEXT("language"), Language}, {TEXT("count"), Count}, {TEXT("minID"), MinId}};

	// 模块参数非空时, 将下划线分隔转换为逗号分隔后加入参数
	if (!Modules.IsEmpty())
	{
		Params.Add(TEXT("module_ids"), Modules.Replace(TEXT("_"), TEXT(","), ESearchCase::IgnoreCase));
	}

	// 遍历参数并进行 URL 编码, 拼接为 query string (以 & 连接)
	FString QueryString;
	for (const TPair<FString, FString>& Pair : Params)
	{
		if (!QueryString.IsEmpty())
			QueryString += TEXT("&");
		QueryString += FString::Printf(
			TEXT("%s=%s"), *FGenericPlatformHttp::UrlEncode(*Pair.Key), *FGenericPlatformHttp::UrlEncode(*Pair.Value));
	}

	// 拼接最终 URL
	const FString URL = HttpRequestConfig::Host + TEXT("/api/job/datas?") + QueryString;
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = CreateRequest(URL, TEXT("GET"));
	// 设置鉴权头
	Request->SetHeader(TEXT("LQA-Authorization"), HttpRequestConfig::Authorization);
	Request->OnProcessRequestComplete().BindStatic(&FHttpRequestHelper::OnGetJobDataRequestResponseFinished);
	Request->ProcessRequest();
}

// 发送还原结果 (使用 multipart/form-data 同时提交表单字段与文件)
void FHttpRequestHelper::SendRestoreResult(const FString& ProjectId, const FString& JobId, const FString& DataId,
	const FString& CheckInfoFilePath, const TArray<FString>& PngFilePaths, const FString& Language,
	const FString& Regression, const FString& CreateBug, const FString& BugId, const FString& AISign)
{
	const FString URL = HttpRequestConfig::Host + TEXT("/api/image/entity");
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = CreateRequest(URL, TEXT("POST"));
	Request->SetHeader(TEXT("LQA-Authorization"), HttpRequestConfig::Authorization);

	// 生成 multipart 分隔符 (使用 GUID 保证唯一性)
	const FString Boundary = TEXT("--") + FGuid::NewGuid().ToString();
	Request->SetHeader(TEXT("Content-Type"), TEXT("multipart/form-data; boundary=") + Boundary);

	// 请求体内容以字节数组形式手动拼装
	TArray<uint8> Content;
	const FString BoundaryPrefix = FString::Printf(TEXT("--%s\r\n"), *Boundary); // 每个分段的起始分隔行

	// 普通表单字段集合 (注意: rect_locations 为文件路径, 稍后作为文件内容读取)
	TMap<FString, FString> FormData = {{TEXT("project_id"), ProjectId}, {TEXT("job_id"), JobId},
		{TEXT("data_id"), DataId}, {TEXT("language"), Language}, {TEXT("rect_locations"), CheckInfoFilePath},
		{TEXT("regression"), Regression}, {TEXT("ai_sign"), AISign}, {TEXT("create_bug_tapd"), CreateBug}};

	// 逐个写入表单字段
	for (const TPair<FString, FString>& Pair : FormData)
	{
		// 写入分隔符
		Content.Append(reinterpret_cast<const uint8*>(TCHAR_TO_UTF8(*BoundaryPrefix)), BoundaryPrefix.Len());
		// 写入该字段的 Content-Disposition 头
		Content.Append(reinterpret_cast<const uint8*>(TCHAR_TO_UTF8(
						   *FString::Printf(TEXT("Content-Disposition: form-data; name=\"%s\"\r\n\r\n"), *Pair.Key))),
			FString::Printf(TEXT("Content-Disposition: form-data; name=\"%s\"\r\n\r\n"), *Pair.Key).Len());

		if (Pair.Key == TEXT("rect_locations"))
		{
			// rect_locations 特殊处理: 将其值当作文件路径, 读取文件内容写入请求体
			TArray<uint8> FileData;
			if (FFileHelper::LoadFileToArray(FileData, *Pair.Value))
			{
				Content.Append(FileData);
			}
		}
		else
		{
			// 普通字段: 直接写入字符串值 (UTF-8)
			Content.Append(reinterpret_cast<const uint8*>(TCHAR_TO_UTF8(*Pair.Value)), Pair.Value.Len());
		}
		// 字段结束换行
		Content.Append(reinterpret_cast<const uint8*>("\r\n"), 2);
	}

	// 逐个写入 PNG 图片文件
	for (const FString& FilePath : PngFilePaths)
	{
		if (FPaths::FileExists(FilePath)) // 仅处理存在的文件
		{
			// 文件名规则: {JobId}-{DataId}-{Language}.png
			const FString FileName = FString::Printf(TEXT("%s-%s-%s.png"), *JobId, *DataId, *Language);
			// 文件分段头, 字段名统一为 "files", 二进制流类型
			const FString FileHeader =
				FString::Printf(TEXT("Content-Disposition: form-data; name=\"files\"; filename=\"%s\"\r\nContent-Type: "
									 "application/octet-stream\r\n\r\n"),
					*FileName);

			TArray<uint8> FileData;
			if (FFileHelper::LoadFileToArray(FileData, *FilePath)) // 读取图片字节
			{
				Content.Append(reinterpret_cast<const uint8*>(TCHAR_TO_UTF8(*BoundaryPrefix)), BoundaryPrefix.Len());
				Content.Append(reinterpret_cast<const uint8*>(TCHAR_TO_UTF8(*FileHeader)), FileHeader.Len());
				Content.Append(FileData);							// 图片数据主体
				Content.Append(reinterpret_cast<const uint8*>("\r\n"), 2); // 分段结束换行
			}
		}
	}

	// 写入 multipart 结束分隔符 (--boundary--)
	Content.Append(reinterpret_cast<const uint8*>(TCHAR_TO_UTF8(*FString::Printf(TEXT("--%s--\r\n"), *Boundary))),
		FString::Printf(TEXT("--%s--\r\n"), *Boundary).Len());

	// 设置请求体并发起请求
	Request->SetContent(Content);
	Request->OnProcessRequestComplete().BindStatic(&FHttpRequestHelper::OnRequestResponseFinished);
	Request->ProcessRequest();
}

// 下载 dump 数据
void FHttpRequestHelper::GetDumpData(const FString& DataId, const FString& FilePath)
{
	// 下载基址使用独立的 FileHost (file_path 为域名根下绝对路径, 不含 API 网关前缀);
	// FileHost 为空时回退到 Host, 不再对端口做 :8080->:80 的硬替换
	const FString DownloadHost =
		HttpRequestConfig::FileHost.IsEmpty() ? HttpRequestConfig::Host : HttpRequestConfig::FileHost;

	const FString URL = DownloadHost + FilePath;
	TSharedRef<IHttpRequest, ESPMode::ThreadSafe> Request = CreateRequest(URL, TEXT("GET"));
	Request->SetHeader(TEXT("Content-Type"), TEXT("application/json"));

	// 若下载同样需要鉴权, 带上鉴权头 (media 为公开资源时服务端会忽略该头, 不影响)
	Request->SetHeader(TEXT("LQA-Authorization"), HttpRequestConfig::Authorization);

	// 构造用户数据, 携带 DataId 以便回调时识别对应数据
	TSharedPtr<FHttpRequestData> RequestData = MakeShared<FHttpRequestData>();
	RequestData->DataId = DataId;

	// 绑定携带用户数据的回调并发起请求
	Request->OnProcessRequestComplete().BindStatic(&FHttpRequestHelper::OnGetDataRequestResponseFinished, RequestData);
	Request->ProcessRequest();
}

// 任务数据请求完成回调 -> 分发到通用成功 / dump 失败委托
void FHttpRequestHelper::OnGetJobDataRequestResponseFinished(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully)
{
	HandleResponse(Response, bConnectedSuccessfully, OnRequestSuccess, OnRequestFailForDump);
}

// 通用请求完成回调 -> 分发到发送结果成功 / 失败委托
void FHttpRequestHelper::OnRequestResponseFinished(
	FHttpRequestPtr Request, FHttpResponsePtr Response, bool bConnectedSuccessfully)
{
	HandleResponse(Response, bConnectedSuccessfully, OnRequestSuccessForSendResult, OnRequestFailForSendResult);
}

// dump 数据下载完成回调 -> 分发到 dump 成功 / 失败委托
void FHttpRequestHelper::OnGetDataRequestResponseFinished(FHttpRequestPtr Request, FHttpResponsePtr Response,
	bool bConnectedSuccessfully, TSharedPtr<FHttpRequestData> UserData)
{
	HandleResponse(Response, bConnectedSuccessfully, OnRequestSuccessForDump, OnRequestFailForDump);
}

// 恢复编译器优化
LQA_ENABLE_OPTIMIZATION