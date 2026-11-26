#include "Utils/TextureUtils.h"

#include "LQABase.h"                              // 日志分类 LogLQARestore 等基础定义

#include "Components/Image.h"                     // UImage 图片控件
#include "Core/RestoreWindowProxy.h"              // URestoreWindowProxy, 含纹理缓存 SharedTextureMap
#include "IImageWrapper.h"                        // IImageWrapper, PNG 解码
#include "IImageWrapperModule.h"                  // IImageWrapperModule, 获取 PNG 解码器
#include "ImageUtils.h"                           // FImageUtils, 用于 PNG 压缩
#include "Materials/MaterialInstanceDynamic.h"    // UMaterialInstanceDynamic (动态材质实例)
#include "Materials/MaterialInterface.h"          // UMaterialInterface (材质接口基类)
#include "Misc/FileHelper.h"                      // FFileHelper (读取导出的 PNG)
#include "Modules/ModuleManager.h"                // FModuleManager (获取 ImageWrapper 模块)
#include "Utils/JsonUtils.h"                      // 自定义 JSON 反序列化工具
#include "Utils/SlateBrushUtils.h"                // 自定义 Slate 画刷构建工具

// 初始化静态成员变量 (材质画刷缓存)
TMap<UMaterialInstanceConstant*, FSlateBrush> FTextureUtils::MaterialBrushCache;

// 辅助函数: 将 JSON 对象转换为线性颜色 (FLinearColor)
static bool JsonObjectToLinearColor(const TSharedPtr<FJsonObject>& JsonColor, FLinearColor& OutColor)
{
	// JSON 对象无效直接返回失败
	if (!JsonColor.IsValid())
		return false;

	double R = 0.0, G = 0.0, B = 0.0, A = 0.0;
	// 依次尝试读取 R/G/B/A 四个颜色通道字段, 全部成功才构造颜色
	if (JsonColor->TryGetNumberField(TEXT("R"), R) && JsonColor->TryGetNumberField(TEXT("G"), G) &&
		JsonColor->TryGetNumberField(TEXT("B"), B) && JsonColor->TryGetNumberField(TEXT("A"), A))
	{
		// JSON 中数值为 double, 需显式转换为 float
		OutColor =
			FLinearColor(static_cast<float>(R), static_cast<float>(G), static_cast<float>(B), static_cast<float>(A));
		return true;
	}
	return false;
}

// 辅助函数: 根据资源路径加载纹理 (UTexture)
static UTexture* LoadTextureFromPath(const FString& Path)
{
	// 路径为空直接返回空指针
	if (Path.IsEmpty())
		return nullptr;
	// 同步加载纹理对象并转换为 UTexture 类型
	return Cast<UTexture>(StaticLoadObject(UTexture::StaticClass(), nullptr, *Path));
}

// 辅助函数: 从 JSON 中读取并应用材质参数 (标量/向量/纹理)
static void ApplyMaterialParametersFromJson(UMaterialInstance* MI, const TSharedPtr<FJsonObject>& JsonObject)
{
	// 材质实例或 JSON 对象无效时记录错误并返回
	if (!MI || !JsonObject.IsValid())
	{
		UE_LOG(LogLQARestore, Error, TEXT("Invalid material instance or JSON object"));
		return;
	}

	// 只有动态材质实例 (MID) 才支持运行时设置参数
	UMaterialInstanceDynamic* MID = Cast<UMaterialInstanceDynamic>(MI);
	if (!MID)
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Material instance is not dynamic, cannot set parameters"));
		return;
	}

	// —— 处理标量参数 (ScalarParameters) ——
	const TSharedPtr<FJsonObject>* ScalarParamsObj = nullptr;
	if (JsonObject->TryGetObjectField(TEXT("ScalarParameters"), ScalarParamsObj))
	{
		// 遍历每一个标量参数键值对
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*ScalarParamsObj)->Values)
		{
			const FString& ParamName = Pair.Key;
			double Value = 0.0;
			// 成功读取数值后设置到材质
			if (Pair.Value->TryGetNumber(Value))
			{
				MID->SetScalarParameterValue(FName(*ParamName), static_cast<float>(Value));
			}
		}
	}

	// —— 处理向量参数 (VectorParameters, 通常为颜色) ——
	const TSharedPtr<FJsonObject>* VectorParamsObj = nullptr;
	if (JsonObject->TryGetObjectField(TEXT("VectorParameters"), VectorParamsObj))
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*VectorParamsObj)->Values)
		{
			const FString& ParamName = Pair.Key;
			const TSharedPtr<FJsonObject>* ColorObj = nullptr;
			// 向量参数本身是一个 JSON 对象 (含 RGBA)
			if (Pair.Value->TryGetObject(ColorObj))
			{
				FLinearColor Color;
				// 转换为线性颜色后设置到材质
				if (JsonObjectToLinearColor(*ColorObj, Color))
				{
					MID->SetVectorParameterValue(FName(*ParamName), Color);
				}
			}
		}
	}

	// —— 处理纹理参数 (TextureParameters) ——
	const TSharedPtr<FJsonObject>* TextureParamsObj = nullptr;
	if (JsonObject->TryGetObjectField(TEXT("TextureParameters"), TextureParamsObj))
	{
		for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : (*TextureParamsObj)->Values)
		{
			const FString& ParamName = Pair.Key;
			FString TexturePath;
			// 纹理参数的值是纹理资源路径字符串
			if (Pair.Value->TryGetString(TexturePath))
			{
				UTexture* Tex = LoadTextureFromPath(TexturePath);
				if (Tex)
				{
					MID->SetTextureParameterValue(FName(*ParamName), Tex);
				}
				else
				{
					UE_LOG(LogLQARestore, Warning, TEXT("Failed to load texture: %s"), *TexturePath);
				}
			}
		}
	}
}

