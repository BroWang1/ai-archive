// ==========================================
// 文件: LQATool\Input\InputDetector.cs
// 模块: Input (输入)
// ==========================================

using System;
using UnityEngine;

/// <summary>
/// LQATool 输入层命名空间
/// </summary>
namespace LQATool.Input
{
    /// <summary>
    /// 输入检测器: 挂载在 GameObject 上的 MonoBehaviour
    /// 每帧检测鼠标 / 触摸输入, 识别 [按下] 与 [长按] 两类手势, 并通过事件对外通知
    /// 同时兼容 PC 端鼠标 (GetMouseButton*) 与移动端触摸 (Touch) 两种输入源
    /// </summary>
    public class InputDetector : MonoBehaviour
    {
        #region 对外抛出的事件 (Actions)

        /// <summary>
        /// 长按触发事件, 参数为长按发生时指针 (鼠标/手指) 在屏幕上的坐标 (Vector2)
        /// 订阅方可据此坐标做后续处理 (如弹出菜单、拾取该位置的对象等)
        /// </summary>
        public Action<Vector2> OnLongPressTriggered;

        /// <summary>
        /// 指针按下事件, 在按下 (鼠标左键按下 / 手指刚触屏) 的当帧触发一次
        /// </summary>
        public Action OnPointerDown;

        #endregion

        #region 内部状态变量

        /// <summary>
        /// 是否处于检测状态, 为 false 时 Update 直接跳过, 不做任何检测
        /// </summary>
        private bool _isDetecting = false;

        /// <summary>
        /// 当前是否正处于按压中 (从按下到抬起之间为 true)
        /// </summary>
        private bool _isPressing = false;

        /// <summary>
        /// 本次按压的起始时间 (Time.time, 单位秒), 用于计算按压时长
        /// </summary>
        private float _pressStartTime = 0f;

        /// <summary>
        /// 判定为长按所需的最短持续时间 (秒), 持续按住超过此值即视为长按
        /// </summary>
        private const float LONG_PRESS_DURATION = 1.0f;

        /// <summary>
        /// 本次按压是否已触发过长按
        /// 用于确保一次按压只触发一次长按, 避免达到阈值后每帧重复触发
        /// </summary>
        private bool _hasTriggeredLongPress = false;

        #endregion

        /// <summary>
        /// 设置检测开关
        /// </summary>
        /// <param name="enable">true 开启检测, false 关闭检测</param>
        public void SetEnable(bool enable) => _isDetecting = enable;

        /// <summary>
        /// Unity 生命周期方法, 每帧调用, 负责采集输入并推进长按状态机
        /// </summary>
        void Update()
        {
            // 未开启检测时直接返回, 避免不必要的输入采集
            if (!_isDetecting) return;

            // ==========================================
            // 采集本帧的三种指针状态 (同时兼容鼠标与触摸)
            // ==========================================

            // 按下: 鼠标左键按下 或 首个触摸点处于 Began (刚接触屏幕) 阶段
            bool isPointerDown = UnityEngine.Input.GetMouseButtonDown(0) || 
                (UnityEngine.Input.touchCount > 0 && UnityEngine.Input.GetTouch(0).phase == TouchPhase.Began);

            // 抬起: 鼠标左键抬起 或 首个触摸点处于 Ended (离开屏幕) / Canceled (被系统取消) 阶段
            bool isPointerUp = UnityEngine.Input.GetMouseButtonUp(0) || 
                (UnityEngine.Input.touchCount > 0 && (UnityEngine.Input.GetTouch(0).phase == TouchPhase.Ended || UnityEngine.Input.GetTouch(0).phase == TouchPhase.Canceled));

            // 持续按住: 鼠标左键保持按下 或 首个触摸点处于 Stationary (按住未移动) 阶段
            bool isPointerHeld = UnityEngine.Input.GetMouseButton(0) || 
                (UnityEngine.Input.touchCount > 0 && UnityEngine.Input.GetTouch(0).phase == TouchPhase.Stationary);

            // 按下瞬间: 抛出按下事件, 并初始化本次按压的状态
            if (isPointerDown)
            {
                OnPointerDown?.Invoke();

                _isPressing = true;  // 进入按压中
                _hasTriggeredLongPress = false;  // 重置长按触发标记
                _pressStartTime = Time.time;  // 记录起始时间
            }

            // 抬起瞬间: 结束按压并重置状态
            if (isPointerUp)
            {
                _isPressing = false;
                _hasTriggeredLongPress = false;
            }

            // 长按判定: 正在按压、尚未触发过长按、且仍保持按住
            if (_isPressing && !_hasTriggeredLongPress && isPointerHeld)
            {
                // 按住时长达到阈值 → 触发长按 (一次按压仅触发一次)
                if (Time.time - _pressStartTime >= LONG_PRESS_DURATION)
                {
                    _hasTriggeredLongPress = true;
                    TriggerLongPress();
                }
            }
        }

        /// <summary>
        /// 触发长按: 获取当前指针屏幕坐标并通过 OnLongPressTriggered 事件抛出
        /// 优先使用触摸坐标, 无触摸时回退到鼠标坐标
        /// </summary>
        private void TriggerLongPress()
        {
            // 默认取鼠标位置
            Vector2 pointerPosition = UnityEngine.Input.mousePosition;

            // 若存在触摸点, 则以首个触摸点的位置为准 (移动端优先)
            if (UnityEngine.Input.touchCount > 0)
            {
                pointerPosition = UnityEngine.Input.GetTouch(0).position;
            }

            // 抛出长按事件, 携带指针坐标
            OnLongPressTriggered?.Invoke(pointerPosition);
        }
    }
}