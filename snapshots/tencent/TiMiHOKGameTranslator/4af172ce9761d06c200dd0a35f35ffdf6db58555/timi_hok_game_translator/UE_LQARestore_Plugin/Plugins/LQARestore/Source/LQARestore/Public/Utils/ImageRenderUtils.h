#pragma once

#include "Components/SlateWrapperTypes.h"  // ESlateVisibility 等 Slate 包装类型
#include "Components/Widget.h"             // UWidget 控件基类
#include "CoreMinimal.h"                   // UE 核心基础类型 (FVector2D、FIntRect 等)
#include "Engine/Texture2D.h"              // UTexture2D 2D 纹理资源
#include "Styling/SlateBrush.h"            // FSlateBrush 画刷结构

/**
 * 图像渲染与可见性计算的工具类
 * 提供画刷 (Brush) 可见性检测、纹理 Alpha 通道分析、以及几何边界运算等能力
 * 该类是纯静态工具类, 无需实例化, 所有方法均通过 FImageRenderUtils::Xxx 直接调用
 */
class FImageRenderUtils
{
public:
	//==============================================================================
	// 画刷与控件可见性 (Brush & Widget Visibility)
	//==============================================================================

	/**
	 * 根据多个因素综合判断一个 Slate 画刷是否 “可见” (即是否会真正渲染出内容)
	 * 依次检查: 可见性状态、渲染不透明度、渲染缩放、绘制类型、图像尺寸、着色颜色、以及资源对象
	 * @param Brush         - 待检测的画刷
	 * @param Visibility    - 控件的可见性状态
	 * @param RenderOpacity - 渲染不透明度 (取值范围 0.0 ~ 1.0)
	 * @param RenderScale   - 渲染缩放向量
	 * @return 画刷可见返回 true, 否则返回 false
	 */
	static bool IsBrushVisible(
		const FSlateBrush& Brush, ESlateVisibility Visibility, float RenderOpacity, FVector2D RenderScale);

	/**
	 * 判断一个画刷是否没有可绘制的背景 (即无绘制类型或无资源对象)
	 * @param Brush - 待检测的画刷
	 * @return 画刷无背景返回 true
	 */
	static bool IsBrushNoBackground(const FSlateBrush& Brush);

	/**
	 * 判断一个控件在其所有状态下是否都没有背景
	 * 目前支持 UButton (检查 Normal/Hovered/Pressed/Disabled 四个状态) 和 UImage 控件
	 * @param Widget - 待检测的控件
	 * @return 控件无背景返回 true
	 */
	static bool IsWidgetNoBackground(UWidget* Widget);

	//==============================================================================
	// 纹理 Alpha 通道分析 (Texture Alpha Analysis)
	//==============================================================================

	/**
	 * 计算纹理中可见 (非透明) 像素的包围矩形
	 * 基于 PlatformData (平台已烘焙的运行时数据) 进行分析
	 * @param Texture        - 待分析的纹理
	 * @param AlphaThreshold - Alpha 值大于该阈值的像素被视为可见 (默认 10)
	 * @return 可见像素的包围矩形
	 */
	static FIntRect GetVisiblePixelRect(UTexture2D* Texture, uint8 AlphaThreshold = 10);

	/**
	 * 检查纹理的指定区域内是否存在任意透明像素
	 * 使用纹理的 Source (源) 数据进行精确的 Alpha 通道分析
	 * @param Texture        - 待检测的纹理
	 * @param AlphaThreshold - Alpha 值小于等于该阈值的像素被视为透明 (默认 0)
	 * @param RegionUV       - 检测区域的左上角 UV 坐标 (默认 0,0)
	 * @param RegionSize     - 检测区域的尺寸 (默认 0,0 表示整张纹理)
	 * @return 存在透明像素返回 true
	 */
	static bool HasTransparencyFromSource(UTexture2D* Texture, uint8 AlphaThreshold = 0,
		FIntPoint RegionUV = FIntPoint(0, 0), FIntPoint RegionSize = FIntPoint(0, 0));

	/**
	 * 计算非透明像素的包围盒 (边界框)
	 * 采用 “由外向内” 扫描策略: 从矩形四条边向中心逐行/逐列扫描, 找到第一条含不透明像素的边界即停止
	 * @param Texture        - 待分析的纹理
	 * @param AlphaThreshold - Alpha 值大于该阈值视为不透明 (默认 0)
	 * @param RegionUV       - 检测区域的左上角 UV 坐标 (默认 0,0)
	 * @param RegionSize     - 检测区域的尺寸 (默认 0,0 表示整张纹理)
	 * @return 不透明区域的包围盒 (Min 为闭区间, Max 为开区间)
	 */
	static FIntRect GetAlphaBoundsFromSource_OuterToInner(UTexture2D* Texture, uint8 AlphaThreshold = 0,
		FIntPoint RegionUV = FIntPoint(0, 0), FIntPoint RegionSize = FIntPoint(0, 0));

	/**
	 * 判断一个点是否超出了视口 (Viewport) 边界
	 * @param Point        - 待检测的点坐标
	 * @param ViewportSize - 视口尺寸
	 * @return 点在视口外返回 true
	 */
	static bool IsPointOutOfViewport(const FVector2D& Point, const FVector2D& ViewportSize);
};