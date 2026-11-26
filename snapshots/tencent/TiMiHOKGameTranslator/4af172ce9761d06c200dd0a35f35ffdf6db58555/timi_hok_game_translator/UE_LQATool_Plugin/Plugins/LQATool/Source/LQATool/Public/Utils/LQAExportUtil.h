#pragma once

#include "CoreMinimal.h"

// 前置声明, 避免在头文件中引入完整定义, 减少编译依赖
class FJsonObject;        // JSON 对象类, 用于序列化控件数据
class FLQAWidgetNode;     // LQA 控件树节点, 描述 UI 控件层级结构
class SWindow;            // Slate 窗口类
class UTexture;           // 纹理资源类
class UTexture2D;

/**
 * 控件数据与截图导出工具类
 * 提供控件树分析、JSON 序列化以及屏幕截图捕获等功能
 * 整个类均为静态方法 (无需实例化), 作为纯工具集合使用
 */
class FLQAExportUtil
{
public:
	// ========================================
	// 公共接口 —— 主要导出函数
	// ========================================

	/**
	 * 将当前激活窗口的控件视图以 “高级模式” 导出为 JSON
	 * @param CurDate         时间戳, 用于生成文件名 (保证唯一性)
	 * @param bContainsTextures 是否在导出数据中包含纹理数据
	 * @param bNeedObjectData   是否包含控件的对象元数据 (额外信息)
	 * @return 控件蓝图 (WidgetBlueprint) 名称
	 */
	static FString DumpViewAdvanced(const FDateTime& CurDate, bool bContainsTextures, bool bNeedObjectData);

	/**
	 * 提取当前视图中所有的文本类控件
	 * @return 文本控件对应的 JSON 对象数组
	 */
	static TArray<TSharedPtr<FJsonObject>> DumpText();

	/**
	 * 捕获屏幕截图
	 * @param CurDate 时间戳, 用于生成文件名
	 * @param WBPName 控件蓝图名称, 用于组织截图保存路径
	 */
	static void ScreenShot(const FDateTime& CurDate, const FString& WBPName);

	// ========================================
	// 公共接口 —— 交互相关函数
	// ========================================

	/** 处理鼠标按下事件 (根据点击位置查找对应的文本控件) */
	static void OnPointerDown(const FPointerEvent& MouseEvent);

	/**
	 * 查找所有包含指定屏幕坐标点的控件
	 * @param ClickPosition 屏幕坐标位置 (点击点)
	 * @param TextWidgets   待搜索的文本控件集合
	 * @param OutWidgets    输出参数, 命中的控件集合
	 * @return 若找到任意匹配控件则返回 true
	 */
	static bool FindAllWidgetsContainingPoint(const FVector2D& ClickPosition,
		const TArray<TSharedPtr<FJsonObject>>& TextWidgets, TArray<TSharedPtr<FJsonObject>>& OutWidgets);

	// ========================================
	// 公共接口 —— 通用工具函数
	// ========================================

	/** 获取系统当前的区域/语言 (Culture) 设置 */
	static FString GetCurrentCulture();

	/**
	 * 向 JSON 对象中追加系统元数据 (版本、设备、视口尺寸等)
	 * @param JsonObject 目标 JSON 对象
	 */
	static void AddSystemData(const TSharedPtr<FJsonObject>& JsonObject);

	/**
	 * 将快照数据保存到磁盘
	 * @param InJsonData 待保存的 JSON 字符串
	 * @param WBPName    控件蓝图名称, 用于生成保存路径与文件名
	 * @param CurDate    时间戳, 用于生成文件名
	 * @return 保存成功返回 true
	 */
	static bool SaveSnapshotData(const FString& InJsonData, const FString& WBPName, const FDateTime& CurDate);

private:
	// ========================================
	// 私有 —— 核心快照函数
	// ========================================

	/**
	 * 从指定窗口创建 “高级模式” 快照
	 * @param VisibleWindow     目标窗口
	 * @param CurDate           时间戳
	 * @param bContainsTextures 是否包含纹理数据
	 * @param bNeedObjectData   是否包含对象元数据
	 * @return 控件蓝图名称
	 */
	static FString CreateSnapshotAdvanced(const TSharedPtr<SWindow>& VisibleWindow, const FDateTime& CurDate,
		bool bContainsTextures, bool bNeedObjectData);

	/**
	 * 从名称列表中解析出控件蓝图名称
	 * @param NameList 待处理的控件名称列表
	 * @return 解析得到的蓝图名称
	 */
	static FString FindWBPName(TArray<FName>& NameList);

	/**
	 * Build the session directory that holds every artifact of one dump.
	 * @param CurDate Timestamp for directory naming
	 * @param WBPName Widget blueprint name
	 * @return Absolute path to the session directory
	 */
	static FString GetSnapshotDirectory(const FDateTime& CurDate, const FString& WBPName);

