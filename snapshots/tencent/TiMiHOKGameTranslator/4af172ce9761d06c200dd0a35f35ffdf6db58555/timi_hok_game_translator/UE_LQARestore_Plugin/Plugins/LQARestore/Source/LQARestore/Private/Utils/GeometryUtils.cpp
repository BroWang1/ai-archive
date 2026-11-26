#include "Utils/GeometryUtils.h"

#include "LQABase.h"

// 将 JSON 数组转换为二维点 (FVector2D) 数组
bool FGeometryUtils::JsonArrayToVector2DArray(
	const TArray<TSharedPtr<FJsonValue>>& JsonArray, TArray<FVector2D>& OutPoints, int32 ExpectedCount)
{
	// 先清空输出数组, 避免残留旧数据
	OutPoints.Empty();

	// 若已知期望的点数量, 提前预留内存以减少动态扩容带来的开销
	if (ExpectedCount > 0)
	{
		OutPoints.Reserve(ExpectedCount);
	}

	// 遍历 JSON 数组中的每一个元素
	for (const TSharedPtr<FJsonValue>& JsonValue : JsonArray)
	{
		// 跳过空的 JSON 值
		if (!JsonValue.IsValid())
		{
			continue;
		}

		// 将 JSON 值转换为 JSON 对象 (期望形如 { "x": ..., "y": ... })
		const TSharedPtr<FJsonObject> PointObj = JsonValue->AsObject();
		if (!PointObj.IsValid())
		{
			continue;
		}

		// 尝试读取 x、y 两个数值字段, 二者都存在时才算一个有效点
		double X = 0, Y = 0;
		if (PointObj->TryGetNumberField(TEXT("x"), X) && PointObj->TryGetNumberField(TEXT("y"), Y))
		{
			// double 转为 float 存入二维向量数组
			OutPoints.Add(FVector2D(static_cast<float>(X), static_cast<float>(Y)));
		}
	}

	// ExpectedCount < 0 表示不校验数量, 直接视为成功;
	// 否则需要实际解析出的点数与期望数量一致才算成功
	return ExpectedCount < 0 || OutPoints.Num() == ExpectedCount;
}

// 根据一组角点计算轴对齐包围盒 (AABB)
FBox2D FGeometryUtils::GetBoundingBox(const TArray<FVector2D>& Corners)
{
	// 没有角点时返回一个默认 (空) 的包围盒
	if (Corners.Num() == 0)
	{
		return FBox2D();
	}

	// 以第一个角点初始化最小 / 最大坐标
	FVector2D Min = Corners[0];
	FVector2D Max = Corners[0];

	// 遍历剩余角点, 逐步更新包围盒的边界
	for (int32 i = 1; i < Corners.Num(); ++i)
	{
		Min.X = FMath::Min(Min.X, Corners[i].X);
		Min.Y = FMath::Min(Min.Y, Corners[i].Y);
		Max.X = FMath::Max(Max.X, Corners[i].X);
		Max.Y = FMath::Max(Max.Y, Corners[i].Y);
	}

	// 由最小点和最大点构造包围盒
	return FBox2D(Min, Max);
}

// 计算两个包围盒的重叠比例 (相对于 BoxB 的面积)
float FGeometryUtils::GetOverlapRatio(const FBox2D& BoxA, const FBox2D& BoxB)
{
	// 计算重叠区域的左下角 (取两个盒子较大的最小值)
	FVector2D OverlapMin(FMath::Max(BoxA.Min.X, BoxB.Min.X), FMath::Max(BoxA.Min.Y, BoxB.Min.Y));
	// 计算重叠区域的右上角 (取两个盒子较小的最大值)
	FVector2D OverlapMax(FMath::Min(BoxA.Max.X, BoxB.Max.X), FMath::Min(BoxA.Max.Y, BoxB.Max.Y));

	// 重叠区域的宽和高
	float OverlapWidth = OverlapMax.X - OverlapMin.X;
	float OverlapHeight = OverlapMax.Y - OverlapMin.Y;

	// 宽或高小于等于 0, 说明两个盒子没有实际重叠
	if (OverlapWidth <= 0 || OverlapHeight <= 0)
	{
		return 0.f;
	}

	// 重叠面积
	float OverlapArea = OverlapWidth * OverlapHeight;
	// BoxB 的总面积 (作为比例基准)
	float AreaB = (BoxB.Max.X - BoxB.Min.X) * (BoxB.Max.Y - BoxB.Min.Y);

	// 基准面积无效时直接返回 0, 避免除零
	if (AreaB <= 0)
	{
		return 0.f;
	}

	// 返回重叠面积占 BoxB 面积的比例
	return OverlapArea / AreaB;
}