// 根据 JSON 对象更新图片控件画刷: 支持动态材质、Texture2D、PaperSprite、常量材质实例
void FTextureUtils::UpdateImageBrushFromJsonObj(
	UImage* InImage, const TSharedPtr<FJsonObject>& InTextureDataRoot, URestoreWindowProxy* RestoreWindowProxy)
{
	// 图片控件为空直接返回
	if (!InImage)
	{
		return;
	}

	// 获取当前画刷: UE5 与 UE4 的接口不同, 这里做版本兼容处理
#if ENGINE_MAJOR_VERSION >= 5
	FSlateBrush CurrentBrush = InImage->GetBrush();
#else
	FSlateBrush CurrentBrush = InImage->Brush;
#endif
	// 从 JSON 中读取资源对象字符串 (格式: "Type'Path'")
	FString ResourceString = InTextureDataRoot->GetStringField(TEXT("resourceObject"));

	// 取出当前画刷已绑定的资源对象
	UObject* Resource = CurrentBrush.GetResourceObject();

	// 若资源已经加载且有效, 则无需重复加载直接返回
	// UE 5.0+ 已移除 UObject::IsPendingKill(), 统一使用全局 ::IsValid() (UE4 下也可用)
	if (IsValid(Resource) && !Resource->HasAnyFlags(RF_NeedLoad))
	{
		UE_LOG(LogLQARestore, Log, TEXT("Resource already loaded and valid"));
		return;
	}

	// 解析资源字符串, 拆分出类型与路径
	FString Type, Path;
	UE_LOG(LogLQARestore, Warning, TEXT("ResourceString: %s"), *ResourceString);
	if (!ParseResourceString(ResourceString, Type, Path))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("ParseResourceString failed for %s"), *ResourceString);
		return;
	}

	// 归一化类型名: dump 端可能写出全限定名 (如 "/Script/Engine.Texture2D"),
	// 转为短名后下面的各项类型判定才能命中
	Type = NormalizeAssetType(Type);

	// —— 分支一: 动态材质实例 (MaterialInstanceDynamic) ——
	if (Type == TEXT("MaterialInstanceDynamic"))
	{
		// 读取基础材质路径并加载
		FString BaseMaterialPath = InTextureDataRoot->GetStringField(TEXT("MaterialPath"));
		UMaterialInterface* BaseMaterial = LoadObject<UMaterialInterface>(nullptr, *BaseMaterialPath);
		if (!BaseMaterial)
		{
			UE_LOG(LogLQARestore, Error, TEXT("BaseMaterial not found"));
			return;
		}

		// 基于基础材质创建动态材质实例 (以 InImage 作为 Outer)
		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseMaterial, InImage);
		if (!MID)
		{
			UE_LOG(LogLQARestore, Error, TEXT("Failed to create MID"));
			return;
		}
		// 应用 JSON 中的材质参数, 再把动态材质挂到既有画刷上
		ApplyMaterialParametersFromJson(MID, InTextureDataRoot);
		InImage->SetBrushResourceObject(MID);
		return;
	}
	// —— 分支二: 其它资源类型 (Texture2D / PaperSprite / MaterialInstanceConstant) ——
	else
	{
		// 按类型加载资源对象
		UObject* ResourceObject = LoadResourceByType(Type, Path);
		if (!ResourceObject)
		{
			// 按路径加载失败: 运行时生成的纹理 (如 /Engine/Transient.Texture2D_x) 并不存在于磁盘上,
			// 此时退回到 dump session 目录内的导出结果, 用 nameMD5 定位那份 PNG 并重建成运行时纹理
			FString NameMD5;
			InTextureDataRoot->TryGetStringField(TEXT("nameMD5"), NameMD5);

			FString SnapshotDirectory;
			if (RestoreWindowProxy)
			{
				SnapshotDirectory = RestoreWindowProxy->GetSnapshotDirectory();
			}

			if (UTexture2D* FallbackTexture =
					LoadRuntimeTextureFromSnapshot(RestoreWindowProxy, SnapshotDirectory, NameMD5))
			{
				InImage->SetBrushResourceObject(FallbackTexture);
				UE_LOG(LogLQARestore, Log, TEXT("Applied exported PNG fallback for %s (nameMD5=%s)"),
					*ResourceString, *NameMD5);
				return;
			}

			UE_LOG(LogLQARestore, Warning, TEXT("LoadResourceByType failed for %s %s"), *Type, *Path);
			return;
		}

		// 2D 纹理
		if (Type == TEXT("Texture2D"))
		{
			UTexture2D* Texture = Cast<UTexture2D>(ResourceObject);
			if (Texture)
			{
				InImage->SetBrushResourceObject(Texture);
				return;
			}
		}
		// 2D 精灵
		else if (Type == TEXT("PaperSprite"))
		{
			UPaperSprite* Sprite = Cast<UPaperSprite>(ResourceObject);
			if (Sprite)
			{
				InImage->SetBrushResourceObject(Sprite);
				return;
			}
		}
		// 常量材质实例
		else if (Type == TEXT("MaterialInstanceConstant"))
		{
			UMaterialInstanceConstant* MatInst = Cast<UMaterialInstanceConstant>(ResourceObject);
			if (MatInst)
			{
				InImage->SetBrushResourceObject(MatInst);
				return;
			}
		}
		// 不支持的类型或类型转换失败
		else
		{
			UE_LOG(LogLQARestore, Warning, TEXT("Unsupported resource type or failed to cast: %s"), *Type);
		}
	}
}

