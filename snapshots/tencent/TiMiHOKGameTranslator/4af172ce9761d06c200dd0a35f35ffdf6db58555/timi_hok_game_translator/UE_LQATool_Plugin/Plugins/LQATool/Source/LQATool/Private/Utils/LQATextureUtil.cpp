#include "Utils/LQATextureUtil.h"

#include "Engine/Texture.h"                        // UTexture 基类
#include "Engine/Texture2D.h"
#include "Engine/TextureCube.h"                    // 立方体贴图
#include "Engine/TextureRenderTarget2D.h"          // 渲染目标纹理
#include "ImageUtils.h"
#include "Materials/MaterialInstanceConstant.h"    // 常量材质实例
#include "Materials/MaterialInstanceDynamic.h"     // 动态材质实例
#include "PaperSprite.h"                           // Paper2D 精灵
#include "Utils/LQAJsonUtils.h"                    // LQA 自定义 JSON 工具
#include "LQABase.h"                               // 日志分类 LogLQATool 声明

// ============ JSON 字段名常量定义 (与头文件声明一一对应) ============
const FString FLQATextureUtil::JsonFields::NAME = TEXT("name");
const FString FLQATextureUtil::JsonFields::NAME_MD5 = TEXT("nameMD5");
const FString FLQATextureUtil::JsonFields::TYPE = TEXT("type");
const FString FLQATextureUtil::JsonFields::SPRITE_NAME = TEXT("spritename");
const FString FLQATextureUtil::JsonFields::SPRITE_NAME_MD5 = TEXT("spritenameMD5");
const FString FLQATextureUtil::JsonFields::MATERIAL_PATH = TEXT("MaterialPath");
const FString FLQATextureUtil::JsonFields::SCALAR_PARAMS = TEXT("ScalarParameters");
const FString FLQATextureUtil::JsonFields::VECTOR_PARAMS = TEXT("VectorParameters");
const FString FLQATextureUtil::JsonFields::TEXTURE_PARAMS = TEXT("TextureParameters");

// 颜色分量字段名常量定义
const FString FLQATextureUtil::JsonFields::ColorFields::R = TEXT("R");
const FString FLQATextureUtil::JsonFields::ColorFields::G = TEXT("G");
const FString FLQATextureUtil::JsonFields::ColorFields::B = TEXT("B");
const FString FLQATextureUtil::JsonFields::ColorFields::A = TEXT("A");

// 纹理类型名称常量定义
const FString FLQATextureUtil::TextureTypes::PAPER_SPRITE = TEXT("PaperSprite");
const FString FLQATextureUtil::TextureTypes::TEXTURE_2D = TEXT("Texture2D");
const FString FLQATextureUtil::TextureTypes::TEXTURE_CUBE = TEXT("TextureCube");

// =================== JSON 转换工具 ===================

// 将线性颜色 (FLinearColor) 转换为含 R/G/B/A 四个数值字段的 JSON 对象
TSharedPtr<FJsonObject> FLQATextureUtil::LinearColorToJson(const FLinearColor& Color)
{
	TSharedPtr<FJsonObject> JsonColor = MakeShared<FJsonObject>();
	JsonColor->SetNumberField(JsonFields::ColorFields::R, Color.R);  // 写入红色分量
	JsonColor->SetNumberField(JsonFields::ColorFields::G, Color.G);  // 写入绿色分量
	JsonColor->SetNumberField(JsonFields::ColorFields::B, Color.B);  // 写入蓝色分量
	JsonColor->SetNumberField(JsonFields::ColorFields::A, Color.A);  // 写入透明度分量
	return JsonColor;
}

// 写入纹理的公共元数据: 全名、类型、全名的 MD5, 并缓存到共享纹理表
void FLQATextureUtil::WriteTextureMetadata(UTexture* Texture, const TSharedPtr<FJsonObject>& JsonRoot,
	const FString& TextureType, TMap<FString, UTexture*>& SharedTextureMap)
{
	// 入参校验: 纹理或 JSON 根对象无效则直接返回
	if (!Texture || !JsonRoot.IsValid())
	{
		return;
	}

	// 获取纹理全名 (包含类型前缀与完整路径)
	const FString TextureName = Texture->GetFullName();
	JsonRoot->SetStringField(JsonFields::NAME, TextureName);   // 写入名称
	JsonRoot->SetStringField(JsonFields::TYPE, TextureType);   // 写入类型

	// 计算名称的 MD5, 便于在导出数据中做唯一标识/校验
	const FString NameMD5 = FMD5::HashAnsiString(*TextureName);
	JsonRoot->SetStringField(JsonFields::NAME_MD5, NameMD5);

	// 将纹理加入共享缓存, 供外部复用 (避免重复处理同一纹理)
	SharedTextureMap.Add(TextureName, Texture);
}

