#pragma once

#include "CoreMinimal.h"

/**
 * 数据转换工具类 (Data Converter Utils)
 *
 * 用于在「二进制数据」与「十六进制字符串」之间进行相互转换
 * 本类仅提供静态方法, 无需实例化即可调用, 常用于:
 *   - 将接口返回/文件读取到的十六进制文本还原为原始字节数据;
 *   - 将原始字节数据序列化为可读、可传输的十六进制字符串
 *
 * 说明: LQARESTORE_API 为模块导出宏, 保证该类可被其他模块引用
 */
class LQARESTORE_API FDataConverterUtils
{
public:
	/**
	 * 将十六进制字符串转换为二进制字节数组
	 *
	 * @param InData   输入的十六进制字符串 (例如 "48656C6C6F")
	 * @param OutData  输出参数, 用于接收转换后的二进制字节数组; 调用前会被清空
	 * @return         转换成功返回 true; 失败 (如字符串格式非法) 返回 false
	 */
	static bool GetBinaryDataFromString(const FString& InData, TArray<uint8>& OutData);

	/**
	 * 将二进制字节数组转换为十六进制字符串
	 *
	 * 每个字节会被格式化为两位大写十六进制字符（例如字节 0x0A -> "0A")
	 *
	 * @param InData  输入的二进制字节数组
	 * @param OutStr  输出参数, 用于接收转换后的十六进制字符串; 调用前会被清空
	 */
	static void TransBinaryDataToString(const TArray<uint8>& InData, FString& OutStr);
};