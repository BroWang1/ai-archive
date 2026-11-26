// ==========================================
// 文件: LQATool\Utils\UIHelper.cs
// 模块: Utils (工具箱)
// ==========================================

using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// UI 辅助工具类
    /// 提供与 Unity GameObject / UI 组件相关的静态辅助方法,
    /// 主要用于在 LQA (本地化质量保证) 流程中定位与识别 UI 元素
    /// 该类为静态类, 所有方法均可直接通过类名调用, 无需实例化
    /// </summary>
    public static class UIHelper
    {
        /// <summary>
        /// 获取指定 GameObject 在 Hierarchy (层级) 中的完整路径
        /// 例如: "Canvas/Panel/Button/Text", 用于唯一标识并定位某个 UI 对象
        /// </summary>
        /// <param name="obj">目标 GameObject</param>
        /// <returns>
        /// 从根节点到该对象, 以 "/" 分隔的层级路径字符串
        /// 若传入对象为 null, 则返回空字符串
        /// </returns>
        public static string GetGameObjectPath(GameObject obj)
        {
            // 防御性判空: 对象为空时直接返回空字符串, 避免空引用异常
            if (obj == null) return string.Empty;

            // 以自身名称作为路径的起点 (最末端节点)
            string path = obj.name;

            // 取得父级 Transform, 准备自底向上遍历
            Transform parent = obj.transform.parent;

            // 逐级向上回溯, 直到到达根节点 (parent 为 null)
            while (parent != null)
            {
                // 将父级名称拼接到当前路径前方, 形成 "父/子" 结构
                path = parent.name + "/" + path;

                // 继续向上一层父级移动
                parent = parent.parent;
            }

            // 返回拼接完成的完整层级路径
            return path;
        }

        /// <summary>
        /// 判断并返回指定 GameObject 上最主要 (最具代表性) 的 UI 组件类型名称
        /// 由于一个 GameObject 可能同时挂载多个组件 (如 Button 通常也带有 Image),
        /// 这里按照 "语义优先级" 从高到低依次检测, 返回第一个命中的类型
        /// </summary>
        /// <param name="go">目标 GameObject</param>
        /// <returns>
        /// 代表主要组件类型的字符串
        /// 若对象为 null 返回 "Unknown", 若未匹配到任何已知 UI 组件则返回 "Transform"
        /// </returns>
        public static string GetPrimaryComponentType(GameObject go)
        {
            // 防御性判空: 对象为空时返回 "Unknown"
            if (go == null) return "Unknown";

            // 优先级最高: 文本组件 (本地化最关注的对象)
            if (go.GetComponent<Text>() != null) return "Text";

            // TMP 文本 (通过 Graphic + 类型判定, 不直接引用 TMPro 程序集)
            var graphicForTmp = go.GetComponent<Graphic>();
            if (graphicForTmp != null && TextLike.TryWrap(graphicForTmp, out var tl) && tl.isTmp) return "TMP";

            // 交互类控件: 按钮 / 开关 / 滑动条 / 输入框 / 下拉框 / 滚动条
            if (go.GetComponent<Button>() != null) return "Button";
            if (go.GetComponent<Toggle>() != null) return "Toggle";
            if (go.GetComponent<Slider>() != null) return "Slider";
            if (go.GetComponent<InputField>() != null) return "InputField";
            if (go.GetComponent<Dropdown>() != null) return "Dropdown";
            if (go.GetComponent<Scrollbar>() != null) return "Scrollbar";

            // 容器类控件: 滚动视图 / 画布
            if (go.GetComponent<ScrollRect>() != null) return "ScrollRect";
            if (go.GetComponent<Canvas>() != null) return "Canvas";

            // 图像展示类: 普通图像 / 原始图像
            if (go.GetComponent<Image>() != null) return "Image";
            if (go.GetComponent<RawImage>() != null) return "RawImage";

            // 布局基础组件: 带有 RectTransform 说明是 UI 元素
            if (go.GetComponent<RectTransform>() != null) return "RectTransform";

            // 兜底: 未命中任何 UI 组件, 视为普通 Transform 对象
            return "Transform";
        }

        /// <summary>
        /// 跨 Unity 版本安全获取对象的实例标识, 仅用于日志/Dump JSON 里做 "本次运行期间" 的调试定位,
        /// 不保证跨进程、跨版本数值稳定, 禁止用于持久化存储或跨版本比对
        /// 版本分界: Unity 6000.4 (6.4) 起 Object.GetInstanceID() 被官方标记为 Obsolete(error: true),
        /// 不再通过编译; Unity 7000.0 起该方法被彻底移除, 必须改用 GetEntityId()
        /// </summary>
        /// <param name="obj">待获取标识的对象, 允许为 null</param>
        /// <returns>对象的实例标识数值, obj 为 null 时返回 0</returns>
        public static long GetStableInstanceId(Object obj)
        {
            if (obj == null) return 0;

#if UNITY_6000_4_OR_NEWER
            // 6000.4+: 官方新 ID 体系, 不能直接 (int) 强转 (会截断高位), 按官方建议转 ulong 再收窄成 long
            return (long)EntityId.ToULong(obj.GetEntityId());
#else
            // 6000.4 之前: 原生 API 仍可用, 行为与改造前完全一致
            return obj.GetInstanceID();
#endif
        }
    }
}