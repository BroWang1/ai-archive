#include "Utils/SlateBrushUtils.h"

#include "LQABase.h"

#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"

// 根据 JSON 对象创建 FSlateBrush: 逐个字段尝试解析, 解析成功才覆盖对应属性, 失败则保留默认值
FSlateBrush FSlateBrushUtils::CreateSlateBrushFromJson(
	const TSharedPtr<FJsonObject>& JsonObject, UObject* ResourceObject)
{
	// 创建一个使用默认值初始化的画刷
	FSlateBrush Brush;

	// 若传入了资源对象 (纹理/材质等)，则设置到画刷上
	if (ResourceObject)
	{
		Brush.SetResourceObject(ResourceObject);
	}

	// 解析图片尺寸 ImageSize([X, Y] 数组)
	FVector2D ImageSize;
	if (ParseVector2D(JsonObject, TEXT("ImageSize"), ImageSize))
	{
		Brush.ImageSize = ImageSize;
	}

	// 解析边距 Margin (Left/Top/Right/Bottom 子对象)
	FMargin Margin;
	if (ParseMargin(JsonObject, TEXT("Margin"), Margin))
	{
		Brush.Margin = Margin;
	}

	// 解析着色颜色 TintColor
	FSlateColor TintColor;
	if (ParseSlateColor(JsonObject, TEXT("TintColor"), TintColor))
	{
		Brush.TintColor = TintColor;
	}

	// 解析 UV 区域 UVRegion (定义采样纹理的子区域)
	const TSharedPtr<FJsonObject>* UVRegionObj;
	if (JsonObject->TryGetObjectField(TEXT("UVRegion"), UVRegionObj))
	{
		// UVRegion 需要同时包含 MinX/MinY/MaxX/MaxY 四个数值字段
		double MinX = 0.0, MinY = 0.0, MaxX = 0.0, MaxY = 0.0;
		if ((*UVRegionObj)->TryGetNumberField(TEXT("MinX"), MinX) &&
			(*UVRegionObj)->TryGetNumberField(TEXT("MinY"), MinY) &&
			(*UVRegionObj)->TryGetNumberField(TEXT("MaxX"), MaxX) &&
			(*UVRegionObj)->TryGetNumberField(TEXT("MaxY"), MaxY))
		{
			// 用最小点和最大点构造一个 FBox2D 作为 UV 区域
			Brush.SetUVRegion(FBox2D(FVector2D(static_cast<float>(MinX), static_cast<float>(MinY)),
				FVector2D(static_cast<float>(MaxX), static_cast<float>(MaxY))));
		}
	}

	// 解析绘制方式 DrawAs (如 Box / Border / Image 等)
	ESlateBrushDrawType::Type DrawAs;
	if (ParseEnum(JsonObject, TEXT("DrawAs"), DrawAs))
	{
		Brush.DrawAs = DrawAs;
	}

	// 解析平铺方式 Tiling (水平/垂直/双向平铺)
	ESlateBrushTileType::Type Tiling;
	if (ParseEnum(JsonObject, TEXT("Tiling"), Tiling))
	{
		Brush.Tiling = Tiling;
	}

	// 解析镜像方式 Mirroring (水平/垂直/双向镜像)
	ESlateBrushMirrorType::Type Mirroring;
	if (ParseEnum(JsonObject, TEXT("Mirroring"), Mirroring))
	{
		Brush.Mirroring = Mirroring;
	}

	// 解析图片类型 ImageType (如 FullColor / Linear 等)
	ESlateBrushImageType::Type ImageType;
	if (ParseEnum(JsonObject, TEXT("ImageType"), ImageType))
	{
		Brush.ImageType = ImageType;
	}

	// 记录日志, 表示画刷已从 JSON 成功创建
	UE_LOG(LogLQARestore, Log, TEXT("Created SlateBrush from JSON"));
	return Brush;
}

