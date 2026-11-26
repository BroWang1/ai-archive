// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaJobConfig.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 任务配置 (编辑器侧)
    /// 职责: 只保存/读取 "当前操作的是哪个任务批次" —— job_id 这一个任务标识
    ///   稳定的项目上下文 (project_id 等) 在 LqaProjectConfig
    ///   任务从属于项目 (job 属于某 project_id)
    /// 存储: EditorPrefs, 键前缀 LQA_Job_
    /// </summary>
    public class LqaJobConfig
    {
        /// <summary>
        /// EditorPrefs 存储键 (前缀统一为 LQA_Job_, 与平台/项目/筛选三组配置隔离)
        /// 一一对应下方 JobId 字段, 也供外部 (如 LQAResetMenu 一键清空配置) 引用删除
        /// </summary>
        public const string KEY_JOB_ID = "LQA_Job_JobId";

        /// <summary>
        /// 任务批次 ID (平台 job 实体主键, 拉取数据时定位到具体任务)
        /// "0" (或空串) 表示无远程任务: 处于空闲态, 不应发起拉取
        /// </summary>
        public string JobId = "0";

        /// <summary>
        /// 是否为 "无远程任务" 状态 (JobId 空或 "0")
        /// 为 true 时上层不应发起拉取; 供调用方在请求前做前置判断
        /// </summary>
        public bool IsIdle
        {
            get { return string.IsNullOrEmpty(JobId) || JobId == "0"; }
        }

        /// <summary>
        /// 从 EditorPrefs 读取任务标识; 键缺失时回落到与字段初始值一致的默认值 "0" (空闲态)
        /// </summary>
        public static LqaJobConfig Load()
        {
            var c = new LqaJobConfig();
            // 缺省: "0" = 无远程任务
            c.JobId = EditorPrefs.GetString(KEY_JOB_ID, "0");
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs; 用 ?? 兜底, 避免 JobId 为 null 时写入异常并保持与默认值一致
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_JOB_ID, JobId ?? "0");
        }
    }
}