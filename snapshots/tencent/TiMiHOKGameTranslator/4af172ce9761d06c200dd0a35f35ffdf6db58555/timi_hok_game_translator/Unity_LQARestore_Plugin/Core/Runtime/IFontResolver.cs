// ==========================================
// 文件: LQARestore\Core\Runtime\IFontResolver.cs
// 模块: Core (核心层)
// ==========================================

using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 字体解析抽象: 把 dump 数据里的 "字体引用信息" 转换成一个可用于渲染的 Font 实例
    /// 为什么要抽象成接口:
    ///   字体的查找方式与运行环境强相关, 而还原流程 (TextNodeBuilder等) 不应关心这些差异
    ///   通过接口把 "如何找到字体" 与 "如何使用字体" 解耦:
    ///     - Editor 环境: 由 EditorFontResolver 实现, 依赖 AssetDatabase,
    ///       既可按 assetPath/guid 精确加载, 也可在 assetPath/guid 缺失时按字体名在工程内反查
    ///     - 将来若需要 Runtime (真机运行时无 AssetDatabase) 版本: 可另写实现,
    ///       改走 Resources / Addressables 等运行期可用的加载方式
    /// </summary>
    public interface IFontResolver
    {
        /// <summary>
        /// 根据 dump 中的字体引用信息解析出对应的 Font
        /// </summary>
        /// <param name="fontRef">
        /// dump 里的 "font" 字典, 通常包含以下键 (均可能缺失):
        ///   - "name" —— 字体名 (如 "Arial" 或 "xxx.ttf");
        ///   - "assetPath" —— 工程内资源路径, 用于精确加载;
        ///   - "guid" —— 资源 GUID
        /// 说明: Editor 采集的 dump 一般带有 assetPath/guid, 可精确定位;
        ///       Android 真机采集时因无 AssetDatabase，assetPath/guid 均为 null,
        ///       此时只能依赖 "name" 在工程内按名反查
        /// 整个字典本身也可能为 null (例如 dump 未记录字体信息)
        /// </param>
        /// <returns>
        /// 解析成功返回对应的 Font
        /// 当 fontRef 为 null、信息不足或工程内查无此字体时返回 null
        /// 调用方需自行处理 null (通常回退到内置默认字体, 注意中文可能显示为方块)
        /// </returns>
        Font Resolve(Dictionary<string, object> fontRef);
    }
}