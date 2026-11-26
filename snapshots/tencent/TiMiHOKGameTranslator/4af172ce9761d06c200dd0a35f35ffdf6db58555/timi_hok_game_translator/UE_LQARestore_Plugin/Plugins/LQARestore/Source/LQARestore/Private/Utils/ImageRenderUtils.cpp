#include "Utils/ImageRenderUtils.h"

#include "LQABase.h"  // 提供 LogLQARestore 日志分类

#include "Components/Button.h"  // UButton 控件
#include "Components/Image.h"   // UImage 控件

//==============================================================================
// 画刷与控件可见性 (Brush & Widget Visibility)
//==============================================================================

// 综合判断一个 Slate 画刷是否会真正渲染出可见内容
// 任意一项检查不通过即认为 “不可见”, 提前返回 false
bool FImageRenderUtils::IsBrushVisible(
	const FSlateBrush& Brush, ESlateVisibility Visibility, float RenderOpacity, FVector2D RenderScale)
{
	// 1. 可见性状态: Collapsed (折叠, 不占布局) 或 Hidden (隐藏, 占布局) 都不渲染
	if (Visibility == ESlateVisibility::Collapsed || Visibility == ESlateVisibility::Hidden)
	{
		return false;
	}

	// 2. 渲染不透明度: 小于等于 0 表示完全透明, 不可见
	if (RenderOpacity <= 0.0f)
	{
		return false;
	}

	// 3. 渲染缩放: 任一轴缩放为 0 则被压缩成一条线/一点, 不可见
	if (RenderScale.X == 0.0f || RenderScale.Y == 0.0f)
	{
		return false;
	}

	// 4. 绘制类型: NoDrawType 表示不绘制任何内容
	if (Brush.DrawAs == ESlateBrushDrawType::NoDrawType)
	{
		return false;
	}

	// 5. 图像尺寸: 宽或高小于等于 0 则没有可绘制面积
	FVector2D ImageSize = Brush.GetImageSize();
	if (ImageSize.X <= 0.0f || ImageSize.Y <= 0.0f)
	{
		return false;
	}

	// 6. 着色颜色的 Alpha: 小于等于 0 表示整体被着色为完全透明
	FLinearColor Tint = Brush.TintColor.GetSpecifiedColor();
	if (Tint.A <= 0.0f)
	{
		return false;
	}

	// 7. 资源对象: 若没有绑定资源 (如纹理/材质)
	if (Brush.GetResourceObject() == nullptr)
	{
		// 当绘制类型既不是 Box (九宫格盒子) 也不是 Border (边框) 时,
		// 没有资源意味着没有可绘制内容; 而 Box/Border 可仅靠纯色绘制, 故放行
		if (Brush.DrawAs != ESlateBrushDrawType::Box && Brush.DrawAs != ESlateBrushDrawType::Border)
		{
			return false;
		}
	}

	// 所有检查均通过, 判定为可见
	return true;
}

// 判断画刷是否没有可绘制背景: 绘制类型为 NoDrawType 或无资源对象
bool FImageRenderUtils::IsBrushNoBackground(const FSlateBrush& Brush)
{
	return Brush.DrawAs == ESlateBrushDrawType::NoDrawType || Brush.GetResourceObject() == nullptr;
}