// 根据资源字符串构建画刷 (输出到 OutBrush), 不直接设置到控件
bool FTextureUtils::SetBrushFromResourceString(
	UImage* InImage, FSlateBrush& OutBrush, const FString& ResourceString, const TSharedPtr<FJsonObject>& JsonObject)
{
	FString Type, Path;

	// 解析资源字符串
	UE_LOG(LogLQARestore, Warning, TEXT("ResourceString: %s"), *ResourceString);
	if (!ParseResourceString(ResourceString, Type, Path))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("ParseResourceString failed for %s"), *ResourceString);
		return false;
	}

	// —— 材质类型 (动态/常量): 统一创建动态材质实例并应用参数 ——
	if (Type == TEXT("MaterialInstanceDynamic") || Type == TEXT("MaterialInstanceConstant"))
	{
		FString BaseMaterialPath = JsonObject->GetStringField(TEXT("MaterialPath"));
		UMaterialInterface* BaseMaterial = LoadObject<UMaterialInterface>(nullptr, *BaseMaterialPath);
		if (!BaseMaterial)
		{
			UE_LOG(LogLQARestore, Error, TEXT("BaseMaterial not found"));
			return false;
		}

		UMaterialInstanceDynamic* MID = UMaterialInstanceDynamic::Create(BaseMaterial, InImage);
		if (!MID)
		{
			UE_LOG(LogLQARestore, Error, TEXT("Failed to create MID"));
			return false;
		}

		// 应用材质参数, 并填充输出画刷
		ApplyMaterialParametersFromJson(MID, JsonObject);
		OutBrush.SetResourceObject(MID);
		OutBrush.ImageSize = FVector2D(1920.0f, 1080.0f);   // 材质默认使用 1920x1080 的尺寸
		OutBrush.DrawAs = ESlateBrushDrawType::Image;        // 以图片方式绘制
		return true;
	}
	// —— 其它资源类型 ——
	else
	{
		UObject* ResourceObject = LoadResourceByType(Type, Path);
		if (!ResourceObject)
		{
			UE_LOG(LogLQARestore, Warning, TEXT("LoadResourceByType failed for %s %s"), *Type, *Path);
			return false;
		}

		// 2D 纹理: 画刷尺寸取纹理实际宽高
		if (Type == TEXT("Texture2D"))
		{
			UTexture2D* Texture = Cast<UTexture2D>(ResourceObject);
			if (Texture)
			{
				OutBrush.SetResourceObject(Texture);
				OutBrush.ImageSize = FVector2D(Texture->GetSizeX(), Texture->GetSizeY());
				OutBrush.DrawAs = ESlateBrushDrawType::Image;
				return true;
			}
		}
		// 2D 精灵: 画刷尺寸取精灵源尺寸
		else if (Type == TEXT("PaperSprite"))
		{
			UPaperSprite* Sprite = Cast<UPaperSprite>(ResourceObject);
			if (Sprite)
			{
				OutBrush.SetResourceObject(Sprite);
#if WITH_EDITOR
				OutBrush.ImageSize = FVector2D(Sprite->GetSourceSize().X, Sprite->GetSourceSize().Y);
#else
				// 打包 (非编辑器) 构建下无法获取精灵源尺寸, 画刷尺寸置零 (由上层按需处理)
				OutBrush.ImageSize = FVector2D::ZeroVector;
				UE_LOG(LogLQARestore, Warning,
					TEXT("PaperSprite 源尺寸(GetSourceSize)为编辑器专属, 打包版本置零"));
#endif
				OutBrush.DrawAs = ESlateBrushDrawType::Image;
				return true;
			}
		}
	}

	// 走到这里说明类型不支持或转换失败
	UE_LOG(LogLQARestore, Warning, TEXT("Unsupported resource type or failed to cast: %s"), *Type);
	return false;
}

