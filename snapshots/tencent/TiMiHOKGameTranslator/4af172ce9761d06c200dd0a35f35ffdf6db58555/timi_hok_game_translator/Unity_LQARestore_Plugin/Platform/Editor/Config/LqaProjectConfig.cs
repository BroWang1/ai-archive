// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaProjectConfig.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 项目配置 (编辑器侧)
    /// 职责: 只保存/读取 "当前测试项目" 这一核心标识 —— project_id
    ///   它是拉取/上传都要用的上级上下文 (变更频率低)
    ///   上传时随数据带上的 module_id / resource_version 已拆到独立的"上传配置"(LqaUploadConfig),
    ///   任务标识 job_id 在 LqaJobConfig, 筛选变量在 LqaFilterConfig, 各司其职不混合
    /// 存储: EditorPrefs, 键前缀 LQA_Project_
    /// </summary>
    public class LqaProjectConfig
    {
        /// <summary>
        /// EditorPrefs 存储键 (前缀统一为 LQA_Project_, 与平台/任务/筛选三组配置隔离)
        /// 一一对应下方 ProjectId 字段, 也供外部 (如 LQAResetMenu 一键清空配置) 引用删除
        /// </summary>
        public const string KEY_PROJECT_ID = "LQA_Project_ProjectId";

        /// <summary>
        /// 项目 ID (平台 /api/project 实体主键, 拉取/上传均需的上级上下文)
        /// "0" (或空串) 表示尚未配置项目; 任务/筛选等操作应以该项目为归属
        /// </summary>
        public string ProjectId = "0";

        /// <summary>
        /// 从 EditorPrefs 读取项目标识; 键缺失时回落到与字段初始值一致的默认值 "0" (未配置)
        /// </summary>
        public static LqaProjectConfig Load()
        {
            var c = new LqaProjectConfig();
            // 缺省: "0" = 未配置项目
            c.ProjectId = EditorPrefs.GetString(KEY_PROJECT_ID, "0");
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs; 用 ?? 兜底, 避免 ProjectId 为 null 时写入异常并保持与默认值一致
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_PROJECT_ID, ProjectId ?? "0");
        }
    }
}