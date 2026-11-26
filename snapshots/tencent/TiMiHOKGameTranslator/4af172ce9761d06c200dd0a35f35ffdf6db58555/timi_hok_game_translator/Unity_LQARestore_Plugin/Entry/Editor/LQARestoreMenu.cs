// ==========================================
// 文件: LQARestore\Entry\Editor\LQARestoreMenu.cs
// 模块: Entry.Editor (入口层 编辑器侧)
// ==========================================

using System;
using System.IO;
using UnityEditor;
using UnityEngine;
using LQARestore.Core;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 入口层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Entry.Editor
{
    /// <summary>
    /// LQARestore 插件在 Unity 编辑器菜单栏 (Tools/LQA) 下的统一入口
    /// 职责: 通过 [MenuItem] 特性注册菜单项, 把编辑器里的常用操作 "挂" 到菜单上:
    ///   1. Tools/LQA/采集/启用 LQA 采集工具 —— 切换 LQATool 采集工具的总开关 (写 PlayerPrefs 并立即生效)
    ///   2. Tools/LQA/还原/从 Dump 文件还原 —— 选择一份 dump 的 JSON, 触发文本画面还原 (按译文配置决定原文/译文)
    ///   3. Tools/LQA/采集/设置 Dump 延时秒数... —— 打开 "Dump 前延时" 设置窗口
    ///   4. Tools/LQA/还原/文本显隐标记... —— 打开 "文本显隐标记" 窗口, 搜索/标记文本显示与否并写回 JSON
    ///   5. Tools/LQA/还原/译文文件配置... —— 设置并持久化 i18n 译文文件路径, 供还原/自动化按译文重建文本
    /// 设计要点: 本类只做 "菜单入口 + 参数编排" 这类轻量工作, 真正逻辑分别委托给
    ///   LQATool.Core.LQATool.SetEnable / LQADumpDelayWindow / RestoreEngine / LQATextShowWindow, 保持入口层薄而清晰
    /// </summary>
    public static class LQARestoreMenu
    {
        /// <summary>
        /// PlayerPrefs 中保存 "LQATool 启用开关" 的 Key (值: 1 = 启用, 0 = 禁用)
        /// 注意: 必须与运行时 LQATool.Core.LQATool.AutoInit 读取的 Key 完全一致,
        /// 否则本菜单写入的开关不会被采集工具的自动初始化逻辑读到
        /// </summary>
        public const string KEY_SHOW_DUMP_AND_GET_BTN = "LQA_ShowDumpAndGetNodeButtons";

        /// <summary>
        /// 菜单项: Tools/LQA/采集/启用 LQA 采集工具 (priority 100, 数值越小越靠前, 故排在该子菜单最前)
        /// 点击后翻转 LQATool 的启用状态: 1 -> 0 或 0 -> 1,
        /// 先写回 PlayerPrefs 持久化, 再调用 LQATool.SetEnable 让当前 Play 会话立即生效
        /// </summary>
        [MenuItem("Tools/LQA/采集/启用 LQA 采集工具", false, 100)]
        private static void ToggleDumpButtons()
        {
            // 1. 读取当前开关值 (缺省 0, 即首次进入时默认按 "未启用" 处理, 与采集工具运行时缺省保持一致)
            int cur = PlayerPrefs.GetInt(KEY_SHOW_DUMP_AND_GET_BTN, 0);
            // 2. 翻转状态 (1 <-> 0)
            int next = cur == 1 ? 0 : 1;
            bool enable = (next == 1);

            // 3. 把新状态写回 PlayerPrefs 并立即落盘, 保证重启编辑器后仍生效
            PlayerPrefs.SetInt(KEY_SHOW_DUMP_AND_GET_BTN, next);
            PlayerPrefs.Save();

            // 4. 让开关在运行时立即生效
            //    LQATool.Core.LQATool 是采集工具插件的静态入口 (采用全限定名以明确归属);
            //    其 SetEnable 通过启用/禁用管理器对象实现整体开关
            try
            {
                LQATool.Core.LQATool.SetEnable(enable);
            }
            catch (Exception ex)
            {
                // 调用失败仅告警不中断 (例如 LQATool 程序集缺失或未编译时), 避免编辑器抛异常
                Debug.LogWarning($"[LQARestore][LQARestoreMenu] 调用 LQATool.SetEnable 失败: {ex.Message}");
            }

            // 5. 输出结果日志, 便于在 Console 中确认开关已切换且已持久化
            Debug.Log($"[LQARestore][LQARestoreMenu] LQATool {(enable ? "已启用" : "已禁用")} (已持久化, 且当前 Play 会话立即生效)");
        }

        /// <summary>
        /// 菜单项校验方法 (validate function): 对应 "Enable LQA Tool" 菜单项
        /// 由 Unity 在菜单显示前调用, 用于控制菜单项的可用性与勾选显示:
        ///   - Menu.SetChecked 让该菜单项前显示/取消对勾, 直观反映当前开关状态;
        ///   - 返回 true 表示该菜单项始终可点击
        /// </summary>
        /// <returns>恒为 true (菜单项始终可用)</returns>
        [MenuItem("Tools/LQA/采集/启用 LQA 采集工具", true)]
        private static bool ToggleDumpButtons_Validate()
        {
            // 根据 PlayerPrefs 中的开关值决定是否在菜单项前显示对勾 (缺省 0 = 不勾选, 与采集工具运行时缺省保持一致)
            Menu.SetChecked("Tools/LQA/采集/启用 LQA 采集工具", PlayerPrefs.GetInt(KEY_SHOW_DUMP_AND_GET_BTN, 0) == 1);
            return true;
        }

        /// <summary>
        /// 菜单项: Tools/LQA/还原/从 Dump 文件还原 (priority 200)
        /// 让用户选择一个 dump 的 JSON 描述文件, 然后启动一次文本画面还原
        /// 流程: 弹出文件选择框 -> 校验所选文件 -> 读取持久化的译文文件配置 (LqaTranslationConfig)
        ///   -> 读取持久化的字体变体模板 (LqaFontVariantConfig)
        ///   -> 组装编辑器实现的两个依赖 (EditorFontResolver 字体解析 + EditorSceneHost 场景宿主)
        ///   -> 交给 RestoreEngine 执行还原
        ///      (译文路径为空/失效时按原文还原; 字体变体模板为空时字体按 dump 原样还原)
        /// </summary>
        [MenuItem("Tools/LQA/还原/从 Dump 文件还原", false, 200)]
        private static void RestoreFromDumpFile()
        {
            // 1. 弹出文件选择框, 限定只显示 json 文件; 用户取消时返回空字符串
            string jsonPath = EditorUtility.OpenFilePanel("选择 Dump 的 ui_data_text.json", "", "json");
            // 2. 未选择文件: 直接返回, 不做任何处理
            if (string.IsNullOrEmpty(jsonPath)) return;
            // 3. 防御性校验: 所选路径不存在时弹窗提示 (正常情况下 OpenFilePanel 不会返回不存在文件)
            if (!File.Exists(jsonPath))
            {
                EditorUtility.DisplayDialog("LQA Restore", "文件不存在", "OK");
                return;
            }

            // 4. 读取持久化的译文文件配置 (在 Tools/LQA/还原/译文文件配置... 中一次设置, 长期复用):
            //    配了有效路径 → 按译文还原; 未配置或路径已失效 → 传 null, 回退原文还原
            string translationPath = LqaTranslationConfig.GetPath();
            if (!string.IsNullOrEmpty(translationPath) && !File.Exists(translationPath))
            {
                Debug.LogWarning($"[LQARestore][LQARestoreMenu] 配置的译文文件不存在, 本次将用原文还原: {translationPath}");
                translationPath = null;
            }

            // 5. 读取持久化的字体变体模板 (在 Tools/LQA/还原/字体变体配置... 中设置):
            //     含 {name} 时还原会把字体名改写为变体 (工程内找不到则回退原字体); 空则字体按 dump 原样还原
            string fontVariantTemplate = LqaFontVariantConfig.GetTemplate();

            // 6. 组装编辑器环境下的两个依赖并创建还原引擎:
            //    - EditorFontResolver: 负责把 dump 里的字体引用解析为工程内真实 Font
            //    - EditorSceneHost: 负责新建场景 / 对齐分辨率 / 截图输出 / 标记脏
            var engine = new RestoreEngine(new EditorFontResolver(), new EditorSceneHost());
            // 7. 执行还原主流程 (译文路径为空时即原文还原)
            engine.RestoreFromDump(jsonPath, translationPath, fontVariantTemplate);
        }

        /// <summary>
        /// 菜单项: Tools/LQA/采集/设置 Dump 延时秒数... (priority 101)
        /// 打开 "LQA Dump 延时设置" 窗口, 供用户配置 Dump 前等待的秒数
        /// 逻辑全部委托给 LQADumpDelayWindow.Open (详见该窗口的配置链路说明)
        /// </summary>
        [MenuItem("Tools/LQA/采集/设置 Dump 延时秒数...", false, 101)]
        private static void SetDumpDelaySeconds() => LQADumpDelayWindow.Open();

        /// <summary>
        /// 菜单项: Tools/LQA/还原/文本显隐标记... (priority 201)
        /// 打开 "文本显隐标记" 窗口: 搜索/显示当前 dump JSON 里的文本 (name + textContent + isVisuallyVisible),
        /// 对每条文本用 "显示" 勾选决定还原时是否显示, 并把 manualShow 写回 JSON;
        /// 还原时: 有 manualShow 则以其为准, 无则回退 isVisuallyVisible
        /// </summary>
        [MenuItem("Tools/LQA/还原/文本显隐标记...", false, 201)]
        private static void OpenTextManualShow() => LQATextShowWindow.Open();
    }
}