// 解析资源字符串: "Type'Path'" -> Type + Path
bool FTextureUtils::ParseResourceString(const FString& ResourceString, FString& OutType, FString& OutPath)
{
	// 查找第一个单引号的位置, 用于分隔类型和路径
	int32 QuoteIndex = ResourceString.Find(TEXT("'"));
	if (QuoteIndex == INDEX_NONE)
		return false;

	// 单引号之前为类型
	OutType = ResourceString.Left(QuoteIndex);
	// 单引号之后为路径
	OutPath = ResourceString.Mid(QuoteIndex + 1);
	// 去除路径末尾的右单引号
	if (OutPath.EndsWith(TEXT("'")))
	{
		OutPath.LeftChopInline(1);
	}
	return true;
}

// 根据类型和路径同步加载对应的资源对象
UObject* FTextureUtils::LoadResourceByType(const FString& Type, const FString& Path)
{
	// dump 端可能写出全限定类型名 (如 "/Script/Engine.Texture2D"),
	// 必须先归一化为短名再判定, 否则所有分支都会落空
	const FString CanonicalType = NormalizeAssetType(Type);

	if (CanonicalType == TEXT("Texture2D"))
	{
		return Cast<UTexture2D>(StaticLoadObject(UTexture2D::StaticClass(), nullptr, *Path));
	}
	else if (CanonicalType == TEXT("PaperSprite"))
	{
		return Cast<UPaperSprite>(StaticLoadObject(UPaperSprite::StaticClass(), nullptr, *Path));
	}
	else if (CanonicalType == TEXT("MaterialInstanceConstant"))
	{
		return Cast<UMaterialInstanceConstant>(
			StaticLoadObject(UMaterialInstanceConstant::StaticClass(), nullptr, *Path));
	}

	// 未知类型返回空指针
	return nullptr;
}

// 归一化资源类型名: "/Script/Engine.Texture2D" -> "Texture2D"
FString FTextureUtils::NormalizeAssetType(const FString& InType)
{
	// 全限定名形如 "/Script/Engine.Texture2D", 取最后一个 '/' 之后的部分
	int32 SlashIndex = INDEX_NONE;
	if (InType.FindLastChar(TEXT('/'), SlashIndex) && SlashIndex < InType.Len() - 1)
	{
		return InType.RightChop(SlashIndex + 1);
	}
	return InType;
}

