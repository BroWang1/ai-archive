#pragma once

#include "CoreMinimal.h"
#include "Engine/Texture2D.h"                        // UTexture2D 定义
#include "Json.h"                                     // JSON 解析相关类型 (FJsonObject 等)
#include "Materials/MaterialInstanceConstant.h"       // UMaterialInstanceConstant 定义
#include "PaperSprite.h"                              // UPaperSprite (2D 精灵) 定义
#include "Styling/SlateBrush.h"                       // FSlateBrush (Slate 画刷) 定义

// 前向声明, 避免在头文件中引入额外依赖
class UImage;                 // UMG 图片控件
class URestoreWindowProxy;    // 还原窗口代理 (持有纹理缓存等共享状态)

/**
 * LQA 纹理元数据, 包含 UV 坐标与尺寸信息
 * 注意：该结构体同时在 RestoreWindowUtils.h 中声明,
 *       后续建议抽取到一个公共头文件中统一管理, 避免重复声明
 */
struct FLQATextureMeta;

/**
 * 纹理资源管理工具类
 * 提供一组静态方法, 用于从 JSON 数据中加载、转换和管理纹理资源
 * 所有方法均为静态方法, 无需实例化即可调用
 */
class LQARESTORE_API FTextureUtils
{
public:
	/**
	 * 根据包含纹理数据的 JSON 对象, 更新图片控件 (UImage) 的画刷 (Brush)
	 * @param InImage            需要更新的目标图片控件
	 * @param InTextureDataRoot  包含纹理元数据的 JSON 对象
	 * @param RestoreWindowProxy 窗口代理, 用于访问纹理缓存
	 */
	static void UpdateImageBrushFromJsonObj(
		UImage* InImage, const TSharedPtr<FJsonObject>& InTextureDataRoot, URestoreWindowProxy* RestoreWindowProxy);

	/**
	 * 根据资源字符串设置图片画刷
	 * @param InImage        目标图片控件
	 * @param OutBrush       输出参数, 被填充的 Slate 画刷
	 * @param ResourceString 资源标识字符串 (格式: "Type'Path'")
	 * @param JsonObject     包含附加画刷数据的 JSON 对象
	 * @return 成功设置画刷返回 true, 否则返回 false
	 */
	static bool SetBrushFromResourceString(UImage* InImage, FSlateBrush& OutBrush, const FString& ResourceString,
		const TSharedPtr<FJsonObject>& JsonObject);

	/**
	 * 将资源字符串解析为「类型」和「路径」两部分
	 * @param ResourceString 输入资源字符串 (格式: "Type'Path'")
	 * @param OutType        输出参数, 资源类型 (如 "Texture2D"、"PaperSprite")
	 * @param OutPath        输出参数, 资源路径
	 * @return 解析成功返回 true, 否则返回 false
	 */
	static bool ParseResourceString(const FString& ResourceString, FString& OutType, FString& OutPath);

	/**
	 * 根据类型和路径加载 UObject 资源
	 * @param Type 资源类型 (如 "Texture2D"、"PaperSprite"、"MaterialInstanceConstant")
	 * @param Path 资源的资产路径
	 * @return 加载成功返回资源对象, 失败返回 nullptr
	 */
	static UObject* LoadResourceByType(const FString& Type, const FString& Path);

	/**
	 * 从 JSON 对象中获取纹理 (UTexture2D)
	 * @param InTextureDataRoot  包含纹理数据的 JSON 对象
	 * @param RestoreWindowProxy 窗口代理, 用于访问纹理缓存
	 * @return 加载成功返回纹理, 失败返回 nullptr
	 */
	static UTexture2D* GetTextureFromJsonObj(
		const TSharedPtr<FJsonObject>& InTextureDataRoot, URestoreWindowProxy* RestoreWindowProxy);

	/**
	 * 获取 Texture2D 的原始数据, 并以 PNG 二进制格式输出
	 * @param Texture2D 源纹理
	 * @param OutData   输出参数, PNG 格式的二进制数据
	 * @return 数据提取成功返回 true, 否则返回 false
	 */
	static bool GetTexture2DData(UTexture2D* Texture2D, TArray<uint8>& OutData);

	/**
	 * 从 JSON 对象中获取纹理元数据
	 * @param TextureDataObj 包含纹理数据的 JSON 对象
	 * @return 纹理元数据结构体
	 */
	static FLQATextureMeta GetTextureMeta(const TSharedPtr<FJsonObject>& TextureDataObj);

private:
	/**
	 * 材质画刷缓存, 用于避免对同一材质实例重复创建画刷
	 * 键为材质实例指针, 值为对应的 Slate 画刷
	 */
	static TMap<UMaterialInstanceConstant*, FSlateBrush> MaterialBrushCache;

	/**
	 * 将资源类型字符串归一化为短名
	 * dump 端可能写出全限定名 (如 "/Script/Engine.Texture2D"), 需归一化为 "Texture2D" 才能参与类型判定
	 * @param InType 原始类型字符串
	 * @return 归一化后的短类型名
	 */
	static FString NormalizeAssetType(const FString& InType);

	/**
	 * 从 dump session 目录的 Textures/<NameMD5>.png 还原运行时生成的纹理
	 * 用于兜底那些因不存在于磁盘而无法按路径加载的资源 (如 /Engine/Transient.Texture2D_x)
	 * 解析结果会缓存在 RestoreWindowProxy 的 SharedTextureMap 中, 避免重复解码
	 * @param RestoreWindowProxy 窗口代理, 持有纹理缓存 (同时确保 UObject 不被 GC 回收)
	 * @param SnapshotDirectory  dump session 目录
	 * @param NameMD5            纹理名称的 MD5, 即 PNG 文件名 (不含扩展名)
	 * @return 还原成功返回纹理, 失败返回 nullptr
	 */
	static UTexture2D* LoadRuntimeTextureFromSnapshot(
		URestoreWindowProxy* RestoreWindowProxy, const FString& SnapshotDirectory, const FString& NameMD5);
};