// 解析二维向量: 期望 JSON 字段是一个长度为 2 的数组 [X, Y]
bool FSlateBrushUtils::ParseVector2D(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FVector2D& OutVector)
{
	const TArray<TSharedPtr<FJsonValue>>* ArrayPtr;
	// 字段必须存在、是数组且长度恰好为 2
	if (JsonObject->TryGetArrayField(FieldName, ArrayPtr) && ArrayPtr->Num() == 2)
	{
		double X = 0, Y = 0;
		// 两个元素都必须能转换为数值
		if ((*ArrayPtr)[0]->TryGetNumber(X) && (*ArrayPtr)[1]->TryGetNumber(Y))
		{
			OutVector = FVector2D(static_cast<float>(X), static_cast<float>(Y));
			return true;
		}
	}
	return false;
}

// 解析边距: 期望 JSON 字段是一个包含 Left/Top/Right/Bottom 的子对象
bool FSlateBrushUtils::ParseMargin(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FMargin& OutMargin)
{
	const TSharedPtr<FJsonObject>* MarginObj;
	if (JsonObject->TryGetObjectField(FieldName, MarginObj))
	{
		double Left = 0, Top = 0, Right = 0, Bottom = 0;
		// 四个方向的数值都必须存在才算解析成功
		if ((*MarginObj)->TryGetNumberField(TEXT("Left"), Left) && (*MarginObj)->TryGetNumberField(TEXT("Top"), Top) &&
			(*MarginObj)->TryGetNumberField(TEXT("Right"), Right) &&
			(*MarginObj)->TryGetNumberField(TEXT("Bottom"), Bottom))
		{
			OutMargin = FMargin(static_cast<float>(Left), static_cast<float>(Top), static_cast<float>(Right),
				static_cast<float>(Bottom));
			return true;
		}
	}
	return false;
}

// 解析线性颜色: 期望 JSON 字段是包含 R/G/B 的子对象, A (透明度) 可选, 缺省为 1.0 (不透明)
bool FSlateBrushUtils::ParseLinearColor(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FLinearColor& OutColor)
{
	const TSharedPtr<FJsonObject>* ColorObj;
	if (JsonObject->TryGetObjectField(FieldName, ColorObj))
	{
		double R = 0, G = 0, B = 0, A = 1.0;
		// R/G/B 为必填项
		if ((*ColorObj)->TryGetNumberField(TEXT("R"), R) && (*ColorObj)->TryGetNumberField(TEXT("G"), G) &&
			(*ColorObj)->TryGetNumberField(TEXT("B"), B))
		{
			// A 为可选项: 若存在则覆盖默认值 1.0, 不存在时忽略返回值保持默认
			(*ColorObj)->TryGetNumberField(TEXT("A"), A);
			OutColor = FLinearColor(
				static_cast<float>(R), static_cast<float>(G), static_cast<float>(B), static_cast<float>(A));
			return true;
		}
	}
	return false;
}

// 解析 Slate 颜色: 先按线性颜色解析, 再包装为 FSlateColor
bool FSlateBrushUtils::ParseSlateColor(
	const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, FSlateColor& OutColor)
{
	FLinearColor LinearColor;
	if (ParseLinearColor(JsonObject, FieldName, LinearColor))
	{
		OutColor = FSlateColor(LinearColor);
		return true;
	}
	return false;
}