// 从 dump session 目录的 Textures/<NameMD5>.png 兜底还原运行时生成的纹理
UTexture2D* FTextureUtils::LoadRuntimeTextureFromSnapshot(
	URestoreWindowProxy* RestoreWindowProxy, const FString& SnapshotDirectory, const FString& NameMD5)
{
	if (SnapshotDirectory.IsEmpty() || NameMD5.IsEmpty())
	{
		return nullptr;
	}

	// dump 端约定: 导出的运行时纹理位于 <SessionDir>/Textures/<nameMD5>.png
	const FString PngFilePath = FPaths::Combine(SnapshotDirectory, TEXT("Textures"), NameMD5 + TEXT(".png"));

	// 优先命中窗口内的纹理缓存, 避免重复解码同一张 PNG
	if (RestoreWindowProxy)
	{
		if (UTexture2D* const* CachedTexture = RestoreWindowProxy->SharedTextureMap.Find(PngFilePath))
		{
			return *CachedTexture;
		}
	}

	if (!FPaths::FileExists(PngFilePath))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("No exported PNG fallback at %s"), *PngFilePath);
		return nullptr;
	}

	TArray<uint8> FileData;
	if (!FFileHelper::LoadFileToArray(FileData, *PngFilePath))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to read PNG file: %s"), *PngFilePath);
		return nullptr;
	}

	// 解码 PNG
	IImageWrapperModule& ImageWrapperModule =
		FModuleManager::LoadModuleChecked<IImageWrapperModule>(FName("ImageWrapper"));
	const TSharedPtr<IImageWrapper> ImageWrapper = ImageWrapperModule.CreateImageWrapper(EImageFormat::PNG);
	if (!ImageWrapper.IsValid() || !ImageWrapper->SetCompressed(FileData.GetData(), FileData.Num()))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to parse PNG data: %s"), *PngFilePath);
		return nullptr;
	}

	TArray<uint8> RawData;
	if (!ImageWrapper->GetRaw(ERGBFormat::RGBA, 8, RawData))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to get raw image data: %s"), *PngFilePath);
		return nullptr;
	}

	// 用解码出的像素填充一张运行时纹理
	UTexture2D* Texture =
		UTexture2D::CreateTransient(ImageWrapper->GetWidth(), ImageWrapper->GetHeight(), PF_R8G8B8A8);
	if (!Texture)
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to create transient texture for %s"), *PngFilePath);
		return nullptr;
	}

// UE 5.0+ 中 PlatformData 已私有化, 必须通过 GetPlatformData() 访问; UE4 下保留直接字段访问
#if ENGINE_MAJOR_VERSION >= 5
	if (!Texture->GetPlatformData() || Texture->GetPlatformData()->Mips.Num() == 0)
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Transient texture has no platform data: %s"), *PngFilePath);
		return nullptr;
	}
	void* TextureData = Texture->GetPlatformData()->Mips[0].BulkData.Lock(LOCK_READ_WRITE);
	FMemory::Memcpy(TextureData, RawData.GetData(), RawData.Num());
	Texture->GetPlatformData()->Mips[0].BulkData.Unlock();
#else
	if (!Texture->PlatformData || Texture->PlatformData->Mips.Num() == 0)
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Transient texture has no platform data: %s"), *PngFilePath);
		return nullptr;
	}
	void* TextureData = Texture->PlatformData->Mips[0].BulkData.Lock(LOCK_READ_WRITE);
	FMemory::Memcpy(TextureData, RawData.GetData(), RawData.Num());
	Texture->PlatformData->Mips[0].BulkData.Unlock();
#endif

	// 将 CPU 端数据提交到 GPU, 使纹理生效
	Texture->UpdateResource();

	UE_LOG(LogLQARestore, Log, TEXT("Restored runtime texture %dx%d from %s"), ImageWrapper->GetWidth(),
		ImageWrapper->GetHeight(), *PngFilePath);

	// 入缓存: SharedTextureMap 是 UPROPERTY, 可确保该纹理不被 GC 回收
	if (RestoreWindowProxy)
	{
		RestoreWindowProxy->SharedTextureMap.Add(PngFilePath, Texture);
	}

	return Texture;
}

