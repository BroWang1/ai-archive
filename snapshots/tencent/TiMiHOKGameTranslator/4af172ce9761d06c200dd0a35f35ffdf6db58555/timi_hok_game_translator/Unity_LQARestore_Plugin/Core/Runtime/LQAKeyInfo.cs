// ==========================================
// 文件: LQARestore\Core\Runtime\LQAKeyInfo.cs
// 模块: Core (核心层)
// ==========================================

using UnityEngine;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 本地化 Key 说明组件 (还原侧轻量数据载体)
    /// 职责: 在还原出的可编辑 UGUI 文本对象上, 携带采集侧从 XxxxLocalize 反射读到的 keyHash,
    ///       使本地化/翻译人员在还原场景中选中该文本时, 能在 Inspector 直接看到其对应的本地化 key
    /// 设计要点:
    ///   - 不还原原工程的 XxxxLocalize 组件本身 (类型不在本还原工程引用范围内, 且还原环境无本地化配置表,
    ///     挂上去也不会驱动出任何效果), 仅把 keyHash 作为 "数据" 还原出来, 与 XxxxText 用内置 Outline/Shadow
    ///     近似其视觉、而不还原组件本身的取舍一致;
    ///   - 纯数据组件, 无任何运行逻辑
    /// </summary>
    public class LQAKeyInfo : MonoBehaviour
    {
        /// <summary>
        /// 采集侧从 XxxxLocalize.keyHash 反射读到的本地化 key (原样字符串, 可能是十六进制哈希或原文 key)
        /// </summary>
        public string keyHash;
    }
}