// 解析枚举: JSON 中以字符串存储枚举名, 这里根据不同枚举类型做字符串到枚举值的映射
// 使用 if constexpr 在编译期按 EnumType 选择对应的分支, 避免运行时开销与无效比较
template <typename EnumType>
bool FSlateBrushUtils::ParseEnum(const TSharedPtr<FJsonObject>& JsonObject, const FString& FieldName, EnumType& OutEnum)
{
	FString EnumStr;
	// 先尝试把字段读取为字符串
	if (JsonObject->TryGetStringField(FieldName, EnumStr))
	{
		// 空字符串视为无效, 解析失败
		if (EnumStr.Len() == 0)
			return false;

		// 画刷绘制方式枚举
		if constexpr (std::is_same<EnumType, ESlateBrushDrawType::Type>::value)
		{
			// "NoDrawType" 与 "None" 都映射为不绘制
			if (EnumStr == "NoDrawType" || EnumStr == "None")
			{
				OutEnum = ESlateBrushDrawType::NoDrawType;
				return true;
			}
			else if (EnumStr == "Box") // 九宫格盒子绘制
			{
				OutEnum = ESlateBrushDrawType::Box;
				return true;
			}
			else if (EnumStr == "Border") // 边框绘制
			{
				OutEnum = ESlateBrushDrawType::Border;
				return true;
			}
			else if (EnumStr == "Image") // 普通图片绘制
			{
				OutEnum = ESlateBrushDrawType::Image;
				return true;
			}
		}
		// 画刷平铺方式枚举
		else if constexpr (std::is_same<EnumType, ESlateBrushTileType::Type>::value)
		{
			if (EnumStr == "NoTile") // 不平铺
			{
				OutEnum = ESlateBrushTileType::NoTile;
				return true;
			}
			else if (EnumStr == "Horizontal") // 水平平铺
			{
				OutEnum = ESlateBrushTileType::Horizontal;
				return true;
			}
			else if (EnumStr == "Vertical") // 垂直平铺
			{
				OutEnum = ESlateBrushTileType::Vertical;
				return true;
			}
			else if (EnumStr == "Both") // 水平和垂直都平铺
			{
				OutEnum = ESlateBrushTileType::Both;
				return true;
			}
		}
		// 画刷镜像方式枚举
		else if constexpr (std::is_same<EnumType, ESlateBrushMirrorType::Type>::value)
		{
			if (EnumStr == "NoMirror") // 不镜像
			{
				OutEnum = ESlateBrushMirrorType::NoMirror;
				return true;
			}
			else if (EnumStr == "Horizontal") // 水平镜像
			{
				OutEnum = ESlateBrushMirrorType::Horizontal;
				return true;
			}
			else if (EnumStr == "Vertical") // 垂直镜像
			{
				OutEnum = ESlateBrushMirrorType::Vertical;
				return true;
			}
			else if (EnumStr == "Both") // 水平和垂直都镜像
			{
				OutEnum = ESlateBrushMirrorType::Both;
				return true;
			}
		}
		// 画刷图片类型枚举
		else if constexpr (std::is_same<EnumType, ESlateBrushImageType::Type>::value)
		{
			if (EnumStr == "NoImage") // 无图片
			{
				OutEnum = ESlateBrushImageType::NoImage;
				return true;
			}
			else if (EnumStr == "FullColor") // 全彩图片
			{
				OutEnum = ESlateBrushImageType::FullColor;
				return true;
			}
			else if (EnumStr == "Linear") // 线性颜色空间图片
			{
				OutEnum = ESlateBrushImageType::Linear;
				return true;
			}
		}
	}
	// 字段不存在、不是字符串或字符串未匹配到任何枚举值时返回 false
	return false;
}

// 显式模板实例化: 由于 ParseEnum 的定义位于 .cpp 中,
// 需要为用到的每种枚举类型显式实例化, 以避免其他翻译单元调用时产生链接错误
template bool FSlateBrushUtils::ParseEnum<ESlateBrushDrawType::Type>(
	const TSharedPtr<FJsonObject>&, const FString&, ESlateBrushDrawType::Type&);
template bool FSlateBrushUtils::ParseEnum<ESlateBrushTileType::Type>(
	const TSharedPtr<FJsonObject>&, const FString&, ESlateBrushTileType::Type&);
template bool FSlateBrushUtils::ParseEnum<ESlateBrushMirrorType::Type>(
	const TSharedPtr<FJsonObject>&, const FString&, ESlateBrushMirrorType::Type&);
template bool FSlateBrushUtils::ParseEnum<ESlateBrushImageType::Type>(
	const TSharedPtr<FJsonObject>&, const FString&, ESlateBrushImageType::Type&);