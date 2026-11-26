// ==========================================
// 文件: LQARestore\Core\Editor\LqaWindowLayout.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using UnityEditor;
using UnityEngine;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// LQA 编辑器窗口布局辅助
    /// 将窗口锁定为固定尺寸 (min==max, 不可缩放), 并在主编辑器窗口内居中
    /// 每次打开 (含聚焦已存在窗口) 调用一次, 即可保证 "固定大小 + 居中"
    /// </summary>
    public static class LqaWindowLayout
    {
        /// <summary>
        /// 把窗口设为固定大小并相对主编辑器窗口居中
        /// </summary>
        /// <param name="win">目标窗口 (GetWindow 返回的实例)</param>
        /// <param name="width">固定宽度</param>
        /// <param name="height">固定高度</param>
        public static void ApplyFixedCentered(EditorWindow win, float width, float height)
        {
            if (win == null) return;

            var size = new Vector2(width, height);
            // 先锁定尺寸: min==max 使窗口不可缩放
            // 必须在设置 position 之前, 否则 position 的宽高会被旧的 maxSize 夹取
            win.minSize = size;
            win.maxSize = size;

            // 相对主编辑器窗口 (多显示器的虚拟桌面坐标系) 居中
            Rect main = EditorGUIUtility.GetMainWindowPosition();
            float x = main.x + (main.width - width) * 0.5f;
            float y = main.y + (main.height - height) * 0.5f;
            win.position = new Rect(x, y, width, height);
        }
    }
}