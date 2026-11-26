// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaSubmitConfig.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 提交结果配置 (编辑器侧)
    /// 职责: 集中管理 "提交还原结果" 这一动作 (POST /api/image/entity) 的配套开关 —— ai_sign
    ///   与 "上传数据回填" (module_id / resource_version, 见 LqaUploadConfig, 走 PATCH /api/data/entity)
    ///   是不同接口、不同动作, 故分开管理, 互不混合
    /// 存储: EditorPrefs, 键前缀 LQA_Submit_ (与 LQA_Platform_ / LQA_Upload_ 等区分)
    /// </summary>
    public class LqaSubmitConfig
    {
        /// <summary>
        /// EditorPrefs 存储键 (前缀统一为 LQA_Submit_)
        /// 也供外部 (如 LQAResetMenu 一键清空配置) 引用删除
        /// </summary>
        public const string KEY_TRIGGER_AI = "LQA_Submit_TriggerAI";

        /// <summary>
        /// 提交图片 (POST /api/image/entity) 时是否触发平台 AI 检测 (ai_sign):
        /// true => ai_sign=1 (触发 AI 检测/建bug); false => ai_sign=0 (只存图与框); 默认 true
        /// </summary>
        public bool TriggerAI = true;

        /// <summary>
        /// 从 EditorPrefs 读取; 键缺失时回落到默认值 (true, 默认触发 AI)
        /// </summary>
        public static LqaSubmitConfig Load()
        {
            var c = new LqaSubmitConfig();
            c.TriggerAI = EditorPrefs.GetBool(KEY_TRIGGER_AI, true);
            return c;
        }

        /// <summary>
        /// 写回 EditorPrefs
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetBool(KEY_TRIGGER_AI, TriggerAI);
        }
    }
}