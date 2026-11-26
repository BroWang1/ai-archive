// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaFilterConfig.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 筛选变量配置 (编辑器侧)
    /// 职责: 集中管理 "从某个任务里怎么筛数据" 的查询过滤变量 —— 对应 GET /api/job/datas 的
    ///   language / count / minID / module_ids
    ///   这些是筛选条件, 语义上独立于 "任务是哪个" (job_id, 见 LqaJobConfig) 与
    ///   "项目上下文" (project_id 等, 见 LqaProjectConfig), 故单独成一层, 不与项目/任务混在一起
    /// 存储: EditorPrefs, 键前缀 LQA_Filter_ (与 LQA_Platform_ / LQA_Project_ / LQA_Job_ 区分)
    /// </summary>
    public class LqaFilterConfig
    {
        /// <summary>
        /// EditorPrefs 存储键 (前缀统一为 LQA_Filter_, 与平台/项目/任务三组配置隔离)
        /// 每个键一一对应下方同名字段, 也供外部 (如 LQAResetMenu 一键清空配置) 引用删除
        /// </summary>
        public const string KEY_LANGUAGE = "LQA_Filter_Language";
        public const string KEY_COUNT = "LQA_Filter_Count";
        public const string KEY_MIN_ID = "LQA_Filter_MinID";
        public const string KEY_MODULE_IDS = "LQA_Filter_ModuleIds";

        /// <summary>
        /// 语言代码 (平台内部数字码 value, 由筛选窗口从平台拉取下拉后选定)
        /// 对应 query 的 language; 空串 = 未选择 (不按语言过滤)
        /// </summary>
        public string Language = "";

        /// <summary>
        /// 单次拉取条数 (对应 query 的 count)
        /// 默认 "1"
        /// </summary>
        public string Count = "1";

        /// <summary>
        /// 增量游标 (对应 query 的 minID): 只拉取 id 大于该值的数据, 用于增量分页
        /// 默认 "0" = 从头拉取所有数据
        /// </summary>
        public string MinID = "0";

        /// <summary>
        /// 模块过滤 (对应 query 的 module_ids): 多个模块以 '_' 分隔, 请求时会替换为 ','
        /// 空串 = 不按模块过滤
        /// </summary>
        public string ModuleIds = "";

        /// <summary>
        /// 从 EditorPrefs 读取全部筛选变量; 键缺失时回落到与字段初始值一致的默认值
        /// </summary>
        public static LqaFilterConfig Load()
        {
            var c = new LqaFilterConfig();
            c.Language = EditorPrefs.GetString(KEY_LANGUAGE, "");  // 缺省: 未选语言
            c.Count = EditorPrefs.GetString(KEY_COUNT, "1");  // 缺省: 拉 1 条
            c.MinID = EditorPrefs.GetString(KEY_MIN_ID, "0");  // 缺省: 从头拉取
            c.ModuleIds = EditorPrefs.GetString(KEY_MODULE_IDS, "");  // 缺省: 不过滤模块
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs; 各字段用 ?? 兜底, 避免字段为 null 时写入异常并保持与默认值一致
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_LANGUAGE, Language ?? "");
            EditorPrefs.SetString(KEY_COUNT, Count ?? "1");
            EditorPrefs.SetString(KEY_MIN_ID, MinID ?? "0");
            EditorPrefs.SetString(KEY_MODULE_IDS, ModuleIds ?? "");
        }
    }
}