	/**
	 * Check whether a texture only exists in memory, i.e. it cannot be loaded back by path.
	 * @param Texture2D Texture to test
	 * @return true if the texture has no asset on disk backing it
	 */
	static bool IsRuntimeGeneratedTexture(const UTexture2D* Texture2D);

	/**
	 * Persist runtime-generated textures to disk as PNG, so they can be restored later.
	 * Textures already backed by an asset on disk are skipped, since those can be loaded by path.
	 * Files are named after the texture's nameMD5 and written to <SessionDir>/Textures.
	 * @param SharedTextureMap Texture cache collected during the dump
	 * @param CurDate Timestamp for directory naming
	 * @param WBPName Widget blueprint name
	 */
	static void ExportSharedTextures(
		const TMap<FString, UTexture*>& SharedTextureMap, const FDateTime& CurDate, const FString& WBPName);

	// ========================================
	// 私有 —— 控件树遍历处理
	// ========================================

	/**
	 * 递归收集控件树中所有有效节点 (UserWidget 类型且未被排除)
	 * @param Node          根节点 (遍历起点)
	 * @param OutValidNodes 输出参数, 收集到的有效节点
	 */
	static void GetAllValidNodes(
		const TSharedPtr<FLQAWidgetNode>& Node, TArray<TSharedPtr<FLQAWidgetNode>>& OutValidNodes);

	/**
	 * 递归收集控件树中所有文本节点, 并转换为 JSON
	 * @param Node              根节点 (遍历起点)
	 * @param OutValidTextNodes 输出参数, 文本节点对应的 JSON 对象
	 */
	static void GetAllTextNodes(
		const TSharedPtr<FLQAWidgetNode>& Node, TArray<TSharedPtr<FJsonObject>>& OutValidTextNodes);

	// ========================================
	// 私有 —— 节点序列化
	// ========================================

	/**
	 * 将单个控件节点序列化为 JSON (根据节点类型分发到不同处理函数)
	 * @param Node             控件节点
	 * @param SharedTextureMap 纹理缓存 (去重复用纹理)
	 * @param NameList         名称跟踪列表
	 * @param bNeedObjectData  是否包含对象元数据
	 * @param ParentName       父控件名称
	 * @return 序列化得到的 JSON 对象
	 */
	static TSharedPtr<FJsonObject> DumpNodeInfo(const TSharedPtr<FLQAWidgetNode>& Node,
		TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData,
		const FName ParentName = FName());

	/** 处理 UserWidget (用户控件) 类型节点的序列化 */
	static TSharedPtr<FJsonObject> HandleUserWidget(const TSharedPtr<FLQAWidgetNode>& Node,
		TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData,
		const FName ParentName = FName());

	/** 处理 Undefined (未定义) 类型节点的序列化 */
	static TSharedPtr<FJsonObject> HandleUndefinedWidget(const TSharedPtr<FLQAWidgetNode>& Node,
		TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData,
		const FName ParentName = FName());

	/** 处理其他 (普通) 类型节点的序列化 */
	static TSharedPtr<FJsonObject> HandleOtherWidget(const TSharedPtr<FLQAWidgetNode>& Node,
		TMap<FString, UTexture*>& SharedTextureMap, TArray<FName>& NameList, bool bNeedObjectData,
		const FName ParentName = FName());

	/**
	 * 处理子节点并将其序列化结果追加到父 JSON 对象中
	 * @param Node             父节点
	 * @param ParentJsonObject 父 JSON 对象
	 * @param SharedTextureMap 纹理缓存
	 * @param NameList         名称跟踪列表
	 * @param bNeedObjectData  是否包含对象元数据
	 * @param ParentName       父控件名称
	 */
	static void ProcessChildNodes(const TSharedPtr<FLQAWidgetNode>& Node,
		const TSharedPtr<FJsonObject>& ParentJsonObject, TMap<FString, UTexture*>& SharedTextureMap,
		TArray<FName>& NameList, bool bNeedObjectData, const FName ParentName = FName());

	// ========================================
	// 私有 —— 截图相关函数
	// ========================================

	/**
	 * 生成截图文件的完整保存路径
	 * @param CurDate 时间戳
	 * @param WBPName 控件蓝图名称
	 * @return 完整文件路径
	 */
	static FString GetScreenShotFileName(const FDateTime& CurDate, const FString& WBPName);

	/**
	 * 发起截图捕获流程 (先截前景图, 延迟后再截背景图)
	 * @param InScreenshotPath 目标文件路径
	 */
	static void StartScreenshotSequence(const FString& InScreenshotPath);

private:
	/** 前景截图文件路径 (静态成员, 供截图回调使用) */
	static FString ScreenshotPath;

	/** 背景截图文件路径 (静态成员, 供延迟截图回调使用) */
	static FString BgScreenshotPath;
};