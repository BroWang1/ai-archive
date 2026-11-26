// ==========================================
// 文件: LQARestore\Core\Runtime\NodePostProcessors.cs
// 模块: Core (核心层)
// ==========================================

using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 节点后处理器委托: 定义 "对单个还原节点做附加处理" 的统一签名
    /// 触发时机: 在 TextNodeBuilder 完成通用组件 (Text / Canvas / RectTransform) 还原后,
    /// 由 NodePostProcessors 逐一回调所有已注册的后处理器, 对该节点做附加还原 (如项目专属特效)
    /// 对称设计: 与采集侧 ComponentExtractors 的注册表模式相对应 ——
    ///   采集侧负责 "把组件属性抽取成 JSON", 还原侧则负责 "把 JSON 还原回组件/特效"
    /// </summary>
    /// <param name="go">已完成通用还原的节点 GameObject</param>
    /// <param name="objectData">该节点从 JSON 反序列化得到的属性字典, 供后处理器读取所需数据</param>
    internal delegate void NodePostProcessor(GameObject go, Dictionary<string, object> objectData);

    /// <summary>
    /// 节点后处理器的注册中心
    /// 职责:
    ///   - 维护一张已注册后处理器的列表;
    ///   - 提供 ApplyAll: 对某个已完成通用还原的节点, 依次执行所有后处理器;
    /// 设计要点:
    ///   - 采用注册表模式, 新增一类附加还原只需 Register, 无需改动 ApplyAll 遍历逻辑;
    ///   - 通用还原 (Text / Canvas / RectTransform) 由 TextNodeBuilder 直接完成, 无需在此注册;
    ///   - 项目专属还原 (对应采集侧的项目专属组件) 由 ProjectCustomRestorers 挂入, 与本类解耦;
    ///   - 声明为 static, 全局只有一份注册表, 由静态构造函数在首次访问时初始化一次;
    /// </summary>
    internal static class NodePostProcessors
    {
        // ==========================================
        // 注册表存储
        // ==========================================

        /// <summary>
        /// 全局注册表, 存放所有已登记的后处理器, 由静态构造填充后按注册顺序遍历执行
        /// </summary>
        private static readonly List<NodePostProcessor> _processors = new List<NodePostProcessor>();

        // ==========================================
        // 静态构造: 注册所有后处理器
        // ==========================================

        /// <summary>
        /// 静态构造函数, 在本类被首次访问时由 CLR 自动调用一次
        /// 负责挂入项目专属还原器 (对称于采集侧 ComponentExtractors 的静态构造)
        /// </summary>
        static NodePostProcessors()
        {
            // 对称采集侧: 通用还原无需注册; 项目专属还原在此挂入
            ProjectCustomRestorers.RegisterAll();
        }

        // ==========================================
        // 注册辅助方法
        // ==========================================

        /// <summary>
        /// 注册一个后处理器, 供 ProjectCustomRestorers 等在初始化时挂入附加还原逻辑
        /// </summary>
        /// <param name="processor">待注册的后处理器 (为 null 时静默忽略)</param>
        internal static void Register(NodePostProcessor processor)
        {
            if (processor != null) _processors.Add(processor);
        }

        // ==========================================
        // 公开 API: 供 TextNodeBuilder 调用
        // ==========================================

        /// <summary>
        /// 对给定节点依次执行所有已注册的后处理器
        /// 由还原流程在完成该节点的通用组件还原后调用一次
        /// </summary>
        /// <param name="go">已完成通用还原的节点 GameObject</param>
        /// <param name="objectData">该节点的属性字典, 转发给每个后处理器读取</param>
        internal static void ApplyAll(GameObject go, Dictionary<string, object> objectData)
        {
            // 逐条执行注册表: 用 for 而非 foreach, 避免枚举器分配, 同时明确按注册顺序执行
            for (int i = 0; i < _processors.Count; i++)
            {
                try { _processors[i](go, objectData); }
                catch (Exception e)
                {
                    // 单个后处理器失败不应中断整棵树的还原, 记一条警告后继续处理其余后处理器
                    var name = go != null ? go.name : "<null>";
                    Debug.LogWarning($"[LQARestore][NodePostProcessors] {name} 后处理失败: {e.Message}");
                }
            }
        }
    }
}