// 射线投射算法: 判断点是否在多边形内部
bool FGeometryUtils::IsPointInPolygon(const FVector2D& Point, const TArray<FVector2D>& Polygon)
{
	// 记录射线与多边形边的交点个数
	int32 Intersections = 0;
	const int32 N = Polygon.Num();

	// 依次遍历多边形的每一条边 (P1 -> P2)
	for (int32 i = 0; i < N; ++i)
	{
		const FVector2D& P1 = Polygon[i];
		// 使用取模保证最后一条边能连回起点, 形成闭合多边形
		const FVector2D& P2 = Polygon[(i + 1) % N];

		// 从测试点向右发出一条水平射线：
		// 1) (P1.Y > Point.Y) != (P2.Y > Point.Y) 判断该边是否跨越测试点所在的水平线;
		// 2) 后半部分计算该边与水平线交点的 X 坐标, 若在测试点右侧则记一次相交
		if (((P1.Y > Point.Y) != (P2.Y > Point.Y)) &&
			(Point.X < (P2.X - P1.X) * (Point.Y - P1.Y) / (P2.Y - P1.Y) + P1.X))
		{
			Intersections++;
		}
	}

	// 交点个数为奇数时, 点在多边形内部 (奇偶规则)
	return (Intersections % 2) == 1;
}

// 判断两条线段 (P1P2) 与 (Q1Q2) 是否相交
bool FGeometryUtils::DoLinesIntersect(
	const FVector2D& P1, const FVector2D& P2, const FVector2D& Q1, const FVector2D& Q2)
{
	// Orientation: 计算三点 (A, B, C) 的方向 (叉积符号)
	//   返回 0 -> 三点共线
	//   返回 1 -> 顺时针方向
	//   返回 2 -> 逆时针方向
	TFunction<int32(const FVector2D&, const FVector2D&, const FVector2D&)> Orientation =
		[](const FVector2D& A, const FVector2D& B, const FVector2D& C)
	{
		float Val = (B.Y - A.Y) * (C.X - B.X) - (B.X - A.X) * (C.Y - B.Y);
		if (Val == 0)
		{
			return 0;
		}
		return (Val > 0) ? 1 : 2;
	};

	// OnSegment: 在已知三点共线的前提下, 判断点 B 是否落在线段 AC 上
	TFunction<bool(const FVector2D&, const FVector2D&, const FVector2D&)> OnSegment =
		[](const FVector2D& A, const FVector2D& B, const FVector2D& C)
	{
		return B.X <= FMath::Max(A.X, C.X) && B.X >= FMath::Min(A.X, C.X) && B.Y <= FMath::Max(A.Y, C.Y) &&
			   B.Y >= FMath::Min(A.Y, C.Y);
	};

	// 分别计算四组三点的方向关系
	int O1 = Orientation(P1, P2, Q1);
	int O2 = Orientation(P1, P2, Q2);
	int O3 = Orientation(Q1, Q2, P1);
	int O4 = Orientation(Q1, Q2, P2);

	// 一般情况: Q1、Q2 位于 P1P2 的两侧, 且 P1、P2 位于 Q1Q2 的两侧, 则相交
	if (O1 != O2 && O3 != O4)
	{
		return true;
	}

	// 特殊情况 (共线且落在线段上): 处理端点重合或点在边上的边界情形
	if (O1 == 0 && OnSegment(P1, Q1, P2))
	{
		return true;
	}
	if (O2 == 0 && OnSegment(P1, Q2, P2))
	{
		return true;
	}
	if (O3 == 0 && OnSegment(Q1, P1, Q2))
	{
		return true;
	}
	if (O4 == 0 && OnSegment(Q1, P2, Q2))
	{
		return true;
	}

	// 以上条件都不满足, 则两线段不相交
	return false;
}

