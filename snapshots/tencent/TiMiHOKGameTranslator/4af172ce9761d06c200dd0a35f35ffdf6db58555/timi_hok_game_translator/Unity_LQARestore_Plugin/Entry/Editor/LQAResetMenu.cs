// ==========================================
// 文件: LQARestore\Entry\Editor\LQAResetMenu.cs
// 模块: Entry.Editor (入口层 编辑器侧)
// ==========================================

using System;
using UnityEditor;
using UnityEngine;
using LQARestore.Platform.Editor;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 入口层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Entry.Editor
{
    /// <summary>
    /// LQA "恢复默认设置" 菜单入口
    /// 职责: 一键清空本插件写入的全部持久化配置 (EditorPrefs + PlayerPrefs),
    ///   使所有配置回落到各 config 类 Load() 时的默认值, 并关闭已打开的 LQA 窗口。
    /// </summary>
    public static class LQAResetMenu
    {
        /// <summary>
        /// 菜单项: Tools/LQA/恢复默认设置... (priority 900)
        /// 与平台组 (300+) 相差远大于 10, Unity 会在其上方自动绘制分隔线, 使其靠底部并与上方分组隔开
        /// </summary>
        [MenuItem("Tools/LQA/恢复默认设置...", false, 900)]
        private static void ResetAllToDefault()
        {
            // 1. 二次确认: 该操作不可撤销
            bool ok = EditorUtility.DisplayDialog(
                "LQA 恢复默认设置",
                "将清空 LQA 插件的全部配置 (平台连接/项目/任务/筛选/上传/提交/译文/字体变体、" +
                "采集开关、Dump 延时), 并关闭已打开的 LQA 窗口\n\n此操作不可撤销, 是否继续?",
                "恢复默认", "取消");
            if (!ok) return;

            // 2. 删除 EditorPrefs 配置 (16 个): 删除后各 config.Load() 会回落到默认值
            EditorPrefs.DeleteKey(LqaPlatformConfig.KEY_HOST);
            EditorPrefs.DeleteKey(LqaPlatformConfig.KEY_AUTH);
            EditorPrefs.DeleteKey(LqaPlatformConfig.KEY_API_PATH);
            EditorPrefs.DeleteKey(LqaPlatformConfig.KEY_DOWNLOAD_PATH);
            EditorPrefs.DeleteKey(LqaProjectConfig.KEY_PROJECT_ID);
            EditorPrefs.DeleteKey(LqaJobConfig.KEY_JOB_ID);
            EditorPrefs.DeleteKey(LqaFilterConfig.KEY_LANGUAGE);
            EditorPrefs.DeleteKey(LqaFilterConfig.KEY_COUNT);
            EditorPrefs.DeleteKey(LqaFilterConfig.KEY_MIN_ID);
            EditorPrefs.DeleteKey(LqaFilterConfig.KEY_MODULE_IDS);
            EditorPrefs.DeleteKey(LqaUploadConfig.KEY_MODULE_ID);
            EditorPrefs.DeleteKey(LqaUploadConfig.KEY_RESOURCE_VERSION);
            EditorPrefs.DeleteKey(LqaSubmitConfig.KEY_TRIGGER_AI);
            EditorPrefs.DeleteKey(LqaTranslationConfig.KEY_TRANSLATION_PATH);
            EditorPrefs.DeleteKey(LqaFontVariantConfig.KEY_FONT_VARIANT_TEMPLATE);

            // 3. 删除 PlayerPrefs 配置 (2 个) 并立即落盘
            PlayerPrefs.DeleteKey(LQARestoreMenu.KEY_SHOW_DUMP_AND_GET_BTN);
            PlayerPrefs.DeleteKey(LQADumpDelayWindow.KEY_DUMP_DELAY_SECONDS);
            PlayerPrefs.Save();

            // 4. 采集开关回默认 (关闭): 让当前 Play 会话立即生效, 与删除 key 后的缺省 0 保持一致
            try
            {
                LQATool.Core.LQATool.SetEnable(false);
            }
            catch (Exception ex)
            {
                // 调用失败仅告警不中断 (例如 LQATool 程序集缺失或未编译时)
                Debug.LogWarning($"[LQARestore][LQAResetMenu] 调用 LQATool.SetEnable 失败: {ex.Message}");
            }

            // 5. 关闭所有已打开的 LQA 窗口 (命名空间以 LQARestore 开头, 覆盖平台/核心/入口三组窗口)
            int closed = 0;
            foreach (var w in Resources.FindObjectsOfTypeAll<EditorWindow>())
            {
                if (w == null) continue;
                var ns = w.GetType().Namespace;
                if (ns != null && ns.StartsWith("LQARestore"))
                {
                    w.Close();
                    closed++;
                }
            }

            // 6. 输出结果日志与完成提示
            Debug.Log($"[LQARestore][LQAResetMenu] 已恢复默认设置: 清除 EditorPrefs 14 项 + PlayerPrefs 2 项, 关闭窗口 {closed} 个");
            EditorUtility.DisplayDialog("LQA 恢复默认设置", "已恢复默认设置", "OK");
        }
    }
}