// 判断控件在所有状态下是否都没有背景, 目前仅支持 UButton 和 UImage
bool FImageRenderUtils::IsWidgetNoBackground(UWidget* Widget)
{
	// 空指针保护
	if (!Widget)
	{
		return false;
	}

	// —— 按钮控件 ——
	if (UButton* Button = Cast<UButton>(Widget))
	{
		// UE 5.1+ 中直接访问 UButton::WidgetStyle 已废弃, 必须改用 GetStyle(); UE4 下仍可直接访问字段
#if ENGINE_MAJOR_VERSION >= 5
		const FButtonStyle& Style = Button->GetStyle();
#else
		const FButtonStyle& Style = Button->WidgetStyle;
#endif

		// 只有当按钮的四种状态 (常态/悬停/按下/禁用) 画刷全部无背景时, 才认为该按钮无背景
		return IsBrushNoBackground(Style.Normal) && IsBrushNoBackground(Style.Hovered) &&
			   IsBrushNoBackground(Style.Pressed) && IsBrushNoBackground(Style.Disabled);
	}
	// —— 图像控件 ——
	else if (UImage* Image = Cast<UImage>(Widget))
	{
		// 检查 Image 的画刷是否无背景 (同样做引擎版本兼容处理)
#if ENGINE_MAJOR_VERSION >= 5
		return IsBrushNoBackground(Image->GetBrush());
#else
		return IsBrushNoBackground(Image->Brush);
#endif
	}

	// 其它类型控件暂不处理, 默认返回 false (视为有背景)
	return false;
}

//==============================================================================
// 纹理 Alpha 通道分析 (Texture Alpha Analysis)
//==============================================================================

// 遍历纹理每个像素, 计算 Alpha 大于阈值的可见像素所构成的包围矩形
// 基于 PlatformData (运行时平台数据) 读取像素颜色
FIntRect FImageRenderUtils::GetVisiblePixelRect(UTexture2D* Texture, uint8 AlphaThreshold)
{
	// UE 5.0+ 中 PlatformData 已私有化, 必须通过 GetPlatformData() 访问; UE4 下保留直接字段访问
#if ENGINE_MAJOR_VERSION >= 5
	// 校验纹理有效性及是否存在 Mip 数据
	if (!Texture || !Texture->GetPlatformData() || Texture->GetPlatformData()->Mips.Num() == 0)
	{
		return FIntRect();
	}

	// 取第 0 级 Mip (最高分辨率)
	FTexture2DMipMap& Mip = Texture->GetPlatformData()->Mips[0];
#else
	if (!Texture || !Texture->PlatformData || Texture->PlatformData->Mips.Num() == 0)
	{
		return FIntRect();
	}

	FTexture2DMipMap& Mip = Texture->PlatformData->Mips[0];
#endif
	int32 Width = Mip.SizeX;
	int32 Height = Mip.SizeY;

	// 以只读方式锁定批量数据, 获取像素内存指针
	void* Data = Mip.BulkData.Lock(LOCK_READ_ONLY);
	if (!Data)
	{
		// 锁定失败也要解锁, 避免数据保持锁定状态
		Mip.BulkData.Unlock();
		return FIntRect();
	}

	// 将原始数据按 FColor (BGRA/RGBA 每像素 4 字节) 解释
	FColor* Colors = static_cast<FColor*>(Data);

	// 初始化边界: Min 取最大值、Max 取最小值, 便于后续收敛
	int32 MinX = Width, MinY = Height, MaxX = 0, MaxY = 0;
	bool bFound = false;  // 是否找到至少一个可见像素

	// 逐行逐列扫描所有像素
	for (int32 Y = 0; Y < Height; ++Y)
	{
		for (int32 X = 0; X < Width; ++X)
		{
			FColor& Pixel = Colors[Y * Width + X];
			if (Pixel.A > AlphaThreshold)  // Alpha 超过阈值视为可见
			{
				bFound = true;
				// 不断更新包围矩形的四个边界
				MinX = FMath::Min(MinX, X);
				MinY = FMath::Min(MinY, Y);
				MaxX = FMath::Max(MaxX, X);
				MaxY = FMath::Max(MaxY, Y);
			}
		}
	}

	// 解锁批量数据
	Mip.BulkData.Unlock();

	if (!bFound)
	{
		// 整张纹理完全透明, 返回空矩形
		return FIntRect(0, 0, 0, 0);
	}

	// 注意: MaxX、MaxY 是 “包含” 的像素索引, 而 FIntRect 右下角为开区间, 故需 +1
	return FIntRect(MinX, MinY, MaxX + 1, MaxY + 1);
}

