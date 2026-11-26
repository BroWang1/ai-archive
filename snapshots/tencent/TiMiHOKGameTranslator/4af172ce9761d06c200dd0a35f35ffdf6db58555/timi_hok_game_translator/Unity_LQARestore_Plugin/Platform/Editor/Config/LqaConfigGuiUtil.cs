// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaConfigGuiUtil.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;
using UnityEngine;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// 配置窗口共用的 GUI 小工具 (编辑器侧)
    /// 目前提供 "配置存储位置" 只读展示区, 供平台连接/项目/任务三个配置窗口复用, 避免重复代码
    /// </summary>
    public static class LqaConfigGuiUtil
    {
        /// <summary>
        /// 绘制 "配置存储位置" 只读区: 说明配置存于 EditorPrefs (非磁盘文件) + 键名 + 实际落点
        /// 全部用 SelectableLabel (只读可复制, 不可编辑, 无回写), 便于用户去 注册表/plist 定位, 无篡改风险
        /// </summary>
        /// <param name="keysText">要展示的 EditorPrefs 键名文本 (如 "KeyA, KeyB")</param>
        public static void DrawStorageLocation(string keysText)
        {
            // 区块标题: 加粗样式, 同时用 "(仅查看)" 明确提示本区内容只读, 不可修改
            EditorGUILayout.LabelField("配置存储位置 (仅查看)", EditorStyles.boldLabel);

            // 说明存储方式: 左侧标签 "存储方式" + 右侧固定说明文本
            // 告知用户配置写入 Unity EditorPrefs (编辑器级键值存储), 而非项目里的磁盘配置文件
            EditorGUILayout.LabelField("存储方式", "Unity EditorPrefs (编辑器级键值, 非磁盘配置文件)");

            // 第 1 行: 展示 EditorPrefs 的键名
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PrefixLabel("键名");

            // SelectableLabel 只读但可选中复制, 不产生任何写回值; 套 textField 样式并限高单行
            EditorGUILayout.SelectableLabel(keysText, EditorStyles.textField,
                GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();

            // 第 2 行: 展示配置在操作系统中的实际落点 (由 LqaPlatformConfig 按平台返回注册表/plist/prefs 路径)
            EditorGUILayout.BeginHorizontal();
            EditorGUILayout.PrefixLabel("实际位置");
            // 同样用只读可复制的 SelectableLabel, 方便用户直接复制去 注册表/plist 定位
            EditorGUILayout.SelectableLabel(LqaPlatformConfig.GetStorageLocationDescription(),
                EditorStyles.textField, GUILayout.Height(EditorGUIUtility.singleLineHeight));
            EditorGUILayout.EndHorizontal();
        }
    }
}