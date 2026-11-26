// ==========================================
// 文件: LQATool\Core\LQAToolManager.cs
// 模块: Core (核心)
// ==========================================

using System.Collections;
using UnityEngine;
using LQATool.UI;
using LQATool.Input;
using LQATool.Services;

/// <summary>
/// LQATool 核心层命名空间
/// </summary>
namespace LQATool.Core
{
    /// <summary>
    /// LQATool 的核心管理器 (总协调者), 挂载在场景中的 [LQATool_Manager] 游戏对象上
    /// 
    /// 职责: 作为整个插件的 "中枢", 负责:
    ///   1. 创建并持有三大模块: UI 管理器 (UI 层)、输入检测器 (Input 层)、Dump 服务 (Services 层)
    ///   2. 把各模块之间的事件 "连线" (订阅/转发), 让彼此解耦的模块协同工作
    ///   3. 监听全局热键 (F9), 提供除 UI 按钮之外的快捷触发入口
    /// 
    /// 设计要点: 各模块之间互不直接引用, 全部通过本类订阅事件来通信, 从而保持低耦合
    /// </summary>
    public class LQAToolManager : MonoBehaviour
    {
        // ==========================================
        // 模块引用 (私有字段) —— 三大子模块由本类创建并持有
        // ==========================================

        /// <summary>
        /// UI 管理器 (UI 层): 负责构建/显示工具面板、Dump 按钮、GetNode 按钮及信息展示面板
        /// 在 Start() 中通过 AddComponent 动态挂载到同一游戏对象上
        /// </summary>
        private LQAToolUIManager _uiManager;

        /// <summary>
        /// 输入检测器 (Input 层): 每帧检测鼠标/触摸的 [按下] 与 [长按] 手势, 并通过事件对外通知
        /// 在 Start() 中通过 AddComponent 动态挂载到同一游戏对象上
        /// </summary>
        private InputDetector _inputDetector;

        /// <summary>
        /// UI Dump 服务 (Services 层): 负责执行完整的 UI 转储流程 (截图 + 生成节点树 JSON),
        /// 以及长按时的单节点信息查找 (FindNearestTextNode)
        /// 注意: 它是普通类 (非 MonoBehaviour), 通过 new 直接实例化
        /// </summary>
        private UIDumpService _dumpService;

        /// <summary>
        /// Dump 执行中的互斥标记, 防止在一次 Dump 尚未完成时被重复触发 (按钮连点 / 热键连按)
        /// true 表示当前正有一次 Dump 协程在运行
        /// </summary>
        private bool _isDumping = false;

        /// <summary>
        /// Dump 前的延时秒数配置 Key (由客户端 GM 面板写入, 整数, 默认 0 表示立即 Dump)
        /// </summary>
        private const string DumpDelayPrefsKey = "LQA_DumpDelaySeconds";

        /// <summary>
        /// 触发 UI Dump 的全局热键 (F9), 作为 UI 按钮之外的快捷入口 (主要方便 PC 端调试)
        /// </summary>
        private const KeyCode DumpHotKey = KeyCode.F9;

        /// <summary>
        /// Unity 生命周期方法: 在对象启用后的第一帧调用一次
        /// 负责创建三大模块并建立它们之间的事件连线
        /// </summary>
        void Start()
        {
            // 1. 创建 Dump 服务 (普通类, 直接 new)
            _dumpService = new UIDumpService();

            // 2. 动态挂载 UI 管理器组件, 并初始化 (构建工具 UI、确保 EventSystem 存在)
            _uiManager = gameObject.AddComponent<LQAToolUIManager>();
            _uiManager.Initialize();

            // 3. 动态挂载输入检测器组件 (默认处于关闭状态, 需由 GetNode 开关开启)
            _inputDetector = gameObject.AddComponent<InputDetector>();

            // ==========================================
            // 4. 事件连线 (把彼此解耦的模块串联起来)
            // ==========================================

            // 点击 UI 上的 Dump 按钮 → 触发一次 UI 转储
            _uiManager.OnDumpClicked += HandleDumpRequest;

            // 切换 UI 上的 GetNode 开关 → 同步开启/关闭输入检测器的长按检测
            _uiManager.OnGetNodeToggled += _inputDetector.SetEnable;

            // 指针再次按下屏幕 → 先隐藏上一次弹出的信息面板 (避免旧面板残留)
            _inputDetector.OnPointerDown += _uiManager.HideInfoPanel;

            // 长按屏幕触发 → 查找该位置最近的文本节点并弹出信息面板
            _inputDetector.OnLongPressTriggered += HandleGetNodeRequest;
        }

        /// <summary>
        /// Unity 生命周期方法: 每帧调用
        /// 仅用于监听全局热键, 提供 UI 按钮之外的 Dump 触发方式
        /// </summary>
        void Update()
        {
            // 按下 F9 → 等同于点击 Dump 按钮
            if (UnityEngine.Input.GetKeyDown(DumpHotKey))
            {
                HandleDumpRequest();
            }
        }

        /// <summary>
        /// 处理 GetNode 请求 (由 InputDetector 的长按事件 OnLongPressTriggered 触发)
        /// 根据长按位置查找最近的文本节点, 并在 UI 上弹出该节点的信息面板
        /// </summary>
        /// <param name="pointerPosition">长按发生时指针在屏幕上的坐标</param>
        private void HandleGetNodeRequest(Vector2 pointerPosition)
        {
            // 在工具画布之外的 UI 中, 查找离长按点最近的文本节点
            var nearestTextNode = _dumpService.FindNearestTextNode(pointerPosition, _uiManager.ToolCanvas);

            // 把查到的节点信息交给 UI 层显示 (面板位置参考长按坐标)
            _uiManager.ShowNodeInfo(nearestTextNode, pointerPosition);
        }

        /// <summary>
        /// 处理 Dump 请求 (由 UI 的 Dump 按钮点击, 或 F9 热键触发)
        /// 先按 GM 配置的延时秒数等待 (默认 0 即立即执行), 再启动一次完整的 UI 转储协程
        /// _isDumping 标记在延时开始前就置位, 防止倒计时期间被重复触发
        /// </summary>
        private void HandleDumpRequest()
        {
            // 互斥保护: 若上一次 Dump 尚未结束 (包含延时等待中), 直接忽略本次请求, 防止重复执行
            if (_isDumping) return;
            _isDumping = true;

            int delaySeconds = PlayerPrefs.GetInt(DumpDelayPrefsKey, 0);
            StartCoroutine(RunDumpWithDelay(delaySeconds));
        }

        /// <summary>
        /// 按延时秒数等待后执行真正的 Dump 流程 (delaySeconds <= 0 时不等待, 行为与之前一致)
        /// </summary>
        private IEnumerator RunDumpWithDelay(int delaySeconds)
        {
            if (delaySeconds > 0)
            {
                Debug.Log($"[LQATool] Dump 将在 {delaySeconds} 秒后开始采集...");
                yield return new WaitForSecondsRealtime(delaySeconds);
            }

            // 启动转储协程, 完成回调 (onComplete) 中把 _isDumping 复位为 false, 允许下一次触发
            yield return _dumpService.ExecuteDump(_uiManager.ToolCanvas, () => _isDumping = false);
        }
    }
}