// 检查纹理指定区域内是否存在透明像素, 基于 Source (源) 数据以保证 Alpha 精确
bool FImageRenderUtils::HasTransparencyFromSource(
	UTexture2D* Texture, uint8 AlphaThreshold, FIntPoint RegionUV, FIntPoint RegionSize)
{
#if WITH_EDITOR
	// 纹理及其源数据有效性校验
	if (!Texture || !Texture->Source.IsValid())
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Texture is invalid or has no Source data"));
		return false;
	}

	int32 Width = Texture->Source.GetSizeX();
	int32 Height = Texture->Source.GetSizeY();

	// 若未指定区域尺寸, 则默认检测整张纹理
	if (RegionSize.X == 0 || RegionSize.Y == 0)
	{
		RegionUV = FIntPoint(0, 0);
		RegionSize = FIntPoint(Width, Height);
	}

	// 校验检测区域是否越界
	if (RegionUV.X < 0 || RegionUV.Y < 0 || RegionUV.X + RegionSize.X > Width || RegionUV.Y + RegionSize.Y > Height)
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Detection region exceeds texture bounds"));
		return false;
	}

	// 读取第 0 级 Mip 的原始字节数据 (每像素 4 字节: R,G,B,A)
	TArray<uint8, TSizedDefaultAllocator<64>> RawData;
	if (!Texture->Source.GetMipData(RawData, 0))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to get Mip data"));
		return false;
	}

	// 遍历区域内每个像素, 取其 Alpha 分量 (偏移 +3)
	for (int32 Y = RegionUV.Y; Y < RegionUV.Y + RegionSize.Y; ++Y)
	{
		for (int32 X = RegionUV.X; X < RegionUV.X + RegionSize.X; ++X)
		{
			uint8 Alpha = RawData[(Y * Width + X) * 4 + 3];
			if (Alpha <= AlphaThreshold)  // 一旦发现透明像素立即返回
			{
				return true;
			}
		}
	}

	// 区域内未发现透明像素
	return false;
#else
	// 打包 (非编辑器) 构建下无法访问 UTexture2D::Source, 功能降级
	UE_LOG(LogLQARestore, Warning,
		TEXT("HasTransparencyFromSource 依赖编辑器源数据(Source), 打包版本不可用"));
	return false;
#endif
}

