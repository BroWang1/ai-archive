// ==========================================
// 文件: LQATool\UI\LQAToolUIManager.EventSystem.cs
// 模块: UI (用户界面)
// ==========================================

using UnityEngine;
using UnityEngine.EventSystems;

/// <summary>
/// LQATool 用户界面层命名空间
/// </summary>
namespace LQATool.UI
{
    /// <summary>
    /// 分部类: 本文件仅实现与 EventSystem 相关的逻辑,
    /// 字段 _fallbackEventSystem 及生命周期入口 Initialize() 定义在 LQAToolUIManager.cs 中
    /// </summary>
    public partial class LQAToolUIManager
    {
        /// <summary>
        /// Unity 生命周期方法, 每帧调用一次
        /// 作用: 监测宿主游戏是否已经动态生成了自己的 EventSystem
        ///       由于插件的备用 EventSystem 只是 "兜底" 手段, 一旦游戏自身有了 EventSystem,
        ///       就必须销毁备用实例, 否则场景中同时存在多个 EventSystem 会触发 Unity 警告并导致输入行为异常
        /// 备注: 仅在 _fallbackEventSystem 不为空 (即当前确实存在插件创建的备用实例) 时才需要检测,
        ///       销毁后 _fallbackEventSystem 置空, 后续帧不再进入检测逻辑, 几乎无额外开销
        /// </summary>
        private void Update()
        {
            // 仅当插件持有备用 EventSystem 时才需要监测冲突, 否则直接跳过
            if (_fallbackEventSystem != null)
            {
                // 获取当前 Unity 认定为激活状态的 EventSystem
                var currentES = EventSystem.current;

                // 若当前激活的 EventSystem 存在, 且不是插件自己创建的那个,
                // 说明宿主游戏已经生成了属于自己的 EventSystem
                if (currentES != null && currentES != _fallbackEventSystem)
                {
                    // 销毁插件的备用 EventSystem 所在的 GameObject, 避免与游戏的 EventSystem 冲突
                    Destroy(_fallbackEventSystem.gameObject);

                    // 清空引用, 使后续帧的 Update 不再进入此分支
                    _fallbackEventSystem = null;

                    Debug.Log("[LQATool][LQAToolUIManager] 检测到游戏动态生成了 EventSystem (事件系统), 插件已自动销毁备用 EventSystem (事件系统) 以避免冲突");
                }
            }
        }

        /// <summary>
        /// 确保当前场景中存在可用的 EventSystem
        /// 调用时机: 由 Initialize() (定义于 LQAToolUIManager.cs) 在 UI 构建完成后调用
        /// 逻辑:
        ///   1. 先在所有已加载对象中查找是否已存在 EventSystem, 存在则直接复用, 不重复创建;
        ///   2. 若不存在, 则新建一个挂载 EventSystem + StandaloneInputModule 的备用对象,
        ///      并将其引用记录到 _fallbackEventSystem, 供 Update() 后续监测与销毁;
        /// 原因: UGUI 的所有指针/点击事件都依赖场景中存在 EventSystem, 缺失时工具按钮将无法响应
        /// </summary>
        private void EnsureEventSystem()
        {
            // 查找工程中所有 EventSystem 对象 (包含未激活对象, 因此需进一步判断是否属于已加载场景)
            var existingES = Resources.FindObjectsOfTypeAll<EventSystem>();

            foreach (var es in existingES)
            {
                // 仅当该 EventSystem 属于已加载的场景时才视为有效
                // (可排除预制体资源、未加载场景中的对象等误判)
                if (es.gameObject.scene.isLoaded)
                {
                    Debug.Log("[LQATool][LQAToolUIManager] 检测到已存在的 EventSystem (事件系统), 不需要重复创建");

                    // 已有可用的 EventSystem, 无需创建备用实例, 直接返回
                    return;
                }
            }

            // 走到这里说明场景中没有可用的 EventSystem, 需要创建一个备用实例
            GameObject esObj = new GameObject("LQATool_EventSystem");
            // 挂到当前管理器对象下, 使其生命周期跟随插件, 便于统一管理与清理
            esObj.transform.SetParent(this.transform);
            // 添加 EventSystem 组件并记录引用, 供 Update() 监测冲突与后续销毁
            _fallbackEventSystem = esObj.AddComponent<EventSystem>();
            // 添加标准输入模块, 负责将鼠标/触摸等输入转发给 UGUI 事件系统
            esObj.AddComponent<StandaloneInputModule>();

            Debug.Log("[LQATool][LQAToolUIManager] 未检测到 EventSystem (事件系统), 创建备用的 EventSystem (事件系统)");
        }
    }
}