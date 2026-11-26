// 引入 UnrealBuildTool 命名空间, 该命名空间提供了 ModuleRules 等编译系统所需的类型
using UnrealBuildTool;

// LQATool 模块的构建规则类, 继承自 ModuleRules
// UBT (Unreal Build Tool) 在编译时会读取此类来决定该模块如何编译、依赖哪些其他模块
public class LQATool : ModuleRules
{
	// 构造函数: 接收目标平台/配置的只读规则 (Target), 用于初始化本模块的编译设置
	public LQATool(ReadOnlyTargetRules Target) : base(Target)
	{
		// 设置预编译头 (PCH) 的使用模式
		// UseExplicitOrSharedPCHs: 使用显式指定的 PCH 或引擎共享的 PCH, 可加快编译速度 (UE 推荐设置)
		PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

		// 公有依赖模块: 这些模块会同时暴露给依赖本模块的其他模块
		// 此处为实现基础功能所必需的核心引擎模块
		PublicDependencyModuleNames.AddRange(new string[]
		{
			"Core",         // UE 核心基础库 (容器、字符串、数学、文件 IO 等)
			"CoreUObject",  // UObject 反射与对象系统 (UClass、序列化、GC 等)
			"Engine"        // 引擎运行时核心 (Actor、World、组件等游戏框架)
		});

		// 私有依赖模块: 仅本模块内部使用, 不会向外部模块暴露
		// 说明: 这是基础配置, 可按项目需要额外添加特定的 UI Widget 模块
		PrivateDependencyModuleNames.AddRange(new string[]
		{
			"Slate",          // Slate UI 框架 (底层 UI 控件系统)
			"SlateCore",      // Slate 核心功能 (基础绘制、布局、输入等)
			"UMG",            // 控件蓝图 (Unreal Motion Graphics, 可视化 UI)
			"Json",           // JSON 解析 (序列化/反序列化 JSON 数据)
			"JsonUtilities",  // JSON 辅助函数 (UStruct 与 JSON 互转等便捷工具)
			"HTTP",           // 网络请求 (发送 HTTP 请求与接收响应)
			"RHI",            // 渲染硬件接口 (Rendering Hardware Interface, 抽象底层图形 API)
			"RenderCore",     // 核心渲染功能 (渲染线程、渲染资源管理等)
			"Paper2D",        // 2D 精灵支持 (Sprite、Flipbook 等 2D 内容)
			"InputCore",      // 输入处理 (按键、鼠标等输入事件定义)
			"ImageWrapper"    // 图像格式支持 (PNG/JPEG/BMP 等图片的编解码)
		});
	}
}