// 由外向内扫描四条边, 求出不透明像素的包围盒, 基于 Source 源数据分析
FIntRect FImageRenderUtils::GetAlphaBoundsFromSource_OuterToInner(
	UTexture2D* Texture, uint8 AlphaThreshold, FIntPoint RegionUV, FIntPoint RegionSize)
{
	// 默认返回空矩形
	FIntRect Result(0, 0, 0, 0);

#if WITH_EDITOR
	// 纹理及其源数据有效性校验
	if (!Texture || !Texture->Source.IsValid())
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Texture is invalid or has no Source data"));
		return Result;
	}

	int32 Width = Texture->Source.GetSizeX();
	int32 Height = Texture->Source.GetSizeY();

	// 未指定区域尺寸则默认为整张纹理
	if (RegionSize.X == 0 || RegionSize.Y == 0)
	{
		RegionUV = FIntPoint(0, 0);
		RegionSize = FIntPoint(Width, Height);
	}

	// 区域越界校验
	if (RegionUV.X < 0 || RegionUV.Y < 0 || RegionUV.X + RegionSize.X > Width || RegionUV.Y + RegionSize.Y > Height)
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Detection region exceeds texture bounds"));
		return Result;
	}

	// 读取第 0 级 Mip 原始字节数据
	TArray<uint8, TSizedDefaultAllocator<64>> RawData;
	if (!Texture->Source.GetMipData(RawData, 0))
	{
		UE_LOG(LogLQARestore, Warning, TEXT("Failed to get Mip data"));
		return Result;
	}

	// 四个边界初始为 -1, 表示尚未找到
	int32 Left = -1;
	int32 Right = -1;
	int32 Top = -1;
	int32 Bottom = -1;

	// —— 从左向右扫描, 找到第一列含不透明像素的位置, 即为左边界 ——
	for (int32 X = RegionUV.X; X < RegionUV.X + RegionSize.X; ++X)
	{
		bool bFound = false;
		for (int32 Y = RegionUV.Y; Y < RegionUV.Y + RegionSize.Y; ++Y)
		{
			uint8 Alpha = RawData[(Y * Width + X) * 4 + 3];
			if (Alpha > AlphaThreshold)
			{
				Left = X;
				bFound = true;
				break;  // 本列已找到不透明像素, 无需继续
			}
		}
		if (bFound)
		{
			break;  // 已确定左边界, 结束外层循环
		}
	}

	// —— 从右向左扫描, 找到右边界 ——
	for (int32 X = RegionUV.X + RegionSize.X - 1; X >= RegionUV.X; --X)
	{
		bool bFound = false;
		for (int32 Y = RegionUV.Y; Y < RegionUV.Y + RegionSize.Y; ++Y)
		{
			uint8 Alpha = RawData[(Y * Width + X) * 4 + 3];
			if (Alpha > AlphaThreshold)
			{
				Right = X;
				bFound = true;
				break;
			}
		}
		if (bFound)
		{
			break;
		}
	}

	// —— 从上向下扫描, 找到上边界 ——
	// 此处 X 范围已利用上面求得的 Left/Right 做收窄优化, 减少无效扫描
	for (int32 Y = RegionUV.Y; Y < RegionUV.Y + RegionSize.Y; ++Y)
	{
		bool bFound = false;
		for (int32 X = (Left != -1 ? Left : RegionUV.X); X <= (Right != -1 ? Right : RegionUV.X + RegionSize.X - 1);
			++X)
		{
			uint8 Alpha = RawData[(Y * Width + X) * 4 + 3];
			if (Alpha > AlphaThreshold)
			{
				Top = Y;
				bFound = true;
				break;
			}
		}
		if (bFound)
		{
			break;
		}
	}

	// —— 从下向上扫描, 找到下边界 ——
	for (int32 Y = RegionUV.Y + RegionSize.Y - 1; Y >= RegionUV.Y; --Y)
	{
		bool bFound = false;
		for (int32 X = (Left != -1 ? Left : RegionUV.X); X <= (Right != -1 ? Right : RegionUV.X + RegionSize.X - 1);
			++X)
		{
			uint8 Alpha = RawData[(Y * Width + X) * 4 + 3];
			if (Alpha > AlphaThreshold)
			{
				Bottom = Y;
				bFound = true;
				break;
			}
		}
		if (bFound)
		{
			break;
		}
	}

	// 若某方向始终未找到不透明像素, 则退回使用该方向的区域默认边界
	if (Left == -1)
	{
		Left = RegionUV.X;
	}
	if (Right == -1)
	{
		Right = RegionUV.X + RegionSize.X - 1;
	}
	if (Top == -1)
	{
		Top = RegionUV.Y;
	}
	if (Bottom == -1)
	{
		Bottom = RegionUV.Y + RegionSize.Y - 1;
	}

	// 返回包围矩形, 由于 FIntRect 右下角为开区间, Right、Bottom 需 +1
	return FIntRect(Left, Top, Right + 1, Bottom + 1);
#else
	// 打包 (非编辑器) 构建下无法访问 UTexture2D::Source, 返回空矩形
	UE_LOG(LogLQARestore, Warning,
		TEXT("GetAlphaBoundsFromSource_OuterToInner 依赖编辑器源数据(Source), 打包版本不可用"));
	return Result;
#endif
}

// 判断某点是否超出视口范围 (坐标为负或超过视口宽高)
bool FImageRenderUtils::IsPointOutOfViewport(const FVector2D& Point, const FVector2D& ViewportSize)
{
	// 任一坐标小于 0, 或超过视口对应的宽/高, 即视为超出
	if (Point.X < 0.f || Point.Y < 0.f || Point.X > ViewportSize.X || Point.Y > ViewportSize.Y)
	{
		return true;  // 超出范围
	}
	return false;  // 在范围内
}