// 写入 Sprite 专有数据: Sprite 名称及其 MD5
void FLQATextureUtil::WriteSpriteData(const TSharedPtr<FJsonObject>& JsonRoot, const FString& SpriteName)
{
	// 入参校验: JSON 根对象无效则直接返回
	if (!JsonRoot.IsValid())
	{
		return;
	}

	JsonRoot->SetStringField(JsonFields::SPRITE_NAME, SpriteName);  // 写入 Sprite 名称

	// 计算 Sprite 名称的 MD5 并写入
	const FString SpriteNameMD5 = FMD5::HashAnsiString(*SpriteName);
	JsonRoot->SetStringField(JsonFields::SPRITE_NAME_MD5, SpriteNameMD5);
}

bool FLQATextureUtil::GetTexture2DData(UTexture2D* Texture2D, TArray<uint8>& OutData)
{
	OutData.Reset();

	// Missing texture, or no mip data available to read from
	if (!Texture2D)
	{
		return false;
	}

	// UE 5.0+ made PlatformData private, must go through GetPlatformData()
#if ENGINE_MAJOR_VERSION >= 5
	FTexturePlatformData* PlatformData = Texture2D->GetPlatformData();
#else
	FTexturePlatformData* PlatformData = Texture2D->PlatformData;
#endif
	if (!PlatformData || PlatformData->Mips.Num() == 0)
	{
		return false;
	}

	const int32 Width = Texture2D->GetSizeX();
	const int32 Height = Texture2D->GetSizeY();
	if (Width <= 0 || Height <= 0)
	{
		return false;
	}

	// Back up compression/sRGB settings so they can be restored after reading
	const TextureCompressionSettings OldCompressionSettings = Texture2D->CompressionSettings;
	const bool OldSRGB = Texture2D->SRGB;
	// Disable compression and sRGB to get untouched raw pixels
	Texture2D->CompressionSettings = TextureCompressionSettings::TC_VectorDisplacementmap;
	Texture2D->SRGB = false;
	Texture2D->UpdateResource();

	const int64 PixelCount = static_cast<int64>(Width) * Height;
	TArray<FColor> Colors;
	Colors.SetNumUninitialized(static_cast<int32>(PixelCount));

	// Read mip 0 pixels
	FTexture2DMipMap& TextureMip = PlatformData->Mips[0];
	void* TextureData = TextureMip.BulkData.Lock(LOCK_READ_WRITE);
	if (TextureData)
	{
		FMemory::Memcpy(Colors.GetData(), TextureData, static_cast<SIZE_T>(PixelCount * sizeof(FColor)));
	}
	TextureMip.BulkData.Unlock();

	// Restore original settings
	Texture2D->CompressionSettings = OldCompressionSettings;
	Texture2D->SRGB = OldSRGB;
	Texture2D->UpdateResource();

	if (!TextureData)
	{
		return false;
	}

	// Compress raw pixels to PNG
	// UE 5.1+ deprecated CompressImageArray in favour of PNGCompressImageArray (requires TArray64<uint8>)
#if ENGINE_MAJOR_VERSION >= 5
	TArray64<uint8> PngData;
	FImageUtils::PNGCompressImageArray(Width, Height, Colors, PngData);
	if (PngData.Num() == 0)
	{
		return false;
	}
	OutData.Append(PngData.GetData(), static_cast<int32>(PngData.Num()));
#else
	FImageUtils::CompressImageArray(Width, Height, Colors, OutData);
#endif

	return OutData.Num() > 0;
}

// =================== 材质处理函数 ===================