// 从 JSON 对象中加载纹理 (支持 Texture2D 与 PaperSprite 两种类型)
UTexture2D* FTextureUtils::GetTextureFromJsonObj(
	const TSharedPtr<FJsonObject>& InTextureDataRoot, URestoreWindowProxy* RestoreWindowProxy)
{
	FString Type;
	// 读取 "type" 字段判断资源类型
	if (InTextureDataRoot->TryGetStringField(TEXT("type"), Type))
	{
		// —— 类型一: Texture2D ——
		if (Type.Equals(TEXT("Texture2D")))
		{
			FString TextureName;

			// 读取纹理名称 (通常格式为 "Texture2D /Game/.../Name")
			if (InTextureDataRoot->TryGetStringField(TEXT("name"), TextureName))
			{
				FString PathName;
				int32 SpaceIndex;
				// 以空格分隔, 空格之后的部分为真实资源路径
				if (TextureName.FindChar(TEXT(' '), SpaceIndex))
				{
					PathName = TextureName.Mid(SpaceIndex + 1);
					UE_LOG(LogLQARestore, Log, TEXT("PathName space: %s"), *PathName);
				}

				// 优先从纹理缓存中查找, 命中则直接返回, 避免重复加载
				if (RestoreWindowProxy->SharedTextureMap.Find(TextureName))
				{
					return RestoreWindowProxy->SharedTextureMap[TextureName];
				}

				// 缓存未命中, 动态加载纹理
				if (TextureName.StartsWith("Texture2D"))
				{
					UTexture2D* NewTexture =
						Cast<UTexture2D>(StaticLoadObject(UTexture2D::StaticClass(), nullptr, *PathName));
					if (NewTexture)
					{
						// 加载成功后写入缓存
						RestoreWindowProxy->SharedTextureMap.Emplace(TextureName, NewTexture);
						UE_LOG(LogLQARestore, Log, TEXT("Loaded Texture2D successfully: %s"), *TextureName);
						return NewTexture;
					}
					UE_LOG(LogLQARestore, Error, TEXT("Failed to load Texture2D: %s"), *PathName);
				}
				else if (TextureName.StartsWith("TextureRenderTarget2D"))
				{
					// 渲染目标纹理暂未实现处理逻辑
					UE_LOG(LogLQARestore, Warning, TEXT("TextureRenderTarget2D not supported: %s"), *TextureName);
				}
				else
				{
					UE_LOG(LogLQARestore, Error, TEXT("Unknown texture type: %s"), *TextureName);
				}
			}
			else
			{
				UE_LOG(LogLQARestore, Error, TEXT("[GetTextureFromJsonObj] Failed to get name field"));
			}
			return nullptr;
		}

		// —— 类型二: PaperSprite (返回其源纹理) ——
		if (Type.Equals(TEXT("PaperSprite")))
		{
			FString TextureName;
			if (InTextureDataRoot->TryGetStringField(TEXT("name"), TextureName))
			{
				// 精灵名称字段 "spritename"
				const FString SpriteName = InTextureDataRoot->GetStringField(TEXT("spritename"));
				FString PathName;
				int32 SpaceIndex;
				// 以空格分隔取出精灵资源路径
				if (SpriteName.FindChar(TEXT(' '), SpaceIndex))
				{
					PathName = SpriteName.Mid(SpaceIndex + 1);
					UE_LOG(LogLQARestore, Log, TEXT("PathName space: %s"), *PathName);
				}

				// 加载精灵资源
				UPaperSprite* MySprite =
					Cast<UPaperSprite>(StaticLoadObject(UPaperSprite::StaticClass(), nullptr, *PathName));
				if (MySprite)
				{
#if WITH_EDITOR
					// 取出精灵的源纹理并写入缓存
					UTexture2D* Texture = MySprite->GetSourceTexture();
					RestoreWindowProxy->SharedTextureMap.Emplace(SpriteName, Texture);
					UE_LOG(LogLQARestore, Log, TEXT("Loaded PaperSprite successfully: %s"), *SpriteName);
					return Texture;
#else
					// 打包 (非编辑器) 构建下 GetSourceTexture 不可用
					UE_LOG(LogLQARestore, Warning,
						TEXT("PaperSprite 源纹理(GetSourceTexture)为编辑器专属, 打包版本不可用: %s"), *SpriteName);
					return nullptr;
#endif
				}
				UE_LOG(LogLQARestore, Error, TEXT("Failed to load PaperSprite: %s"), *PathName);
			}
			else
			{
				UE_LOG(LogLQARestore, Error, TEXT("[GetTextureFromJsonObj] Failed to find texture named"));
			}
			return nullptr;
		}
	}
	// 未能读取到 type 字段
	UE_LOG(LogLQARestore, Error, TEXT("[GetTextureFromJsonObj] Failed to deserialize type"));
	return nullptr;
}