// 判断两个多边形的边是否存在相交
bool FGeometryUtils::DoPolygonsEdgesIntersect(const TArray<FVector2D>& A, const TArray<FVector2D>& B)
{
	const int32 NA = A.Num();
	const int32 NB = B.Num();

	// 遍历多边形 A 的每一条边
	for (int32 i = 0; i < NA; ++i)
	{
		const FVector2D& A_P1 = A[i];
		const FVector2D& A_P2 = A[(i + 1) % NA]; // 取模保证边闭合

		// 遍历多边形 B 的每一条边
		for (int32 j = 0; j < NB; ++j)
		{
			const FVector2D& B_P1 = B[j];
			const FVector2D& B_P2 = B[(j + 1) % NB]; // 取模保证边闭合

			// 只要有任意一对边相交, 即可判定两多边形的边相交
			if (DoLinesIntersect(A_P1, A_P2, B_P1, B_P2))
			{
				return true;
			}
		}
	}

	return false;
}

// 判断两个多边形是否重叠
bool FGeometryUtils::DoPolygonsOverlap(const TArray<FVector2D>& A, const TArray<FVector2D>& B)
{
	// 情况一: A 的任意顶点在 B 内部 (如 A 完全被 B 包含)
	for (const FVector2D& PointA : A)
	{
		if (IsPointInPolygon(PointA, B))
		{
			return true;
		}
	}

	// 情况二: B 的任意顶点在 A 内部 (如 B 完全被 A 包含)
	for (const FVector2D& PointB : B)
	{
		if (IsPointInPolygon(PointB, A))
		{
			return true;
		}
	}

	// 情况三: 两多边形的边相交 (部分重叠 / 相互穿插)
	if (DoPolygonsEdgesIntersect(A, B))
	{
		return true;
	}

	// 三种情况都不满足则不重叠
	return false;
}

#if !UE_BUILD_SHIPPING
// 调试用: 将 JSON 数组中的点逐个打印到日志
void FGeometryUtils::PrintJsonArrayPoints(const TArray<TSharedPtr<FJsonValue>>& JsonArray, const FString& ArrayName)
{
	// 打印数组名称作为日志开头
	UE_LOG(LogLQARestore, Log, TEXT("Print array %s:"), *ArrayName);

	// 遍历数组中的每个元素
	for (int32 i = 0; i < JsonArray.Num(); ++i)
	{
		const TSharedPtr<FJsonValue>& JsonValue = JsonArray[i];

		// 元素为空: 打印警告并跳过
		if (!JsonValue.IsValid())
		{
			UE_LOG(LogLQARestore, Warning, TEXT("  Index %d JsonValue is invalid"), i);
			continue;
		}

		// 尝试转换为 JSON 对象
		const TSharedPtr<FJsonObject> PointObj = JsonValue->AsObject();
		if (PointObj.IsValid())
		{
			double X = 0, Y = 0;
			// 同时读取到 x、y 字段才打印坐标, 否则提示字段缺失
			if (PointObj->TryGetNumberField(TEXT("x"), X) && PointObj->TryGetNumberField(TEXT("y"), Y))
			{
				UE_LOG(LogLQARestore, Log, TEXT("  Point[%d] : x = %.3f, y = %.3f"), i, X, Y);
			}
			else
			{
				UE_LOG(LogLQARestore, Warning, TEXT("  Point[%d] missing x or y field"), i);
			}
		}
		else
		{
			// 元素不是 JSON 对象
			UE_LOG(LogLQARestore, Warning, TEXT("  Point[%d] is not a Json object"), i);
		}
	}
}
#endif