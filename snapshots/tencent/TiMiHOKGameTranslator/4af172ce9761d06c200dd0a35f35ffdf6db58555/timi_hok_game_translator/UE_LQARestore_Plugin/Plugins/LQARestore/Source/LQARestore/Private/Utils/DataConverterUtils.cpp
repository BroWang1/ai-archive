#include "Utils/DataConverterUtils.h"

// 将十六进制字符串转换为二进制字节数组
bool FDataConverterUtils::GetBinaryDataFromString(const FString& InData, TArray<uint8>& OutData)
{
	// 先清空输出数组, 避免残留上一次调用的数据
	OutData.Empty();

	// 获取输入字符串长度, 作为缓冲区的预分配大小
	const uint32 Size = InData.Len();

	// 创建临时缓冲区并预分配空间 (SetNumUninitialized 不初始化内存, 性能更高)
	TArray<uint8> Buffer;
	Buffer.SetNumUninitialized(Size);

	// 调用引擎自带的 ToHexBlob 将十六进制字符串解析为字节写入 Buffer
	// 解析成功返回 true, 失败 (格式非法等) 返回 false
	if (FString::ToHexBlob(InData, Buffer.GetData(), Size))
	{
		// 使用 MoveTemp 进行移动语义赋值, 避免数组内存的额外拷贝
		OutData = MoveTemp(Buffer);
		return true;
	}

	// 解析失败, 返回 false, OutData 保持为空
	return false;
}

// 将二进制字节数组转换为十六进制字符串
void FDataConverterUtils::TransBinaryDataToString(const TArray<uint8>& InData, FString& OutStr)
{
	// 先清空输出字符串, 避免残留上一次调用的数据
	OutStr.Empty();

	// 预分配容量: 每个字节对应两个十六进制字符, 提前 Reserve 可减少动态扩容次数
	OutStr.Reserve(InData.Num() * 2);

	// 逐字节遍历, 将每个字节格式化为两位大写十六进制 (不足两位前面补 0) 并追加到结果字符串
	for (const uint8 Byte : InData)
	{
		OutStr += FString::Printf(TEXT("%02X"), Byte);
	}
}