// 读取 Texture2D 的像素数据并压缩为 PNG 二进制
bool FTextureUtils::GetTexture2DData(UTexture2D* Texture2D, TArray<uint8>& OutData)
{
	// 备份原始压缩设置与 sRGB 设置, 读取完成后恢复
	TextureCompressionSettings OldCompressionSettings = Texture2D->CompressionSettings;
	const bool OldSRGB = Texture2D->SRGB;
	// 为了拿到未经处理的原始像素, 临时关闭压缩与 sRGB
	Texture2D->CompressionSettings = TextureCompressionSettings::TC_VectorDisplacementmap;
	Texture2D->SRGB = false;
	Texture2D->UpdateResource();   // 使设置生效, 重新构建纹理资源

	// 计算像素总数与缓冲区字节大小
	size_t PixelCount = Texture2D->GetSizeX() * Texture2D->GetSizeY();
	size_t BufferSize = PixelCount * sizeof(FColor);

	// 分配颜色数组用于接收像素数据
	TArray<FColor> Colors;
	Colors.SetNum(PixelCount);

	// 获取第 0 级 Mip 数据
	// UE 5.0+ 中 PlatformData 已私有化, 必须通过 GetPlatformData() 访问; UE4 下保留直接字段访问
#if ENGINE_MAJOR_VERSION >= 5
	FTexture2DMipMap& Texture_Mip = Texture2D->GetPlatformData()->Mips[0];
#else
	FTexture2DMipMap& Texture_Mip = Texture2D->PlatformData->Mips[0];
#endif
	// 锁定 BulkData 以读写方式访问底层像素内存
	void* Texture_Data = Texture_Mip.BulkData.Lock(LOCK_READ_WRITE);

	// 将像素数据拷贝到颜色数组, 随后解锁
	FMemory::Memcpy(Colors.GetData(), Texture_Data, BufferSize);
	Texture_Mip.BulkData.Unlock();

	// 恢复原始压缩与 sRGB 设置
	Texture2D->CompressionSettings = OldCompressionSettings;
	Texture2D->SRGB = OldSRGB;
	Texture2D->UpdateResource();

	// 将颜色数组压缩为 PNG 二进制
	// UE 5.5+ 中 CompressImageArray 已废弃, 改用 PNGCompressImageArray (要求 TArray64<uint8>&)
#if ENGINE_MAJOR_VERSION >= 5
	TArray64<uint8> PngData;
	FImageUtils::PNGCompressImageArray(Texture2D->GetSizeX(), Texture2D->GetSizeY(), Colors, PngData);
	// 将 64 位数组内容拷贝到输出的 32 位数组
	OutData.Reset(PngData.Num());
	OutData.Append(PngData.GetData(), PngData.Num());
#else
	FImageUtils::CompressImageArray(Texture2D->GetSizeX(), Texture2D->GetSizeY(), Colors, OutData);
#endif

	return true;
}

// 从 JSON 对象中解析纹理元数据 (索引、UV、尺寸)
FLQATextureMeta FTextureUtils::GetTextureMeta(const TSharedPtr<FJsonObject>& TextureDataObj)
{
	FLQATextureMeta MetaData;
	// 读取索引字段, 注意这里减 1 (通常是把 1-based 索引转换为 0-based)
	MetaData.TextureIndex = FJsonUtils::DeserializeFromJson_Int32(TextureDataObj, TEXT("Index")) - 1;
	// 读取 UV 坐标
	MetaData.TextureUV = FJsonUtils::DeserializeFromJson_Vector2D(TextureDataObj, TEXT("UV"));
	// 读取纹理尺寸
	MetaData.TextureSize = FJsonUtils::DeserializeFromJson_Vector2D(TextureDataObj, TEXT("Size"));

	return MetaData;
}