// 提取材质实例的标量、向量、纹理三类参数, 整合为一个 JSON 对象
TSharedPtr<FJsonObject> FLQATextureUtil::ExtractMaterialParametersToJsonObject(UMaterialInstance* MaterialInstance)
{
	// 入参校验: 材质实例为空则记录警告并返回 nullptr
	if (!MaterialInstance)
	{
		UE_LOG(LogLQATool, Warning,
			TEXT("FLQATextureUtil::ExtractMaterialParametersToJsonObject - MaterialInstance is null"));
		return nullptr;
	}

	TSharedPtr<FJsonObject> RootObject = MakeShared<FJsonObject>();

	// --- 提取标量参数 ---
	TSharedPtr<FJsonObject> ScalarParamsObject = MakeShared<FJsonObject>();
	TArray<FMaterialParameterInfo> ScalarInfos;  // 标量参数信息列表
	TArray<FGuid> ScalarGuids;                    // 对应的 GUID 列表 (此处未使用)
	MaterialInstance->GetAllScalarParameterInfo(ScalarInfos, ScalarGuids);

	// 遍历每个标量参数, 取值后写入 JSON (参数名 -> 值)
	for (const auto& Info : ScalarInfos)
	{
		float Value;
		if (MaterialInstance->GetScalarParameterValue(Info, Value))
		{
			ScalarParamsObject->SetNumberField(Info.Name.ToString(), Value);
		}
	}
	RootObject->SetObjectField(JsonFields::SCALAR_PARAMS, ScalarParamsObject);

	// --- 提取向量参数 ---
	TSharedPtr<FJsonObject> VectorParamsObject = MakeShared<FJsonObject>();
	TArray<FMaterialParameterInfo> VectorInfos;
	TArray<FGuid> VectorGuids;
	MaterialInstance->GetAllVectorParameterInfo(VectorInfos, VectorGuids);

	// 遍历每个向量参数, 取 FLinearColor 后转为 JSON 子对象写入
	for (const auto& Info : VectorInfos)
	{
		FLinearColor Value;
		if (MaterialInstance->GetVectorParameterValue(Info, Value))
		{
			VectorParamsObject->SetObjectField(Info.Name.ToString(), LinearColorToJson(Value));
		}
	}
	RootObject->SetObjectField(JsonFields::VECTOR_PARAMS, VectorParamsObject);

	// --- 提取纹理参数 ---
	TSharedPtr<FJsonObject> TextureParamsObject = MakeShared<FJsonObject>();
	TArray<FMaterialParameterInfo> TextureInfos;
	TArray<FGuid> TextureGuids;
	MaterialInstance->GetAllTextureParameterInfo(TextureInfos, TextureGuids);

	// 遍历每个纹理参数, 取纹理资源路径后写入 (参数名 -> 路径)
	for (const auto& Info : TextureInfos)
	{
		UTexture* Texture = nullptr;
		if (MaterialInstance->GetTextureParameterValue(Info, Texture) && Texture)
		{
			const FString Path = Texture->GetPathName();
			TextureParamsObject->SetStringField(Info.Name.ToString(), Path);
		}
	}
	RootObject->SetObjectField(JsonFields::TEXTURE_PARAMS, TextureParamsObject);

	return RootObject;
}

// 处理材质实例: 在参数 JSON 基础上, 追加基础 (父) 材质的路径
TSharedPtr<FJsonObject> FLQATextureUtil::HandleMaterialInstance(UMaterialInstance* MaterialInstance)
{
	// 先提取参数; 若失败则直接返回 nullptr
	TSharedPtr<FJsonObject> ResultObject = ExtractMaterialParametersToJsonObject(MaterialInstance);
	if (!ResultObject.IsValid())
	{
		return nullptr;
	}

	// 获取基础材质 (材质实例最终继承的母材质)
	UMaterialInterface* BaseMaterialInterface = MaterialInstance->GetBaseMaterial();
	if (BaseMaterialInterface)
	{
		const FString MaterialPath = BaseMaterialInterface->GetPathName();
		ResultObject->SetStringField(JsonFields::MATERIAL_PATH, MaterialPath);  // 写入基础材质路径
	}
	else
	{
		// 未找到基础材质时记录警告 (不影响已提取的参数)
		UE_LOG(LogLQATool, Warning,
			TEXT("FLQATextureUtil::HandleMaterialInstance - BaseMaterialInterface not found for %s"),
			*MaterialInstance->GetName());
	}

	return ResultObject;
}

