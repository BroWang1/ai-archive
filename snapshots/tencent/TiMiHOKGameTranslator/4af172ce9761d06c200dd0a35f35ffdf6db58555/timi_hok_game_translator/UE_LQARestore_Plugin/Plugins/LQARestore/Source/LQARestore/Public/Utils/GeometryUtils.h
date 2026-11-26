#pragma once

#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Dom/JsonValue.h"

/**
 * 几何工具类 (FGeometryUtils)
 *
 * 提供多边形 / 矩形相关的几何运算以及 JSON 数据转换功能,
 * 主要用于控件 (Widget) 边界校验与重叠检测等场景
 *
 * 该类中所有方法均为静态方法 (static), 无需实例化即可直接调用,
 * 可将其视为一个纯函数工具集
 */
class FGeometryUtils
{
public:
	/**
	 * 将 JSON 数组转换为 FVector2D (二维向量) 数组, 并可选地进行数量校验
	 *
	 * JSON 数组中的每个元素应为形如 { "x": <number>, "y": <number> } 的对象
	 *
	 * @param JsonArray     输入的 JSON 数组
	 * @param OutPoints     输出参数, 转换后得到的二维点数组
	 * @param ExpectedCount 期望的点数量; 传入 -1 表示不做数量校验
	 * @return 转换成功返回 true;若指定了 ExpectedCount, 则还需实际数量与之一致
	 */
	static bool JsonArrayToVector2DArray(
		const TArray<TSharedPtr<FJsonValue>>& JsonArray, TArray<FVector2D>& OutPoints, int32 ExpectedCount = -1);

	/**
	 * 从 JSON 数组中解析四个角点坐标到 FVector2D 数组
	 *
	 * 本函数是对 JsonArrayToVector2DArray 的封装, 固定要求解析出 4 个角点,
	 * 常用于矩形 / 四边形控件边框的解析
	 *
	 * @param CornersParent 包含角点数据的 JSON 数组
	 * @param OutCorners    输出参数, 解析得到的角点坐标数组
	 * @return 恰好成功解析出 4 个角点时返回 true
	 */
	static FORCEINLINE bool ParseCornersFromJsonArray(
		const TArray<TSharedPtr<FJsonValue>>& CornersParent, TArray<FVector2D>& OutCorners)
	{
		// 内联函数的定义必须在头文件中, 否则会导致 C4506 (没有定义)错误
		// 四边形固定有 4 个角点
		constexpr int32 PolygonCornerCount = 4;
		return JsonArrayToVector2DArray(CornersParent, OutCorners, PolygonCornerCount);
	}

	/**
	 * 根据一组角点计算其轴对齐包围盒 (AABB)
	 *
	 * @param Corners 角点坐标数组
	 * @return 覆盖所有角点的轴对齐包围盒 (FBox2D)
	 */
	static FBox2D GetBoundingBox(const TArray<FVector2D>& Corners);

	/**
	 * 计算两个包围盒之间的重叠比例
	 *
	 * 比例以 BoxB 的面积为基准, 即: 重叠面积 / BoxB 面积
	 *
	 * @param BoxA 第一个包围盒
	 * @param BoxB 第二个包围盒 (作为比例计算的基准)
	 * @return 重叠面积占 BoxB 面积的比例, 取值范围 [0.0, 1.0]
	 */
	static float GetOverlapRatio(const FBox2D& BoxA, const FBox2D& BoxB);

	/**
	 * 使用射线投射算法 (Ray Casting) 判断某个点是否位于多边形内部
	 *
	 * @param Point   待测试的点
	 * @param Polygon 多边形的顶点数组 (按顺序排列)
	 * @return 点在多边形内部返回 true
	 */
	static bool IsPointInPolygon(const FVector2D& Point, const TArray<FVector2D>& Polygon);

	/**
	 * 判断两条线段是否相交
	 *
	 * @param P1 线段 1 的起点
	 * @param P2 线段 1 的终点
	 * @param Q1 线段 2 的起点
	 * @param Q2 线段 2 的终点
	 * @return 两条线段相交返回 true
	 */
	static bool DoLinesIntersect(const FVector2D& P1, const FVector2D& P2, const FVector2D& Q1, const FVector2D& Q2);

	/**
	 * 判断两个多边形的边是否存在相交
	 *
	 * @param A 第一个多边形
	 * @param B 第二个多边形
	 * @return 任意一条边相交则返回 true
	 */
	static bool DoPolygonsEdgesIntersect(const TArray<FVector2D>& A, const TArray<FVector2D>& B);

	/**
	 * 判断两个多边形是否重叠
	 *
	 * 重叠的判定综合考虑三种情况: 顶点互相包含、边相交
	 *
	 * @param A 第一个多边形
	 * @param B 第二个多边形
	 * @return 两个多边形存在重叠返回 true
	 */
	static bool DoPolygonsOverlap(const TArray<FVector2D>& A, const TArray<FVector2D>& B);

#if !UE_BUILD_SHIPPING
	/**
	 * 调试辅助函数: 将 JSON 数组中的点坐标打印到日志
	 *
	 * 仅在非 Shipping (开发 / 调试) 版本中可用, 用于排查数据问题
	 *
	 * @param JsonArray 待打印的 JSON 数组
	 * @param ArrayName 数组名称, 用于在日志中标识
	 */
	static void PrintJsonArrayPoints(const TArray<TSharedPtr<FJsonValue>>& JsonArray, const FString& ArrayName);
#endif
};