// ==========================================
// 文件: LQATool\Core\LQATool.cs
// 模块: Core (核心)
// ==========================================

using UnityEngine;

/// <summary>
/// LQATool 核心层命名空间
/// </summary>
namespace LQATool.Core
{
    /// <summary>
    /// LQATool 的对外静态入口 (门面/Facade)
    ///
    /// 职责: 作为整个插件的 "总开关" 与自启动入口, 负责:
    ///   1. 在游戏运行时自动创建常驻的 [LQATool_Manager] 游戏对象 (无需手动挂载到场景)
    ///   2. 根据 PlayerPrefs 配置决定工具默认是否启用
    ///   3. 对外暴露 SetEnable 接口, 供业务代码在运行时动态开启/关闭工具
    ///
    /// 设计要点: 本类只做 "创建管理器 + 开关" 这类轻量协调工作, 具体逻辑全部委托给
    /// LQAToolManager (真正的中枢), 从而让调用方无需感知内部实现细节
    /// </summary>
    public static class LQATool
    {
        /// <summary>
        /// 核心管理器 (LQAToolManager) 的单例引用
        /// 由 AutoInit() 在运行时创建并缓存, 用作是否已初始化的判断依据, 避免重复创建
        /// </summary>
        private static LQAToolManager _instance;

        /// <summary>
        /// 自动初始化入口
        ///
        /// 借助 [RuntimeInitializeOnLoadMethod] 特性, 由 Unity 在 "首个场景加载完成后"
        /// (AfterSceneLoad) 自动调用, 因此无需在任何场景里手动挂载脚本即可让工具生效
        /// </summary>
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void AutoInit()
        {
            // 幂等保护: 仅当尚未初始化时才创建, 防止重复生成管理器对象
            if (_instance == null)
            {
                // 1. 创建承载工具的游戏对象 (名称加方括号便于在 Hierarchy 中辨识)
                GameObject go = new GameObject("[LQATool_Manager]");

                // 2. 标记为跨场景常驻, 切换场景时不会被销毁, 保证工具全程可用
                GameObject.DontDestroyOnLoad(go);

                // 3. 挂载核心管理器组件, 由它去创建/连线 UI、输入、Dump 等各子模块
                _instance = go.AddComponent<LQAToolManager>();

                // 4. 读取本地配置, 决定工具默认是否启用 (缺省为 0, 即默认不启用)
                bool shouldEnable = PlayerPrefs.GetInt("LQA_ShowDumpAndGetNodeButtons", 0) == 1;
                if (!shouldEnable)
                {
                    // 配置为禁用时: 关闭整个对象 (连带其上的管理器一起停止工作)
                    go.SetActive(false);
                    Debug.Log("[LQATool] 工具已按 PlayerPrefs 配置禁用 (LQA_ShowDumpAndGetNodeButtons=0)");
                }
            }
        }

        /// <summary>
        /// 运行时动态开启/关闭工具
        /// 通过启用或禁用管理器所在的游戏对象来实现整体开关
        /// </summary>
        /// <param name="enable">true 表示启用工具, false 表示禁用工具</param>
        public static void SetEnable(bool enable)
        {
            // 仅在已完成自动初始化 (_instance 存在) 时才操作, 避免空引用
            if (_instance != null)
            {
                _instance.gameObject.SetActive(enable);
            }
        }
    }
}