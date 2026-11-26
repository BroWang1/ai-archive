#pragma once

#include "CoreMinimal.h"
#include "Json.h"                  // UE 的 JSON 核心库, 提供 FJsonObject 等类型
#include "JsonObjectConverter.h"   // 结构体与 JSON 之间互转的工具
#include "Math/Vector2D.h"         // 二维向量 FVector2D

#include "LQATextureUtil.generated.h"  // UE 反射系统生成的代码 (必须放在最后一个 include)

// 前向声明: 仅声明指针/引用用到的类型, 减少头文件依赖、加快编译
class UTexture;
class UMaterialInstance;
class UMaterialInstanceDynamic;
class UMaterialInstanceConstant;
class UPaperSprite;
class UTexture2D;
class UTextureRenderTarget2D;
class UTextureCube;

/**
 * 纹理元数据结构 (内部使用，未暴露给蓝图)
 * 记录纹理在图集/序列中的索引、UV 坐标与尺寸
 */
struct FLQATextureMeta
{
	int32 Index;        // 纹理索引
	FVector2D UV;       // 纹理的 UV 坐标
	FVector2D Size;     // 纹理尺寸 (宽、高)
};

/**
 * 材质参数数据结构, 可在蓝图中使用 (BlueprintType)
 * 用于聚合材质实例中的三类参数, 便于序列化
 */
USTRUCT(BlueprintType)
struct FMaterialParameterData
{
	GENERATED_BODY()

	// 标量参数: 参数名 -> 浮点值
	UPROPERTY()
	TMap<FString, float> ScalarParameters;

	// 向量参数: 参数名 -> 线性颜色 (RGBA)
	UPROPERTY()
	TMap<FString, FLinearColor> VectorParameters;

	// 纹理参数: 参数名 -> 纹理资源路径
	UPROPERTY()
	TMap<FString, FString> TextureParameters;
};

/**
 * 纹理与材质数据提取工具类
 * 负责把 UE 的纹理 / 材质对象转换为 JSON 表示, 供 LQA 工具导出使用
 * 全部为静态方法, 无需实例化
 */
class FLQATextureUtil
{
public:
	/**
	 * 提取材质实例的全部参数并转换为 JSON 对象
	 * @param MaterialInstance 要提取参数的材质实例
	 * @return 包含材质参数的 JSON 对象; 若入参无效则返回 nullptr
	 */
	static TSharedPtr<FJsonObject> ExtractMaterialParametersToJsonObject(UMaterialInstance* MaterialInstance);

	/**
	 * 将纹理对象转换为 JSON 表示 (对外主入口)
	 * 内部会根据对象实际类型分发到对应的处理函数
	 * @param TextureObject   要转换的纹理/材质对象
	 * @param SharedTextureMap 共享纹理缓存 (避免重复处理同一纹理)
	 * @return 表示该纹理的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> GetTextureJsonObj(
		UObject* TextureObject, TMap<FString, UTexture*>& SharedTextureMap);

	/**
	 * Read a Texture2D's pixels and compress them to PNG bytes.
	 * Used to persist runtime-generated textures (e.g. /Engine/Transient ones) that have no asset on disk.
	 * @param Texture2D Texture to read
	 * @param OutData Compressed PNG bytes
	 * @return true if PNG data was produced
	 */
	static bool GetTexture2DData(UTexture2D* Texture2D, TArray<uint8>& OutData);

private:
	// JSON 字段名常量, 使用 “命名空间式” 的嵌套结构体来组织, 避免魔法字符串散落各处
	struct JsonFields
	{
		static const FString NAME;             // 纹理名称字段
		static const FString NAME_MD5;         // 纹理名称的 MD5 值字段
		static const FString TYPE;             // 纹理类型字段
		static const FString SPRITE_NAME;      // Sprite 名称字段
		static const FString SPRITE_NAME_MD5;  // Sprite 名称的 MD5 值字段
		static const FString MATERIAL_PATH;    // 基础材质路径字段
		static const FString SCALAR_PARAMS;    // 标量参数集合字段
		static const FString VECTOR_PARAMS;    // 向量参数集合字段
		static const FString TEXTURE_PARAMS;   // 纹理参数集合字段

		// 颜色分量字段名 (R/G/B/A)
		struct ColorFields
		{
			static const FString R;  // 红色分量
			static const FString G;  // 绿色分量
			static const FString B;  // 蓝色分量
			static const FString A;  // 透明度分量
		};
	};

	// 纹理类型名称常量
	struct TextureTypes
	{
		static const FString PAPER_SPRITE;  // Paper2D 精灵类型
		static const FString TEXTURE_2D;    // 2D 纹理类型
		static const FString TEXTURE_CUBE;  // 立方体贴图类型
	};

	// 以下为按功能分组的核心工具函数

	// === JSON 转换工具 ===
	/**
	 * 将线性颜色转换为 JSON 对象
	 * @param Color 要转换的颜色
	 * @return 表示该颜色的 JSON 对象 (含 R/G/B/A 字段)
	 */
	static TSharedPtr<FJsonObject> LinearColorToJson(const FLinearColor& Color);

	/**
	 * 写入纹理的公共元数据 (名称、类型、名称 MD5) 到 JSON
	 * @param Texture          要提取数据的纹理
	 * @param JsonRoot         写入目标 JSON 对象
	 * @param TextureType      纹理类型字符串
	 * @param SharedTextureMap 共享纹理缓存
	 */
	static void WriteTextureMetadata(UTexture* Texture, const TSharedPtr<FJsonObject>& JsonRoot,
		const FString& TextureType, TMap<FString, UTexture*>& SharedTextureMap);

	/**
	 * 写入 Sprite 专有数据 (Sprite 名称及其 MD5) 到 JSON
	 * @param JsonRoot   写入目标 JSON 对象
	 * @param SpriteName Sprite 名称
	 */
	static void WriteSpriteData(const TSharedPtr<FJsonObject>& JsonRoot, const FString& SpriteName);

	// === 材质处理函数 ===
	/**
	 * 处理材质实例并转换为 JSON (在参数基础上追加基础材质路径)
	 * @param MaterialInstance 要转换的材质实例
	 * @return 表示该材质的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> HandleMaterialInstance(UMaterialInstance* MaterialInstance);

	// === 纹理处理函数 (按相似逻辑分组) ===
	/**
	 * 处理 Paper 精灵并转换为 JSON
	 * @param Sprite           要转换的精灵
	 * @param SharedTextureMap 共享纹理缓存
	 * @return 表示该精灵的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> HandlePaperSprite(UPaperSprite* Sprite, TMap<FString, UTexture*>& SharedTextureMap);

	/**
	 * 处理标准纹理 (Texture2D / RenderTarget2D) 并转换为 JSON
	 * @param Texture          要转换的纹理
	 * @param SharedTextureMap 共享纹理缓存
	 * @return 表示该纹理的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> HandleStandardTexture(UTexture* Texture, TMap<FString, UTexture*>& SharedTextureMap);

	/**
	 * 处理立方体贴图并转换为 JSON
	 * @param TextureCube 要转换的立方体贴图
	 * @return 表示该立方体贴图的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> HandleTextureCube(UTextureCube* TextureCube);
};