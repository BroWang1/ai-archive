// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaUploadConfig.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 上传配置 (编辑器侧)
    /// 职责: 集中管理 "上传数据时随数据带上" 的字段 —— module_id / resource_version
    ///   这两项仅在上传回填 (PATCH /api/data/entity) 时用到, 语义上属于 "上传" 这一动作的配套参数,
    ///   与 "项目标识" (project_id, 见 LqaProjectConfig, 拉取/上传都要用) 分开管理, 互不混合
    /// 存储: EditorPrefs, 键前缀 LQA_Upload_ (与 LQA_Platform_ / LQA_Project_ / LQA_Job_ / LQA_Filter_ 区分)
    /// </summary>
    public class LqaUploadConfig
    {
        /// <summary>
        /// EditorPrefs 存储键 (前缀统一为 LQA_Upload_, 与平台/项目/任务/筛选四组配置隔离)
        /// 每个键一一对应下方同名字段, 也供外部 (如 LQAResetMenu 一键清空配置) 引用删除
        /// </summary>
        public const string KEY_MODULE_ID        = "LQA_Upload_ModuleId";
        public const string KEY_RESOURCE_VERSION = "LQA_Upload_ResourceVersion";

        /// <summary>
        /// 模块 ID (对应上传回填时随数据带上的 module_id)
        /// 空串 = 不带该字段
        /// </summary>
        public string ModuleId = "";

        /// <summary>
        /// 资源版本号 (如 0.20142.29.0; 上传回填时随数据带上的 resource_version)
        /// 空串 = 不带该字段
        /// </summary>
        public string ResourceVersion = "";

        /// <summary>
        /// 从 EditorPrefs 读取全部上传字段; 键缺失时回落到与字段初始值一致的默认值 (空串)
        /// </summary>
        public static LqaUploadConfig Load()
        {
            var c = new LqaUploadConfig();
            // 缺省: 不带 module_id
            c.ModuleId        = EditorPrefs.GetString(KEY_MODULE_ID, "");
            // 缺省: 不带 resource_version
            c.ResourceVersion = EditorPrefs.GetString(KEY_RESOURCE_VERSION, "");
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs; 各字段用 ?? 兜底, 避免字段为 null 时写入异常并保持与默认值一致
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_MODULE_ID, ModuleId ?? "");
            EditorPrefs.SetString(KEY_RESOURCE_VERSION, ResourceVersion ?? "");
        }
    }
}