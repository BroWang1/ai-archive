// ==========================================
// 文件: LQATool\UI\LQAToolUIManager.cs
// 模块: UI (用户界面)
// ==========================================

using System;
using UnityEngine;
using UnityEngine.UI;
using UnityEngine.EventSystems;

/// <summary>
/// LQATool 用户界面层命名空间
/// </summary>
namespace LQATool.UI
{
    /// <summary>
    /// LQAToolUIManager: 整个 LQA 工具悬浮 UI 的核心管理器 (MonoBehaviour)
    /// 
    /// 本类被拆分为 4 个分部文件, 各司其职:
    ///   - LQAToolUIManager.cs (本文件) 声明全部字段、对外事件/属性, 以及生命周期入口与开关逻辑
    ///   - LQAToolUIManager.Builder.cs 负责用纯代码动态构建 UI 树 (Canvas / 按钮 / 信息面板)
    ///   - LQAToolUIManager.Display.cs 负责信息面板的内容填充与定位
    ///   - LQAToolUIManager.EventSystem.cs 负责保证场景中存在可用的 EventSystem
    /// 
    /// 设计说明: 本类只负责 "UI 表现与交互", 不直接处理业务逻辑;
    ///           通过 OnDumpClicked / OnGetNodeToggled 事件把用户操作向外广播, 由上层订阅者处理;
    /// </summary>
    public partial class LQAToolUIManager : MonoBehaviour
    {
        /// <summary>
        /// 点击 Dump 按钮时触发的事件, 由外部订阅者负责实际的 Dump 逻辑
        /// (在 Builder 中绑定到按钮的 onClick 上)
        /// </summary>
        public Action OnDumpClicked;

        /// <summary>
        /// GetNode 开关状态切换时触发的事件
        /// 参数 bool: 切换后的开关状态 (true = 开启节点拾取, false = 关闭)
        /// </summary>
        public Action<bool> OnGetNodeToggled;

        /// <summary>
        /// 工具 UI 的根画布, 在 Builder 中创建并缓存
        /// (对外通过只读属性 ToolCanvas 暴露, 供 Dump 时临时隐藏工具 UI 等场景使用)
        /// </summary>
        private Canvas _canvas;

        /// <summary>
        /// GetNode 按钮上的文字组件, 缓存以便 ToggleGetNode() 切换文字/颜色时复用, 避免重复查找
        /// </summary>
        private Text _txtGetNode;

        /// <summary>
        /// 长按节点信息展示面板的根对象, 在 Builder 中预创建并默认隐藏
        /// </summary>
        private GameObject _infoPanel;

        /// <summary>
        /// 信息面板内用于显示节点详情的富文本组件 (由 Display 分部填充内容)
        /// </summary>
        private Text _infoText;

        /// <summary>
        /// GetNode 开关的当前状态: true = 开启节点拾取, false = 关闭
        /// </summary>
        private bool _isGetNodeOn = false;

        /// <summary>
        /// 插件创建的备用 EventSystem 引用 (仅在场景原本缺失 EventSystem 时才会被创建)
        /// 由 EventSystem 分部创建/监测/销毁, 详见 EnsureEventSystem() 与 Update()
        /// </summary>
        private EventSystem _fallbackEventSystem;

        /// <summary>
        /// 对外只读暴露工具画布, 供外部 (如 Dump 流程) 访问以临时控制工具 UI 的显隐
        /// </summary>
        public Canvas ToolCanvas => _canvas;

        /// <summary>
        /// 管理器初始化入口, 由外部在创建本组件后调用
        /// 流程: 先构建整套工具 UI, 再确保场景中存在可用的 EventSystem (否则 UI 无法响应点击)
        /// </summary>
        public void Initialize()
        {
            // 动态构建 Canvas / 按钮 / 信息面板 (定义于 Builder 分部)
            CreateToolUI();
            // 确保场景存在 EventSystem, 缺失则创建备用实例 (定义于 EventSystem 分部)
            EnsureEventSystem();
        }

        /// <summary>
        /// 隐藏节点信息面板 (做空判断, 面板未创建时安全返回)
        /// 供内部关闭 GetNode 时调用, 也可由外部主动隐藏
        /// </summary>
        public void HideInfoPanel()
        {
            if (_infoPanel != null) _infoPanel.SetActive(false);
        }

        /// <summary>
        /// 切换 GetNode 开关状态 (绑定到 GetNode 按钮的点击事件)
        /// 副作用: 同步更新按钮文字与颜色, 关闭时隐藏信息面板, 并向外广播 OnGetNodeToggled 事件
        /// </summary>
        private void ToggleGetNode()
        {
            // 翻转开关状态
            _isGetNodeOn = !_isGetNodeOn;
            // 按钮文字随状态变化, 直观反映当前开/关
            _txtGetNode.text = _isGetNodeOn ? "GetNode[on]" : "GetNode[off]";
            // 开启时文字变绿以强调激活, 关闭时恢复白色
            _txtGetNode.color = _isGetNodeOn ? Color.green : Color.white;
            // 关闭拾取时, 一并隐藏可能还在显示的信息面板
            if (!_isGetNodeOn) HideInfoPanel();
            // 向外广播最新开关状态 (?. 防止无人订阅时空引用)
            OnGetNodeToggled?.Invoke(_isGetNodeOn);
        }
    }
}