// ==========================================
// 文件: LQARestore\Entry\Editor\LQADumpDelayWindow.cs
// 模块: Entry.Editor (入口层 编辑器侧)
// ==========================================

using UnityEditor;
using UnityEngine;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 入口层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Entry.Editor
{
    /// <summary>
    /// "LQA Dump 延时设置" 编辑器窗口
    /// 职责: 提供一个可视化界面, 用于设置 "执行 Dump 前等待的延时秒数",
    /// 由菜单 "Tools/LQA/Set Dump Delay Seconds..." (见 LQARestoreMenu) 打开
    /// 配置链路: 本窗口把用户输入的秒数写入 PlayerPrefs (Key: LQA_DumpDelaySeconds),
    /// 运行时由 LQATool.Core.LQAToolManager.HandleDumpRequest 读取该值并决定 Dump 前等待多久,
    /// 因此这里的 Key 必须与 LQAToolManager.DumpDelayPrefsKey 保持一致
    /// </summary>
    public class LQADumpDelayWindow : EditorWindow
    {
        /// <summary>
        /// PlayerPrefs 中保存 "Dump 前延时秒数" 的 Key
        /// 注意: 必须与运行时 LQATool.Core.LQAToolManager.DumpDelayPrefsKey 完全一致,
        /// 否则本窗口写入的配置不会被 Dump 流程读到
        /// </summary>
        public const string KEY_DUMP_DELAY_SECONDS = "LQA_DumpDelaySeconds";

        /// <summary>
        /// 窗口内当前编辑的延时秒数 (单位: 秒)
        /// 打开窗口时从 PlayerPrefs 读取初始化, 保存时回写到 PlayerPrefs
        /// </summary>
        private int _delaySeconds;

        /// <summary>
        /// 打开窗口的静态入口 (供 LQARestoreMenu 的菜单项调用)
        /// 创建 (或聚焦) 一个 "LQA Dump 延时设置" 工具窗口,
        /// 并用 PlayerPrefs 中已保存的延时值初始化界面, 再固定窗口尺寸
        /// </summary>
        public static void Open()
        {
            // 获取一个工具窗口实例 (utility = true 表示浮动工具窗, 不可停靠到主编辑器布局)
            var win = GetWindow<LQADumpDelayWindow>(true, "LQA Dump 延时设置");
            // 读取已持久化的延时值作为初始显示 (缺省 0, 表示立即 Dump)
            win._delaySeconds = PlayerPrefs.GetInt(KEY_DUMP_DELAY_SECONDS, 0);
            // 固定窗口尺寸 300 x 100 并居中, 避免内容简单却可随意拉伸
            LqaWindowLayout.ApplyFixedCentered(win, 300, 100);
        }

        /// <summary>
        /// Unity EditorWindow 的 IMGUI 绘制回调, 每次界面刷新时被调用
        /// 负责绘制 "延时秒数" 输入区与 "保存" 按钮, 并处理保存逻辑
        /// </summary>
        private void OnGUI()
        {
            // 说明性标签: 向用户解释该配置的含义 (0 表示不等待, 直接 Dump)
            EditorGUILayout.LabelField("Dump 前延时秒数 (0 = 立即 Dump)");
            // 整数输入框; 用 Mathf.Max 把下限钳制为 0, 防止配置出负数延时
            _delaySeconds = Mathf.Max(0, EditorGUILayout.IntField("延时秒数", _delaySeconds));
            // 在输入区与按钮之间留出一段垂直间距, 让布局更清晰
            EditorGUILayout.Space();
            // 点击 "保存" 后, 把当前值写回 PlayerPrefs 并持久化
            if (GUILayout.Button("保存"))
            {
                // 写入延时配置
                PlayerPrefs.SetInt(KEY_DUMP_DELAY_SECONDS, _delaySeconds);
                // 立即落盘, 确保配置在编辑器意外退出时也不会丢失
                PlayerPrefs.Save();
                // 打印一条日志, 便于在 Console 中确认配置已生效 (附带 Key 便于排查)
                Debug.Log($"[LQARestore][LQADumpDelayWindow] Dump 延时已设置为 {_delaySeconds} 秒 (LQA_DumpDelaySeconds)");
                // 保存成功后关闭窗口
                Close();
            }
        }
    }
}