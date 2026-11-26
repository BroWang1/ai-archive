// Copyright Epic Games, Inc. All Rights Reserved.

// 引入 UnrealBuildTool 命名空间, 该工具 (UBT) 负责解析本构建脚本并生成编译配置
using UnrealBuildTool;

// LQARestore 模块的构建规则类, 必须继承自 ModuleRules
// 类名需要与模块名、以及 .Build.cs 文件名保持一致
public class LQARestore : ModuleRules
{
	// 构造函数, UBT 会在解析模块时调用它
	// Target 参数描述了当前的编译目标信息 (平台、配置、类型等), 为只读规则
	public LQARestore(ReadOnlyTargetRules Target) : base(Target)
	{
		// 设置预编译头 (PCH) 的使用方式
		// UseExplicitOrSharedPCHs 表示使用显式或共享的 PCH, 是现代 UE 推荐的方式, 可提升编译速度
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		// 公有依赖模块: 这些模块会同时暴露给依赖本模块的其他模块
		// 即其他模块引用 LQARestore 时, 也能间接访问这些依赖的头文件
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",         // UE 核心基础库 (容器、字符串、数学等), 几乎所有模块都需要
			"MediaAssets"   // 媒体资源模块, 用于处理媒体播放器、媒体纹理等资源
		});

		// 私有依赖模块: 仅本模块内部使用, 不会传递给依赖本模块的其他模块
		// 这样可以减少不必要的依赖传播, 加快编译并降低耦合
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"CoreUObject",      // UObject 对象系统 (反射、GC、序列化等)
			"Engine",           // 引擎核心功能 (Actor、World、组件等)
			"Slate",            // Slate UI 框架 (界面控件)
			"SlateCore",        // Slate UI 核心组件 (底层绘制与基础类型)
			"UMG",              // 控件蓝图 (Unreal Motion Graphics, 基于 Slate 的可视化 UI)
			"Settings",         // 项目设置模块 (注册自定义配置页）)
			"Json",             // JSON 解析 (底层读写)
			"JsonUtilities",    // JSON 工具库 (结构体与 JSON 的互转等便捷功能)
			"ImageWrapper",     // 图像编解码 (PNG 解码, 用于还原运行时生成的纹理)
			"RHI",              // 渲染硬件接口 (Render Hardware Interface)
			"RenderCore",       // 渲染核心功能
			"ImageCore",        // 图像核心类型 (FImage/FImageView, CompressImage 的输入)
			"HTTP",             // HTTP 网络请求模块
			"Paper2D",          // 2D 渲染 (精灵 Sprite、Flipbook 等)
			"InputCore",        // 输入处理 (按键、轴映射等基础输入类型)
			"zlib",             // zlib 压缩库 (数据压缩/解压)
			"Projects"          // 项目/插件管理模块 (提供 IPluginManager 等接口)
		});

		// 仅当编译目标为编辑器 (Editor) 时才添加 UnrealEd 依赖
		// UnrealEd 包含大量编辑器专用功能, 若在打包的游戏运行时版本中引用会导致编译/链接错误
		if (Target.Type == TargetType.Editor)
		{
			PrivateDependencyModuleNames.Add("UnrealEd");    // 编辑器核心模块
		}

		// 公有预处理宏定义: 会暴露给依赖本模块的其他模块
		// 代码中可通过 #if WITH_LQA_RESTORE_TOOL_ENABLED 进行条件编译, 控制 LQA 还原工具功能的开关
		PublicDefinitions.Add("WITH_LQA_RESTORE_TOOL_ENABLED=1");
	}
}