// =================== 纹理处理函数 (按相似逻辑分组) ===================

// 处理 Paper 精灵: 使用其烘焙纹理写入元数据, 再补充 Sprite 专有数据
TSharedPtr<FJsonObject> FLQATextureUtil::HandlePaperSprite(
	UPaperSprite* Sprite, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!Sprite)
	{
		return nullptr;
	}

	TSharedPtr<FJsonObject> JsonObject = MakeShared<FJsonObject>();
	UTexture* BakedTexture = Sprite->GetBakedTexture();  // 获取精灵烘焙后的纹理

	// 以 PaperSprite 类型写入纹理公共元数据
	WriteTextureMetadata(BakedTexture, JsonObject, TextureTypes::PAPER_SPRITE, SharedTextureMap);

	// 追加 Sprite 专有数据 (名称及其 MD5)
	WriteSpriteData(JsonObject, Sprite->GetName());

	return JsonObject;
}

// 处理标准纹理 (Texture2D / RenderTarget2D): 写入纹理公共元数据
TSharedPtr<FJsonObject> FLQATextureUtil::HandleStandardTexture(
	UTexture* Texture, TMap<FString, UTexture*>& SharedTextureMap)
{
	if (!Texture)
	{
		return nullptr;
	}

	TSharedPtr<FJsonObject> JsonObject = MakeShared<FJsonObject>();
	WriteTextureMetadata(Texture, JsonObject, TextureTypes::TEXTURE_2D, SharedTextureMap);
	return JsonObject;
}

// 处理立方体贴图: 写入纹理公共元数据
TSharedPtr<FJsonObject> FLQATextureUtil::HandleTextureCube(UTextureCube* TextureCube)
{
	if (!TextureCube)
	{
		return nullptr;
	}

	TSharedPtr<FJsonObject> JsonObject = MakeShared<FJsonObject>();

	// 立方体贴图不参与共享纹理缓存, 这里传入一个临时的空 Map 占位
	TMap<FString, UTexture*> DummyMap;
	WriteTextureMetadata(TextureCube, JsonObject, TextureTypes::TEXTURE_CUBE, DummyMap);

	return JsonObject;
}

// =================== 主入口 ===================

// 根据传入对象的实际类型, 分发到对应的处理函数, 返回其 JSON 表示
TSharedPtr<FJsonObject> FLQATextureUtil::GetTextureJsonObj(
	UObject* TextureObject, TMap<FString, UTexture*>& SharedTextureMap)
{
	// 入参校验: 对象为空则记录警告并返回空 JSON 对象
	if (!TextureObject)
	{
		UE_LOG(LogLQATool, Warning, TEXT("FLQATextureUtil::GetTextureJsonObj - TextureObject is null"));
		return MakeShared<FJsonObject>();
	}

	// 处理材质实例 (动态与常量实例均继承自 UMaterialInstance, 逻辑一致)
	if (UMaterialInstance* MaterialInstance = Cast<UMaterialInstance>(TextureObject))
	{
		return HandleMaterialInstance(MaterialInstance);
	}

	// 处理 Paper 精灵
	if (UPaperSprite* Sprite = Cast<UPaperSprite>(TextureObject))
	{
		return HandlePaperSprite(Sprite, SharedTextureMap);
	}

	// 处理标准纹理 (Texture2D 与 TextureRenderTarget2D 使用相同逻辑)
	if (UTexture2D* Texture2D = Cast<UTexture2D>(TextureObject))
	{
		return HandleStandardTexture(Texture2D, SharedTextureMap);
	}

	if (UTextureRenderTarget2D* TextureRT = Cast<UTextureRenderTarget2D>(TextureObject))
	{
		return HandleStandardTexture(TextureRT, SharedTextureMap);
	}

	// 处理立方体贴图
	if (UTextureCube* TextureCube = Cast<UTextureCube>(TextureObject))
	{
		return HandleTextureCube(TextureCube);
	}

	// 未知纹理类型: 记录错误并返回空 JSON 对象
	UE_LOG(LogLQATool, Error, TEXT("FLQATextureUtil::GetTextureJsonObj - Unknown texture type: %s"),
		*TextureObject->GetClass()->GetName());

	return MakeShared<FJsonObject>();
}