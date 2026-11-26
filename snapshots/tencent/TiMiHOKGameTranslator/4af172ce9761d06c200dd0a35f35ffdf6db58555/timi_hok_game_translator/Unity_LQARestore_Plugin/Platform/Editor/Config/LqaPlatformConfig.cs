// ==========================================
// 文件: LQARestore\Platform\Editor\Config\LqaPlatformConfig.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using UnityEditor;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// LQA 平台连接配置 (编辑器侧, 仅连接信息)
    /// 职责: 集中保存/读取 "连接 LQA 平台" 所需的凭证 —— Host (平台地址) 与 Authorization (JWT)
    ///   本类只管连接信息, 不含任何任务过滤参数 (JobId/Language 等),
    ///   保持 "平台连接配置" 这一职责单一
    /// 存储方式: 落 EditorPrefs (编辑器级键值存储), 原因:
    ///   - 连接测试只在编辑器内运行, 无需随工程/打包分发;
    ///   - 不硬编码任何 Host/JWT (避免把内网地址与凭证写死进源码/版本库);
    ///   - 换机器/换账号时只改本机 EditorPrefs, 不动代码
    /// </summary>
    public class LqaPlatformConfig
    {
        /// <summary>
        /// EditorPrefs 存储键 (前缀统一为 LQA_Platform_, 与项目/任务/筛选三组配置隔离, 避免与工程其它键冲突)
        /// 每个键一一对应下方同名字段, 也供外部 (如 LQAResetMenu 一键清空配置) 引用删除
        /// </summary>
        public const string KEY_HOST = "LQA_Platform_Host";
        public const string KEY_AUTH = "LQA_Platform_Authorization";
        public const string KEY_API_PATH = "LQA_Platform_ApiPath";
        public const string KEY_DOWNLOAD_PATH = "LQA_Platform_DownloadPath";

        /// <summary>
        /// 平台地址, 仅含协议+主机+端口 (不含路径前缀), 例: http://127.0.0.1:8080
        /// </summary>
        public string Host = "";

        /// <summary>
        /// 鉴权 JWT (放入请求头 LQA-Authorization)
        /// </summary>
        public string Authorization = "";

        /// <summary>
        /// 平台接口路径前缀, 例: /api-pro
        /// 拼在 Host 与具体接口 (/api/...) 之间; 留空=直接拼 Host
        /// </summary>
        public string ApiPath = "";

        /// <summary>
        /// 数据下载路径前缀
        /// 拼在 Host 与 file_path 之间; 留空=直接拼 Host
        /// </summary>
        public string DownloadPath = "";

        /// <summary>
        /// dump 下载专用 Host: 把任务端口 :8080 换成静态服务端口 :80
        /// (连接测试用不到, 保留以备后续下载功能复用)
        /// </summary>
        public string DownloadHost
        {
            get { return string.IsNullOrEmpty(Host) ? Host : Host.Replace(":8080", ":80"); }
        }

        /// <summary>
        /// 从 EditorPrefs 读取配置
        /// </summary>
        public static LqaPlatformConfig Load()
        {
            var c = new LqaPlatformConfig();
            c.Host = EditorPrefs.GetString(KEY_HOST, "");
            c.Authorization = EditorPrefs.GetString(KEY_AUTH, "");
            c.ApiPath = EditorPrefs.GetString(KEY_API_PATH, "");
            c.DownloadPath = EditorPrefs.GetString(KEY_DOWNLOAD_PATH, "");
            return c;
        }

        /// <summary>
        /// 把当前配置写回 EditorPrefs
        /// </summary>
        public void Save()
        {
            EditorPrefs.SetString(KEY_HOST, Host ?? "");
            EditorPrefs.SetString(KEY_AUTH, Authorization ?? "");
            EditorPrefs.SetString(KEY_API_PATH, ApiPath ?? "");
            EditorPrefs.SetString(KEY_DOWNLOAD_PATH, DownloadPath ?? "");
        }

        /// <summary>
        /// 配置的实际存储位置描述 (供界面展示)
        /// 注意: 配置存于 EditorPrefs (编辑器级键值存储), 不是磁盘上的配置文件;
        ///   其物理落点随操作系统不同:
        ///   - Windows: 注册表 HKCU\Software\Unity Technologies\Unity Editor 5.x\ (键名带哈希后缀)
        ///   - macOS: ~/Library/Preferences/com.unity3d.UnityEditor5.x.plist
        ///   - Linux: ~/.config/unity3d/prefs
        /// </summary>
        public static string GetStorageLocationDescription()
        {
#if UNITY_EDITOR_WIN
            return @"注册表 HKCU\Software\Unity Technologies\Unity Editor 5.x\";
#elif UNITY_EDITOR_OSX
            return "~/Library/Preferences/com.unity3d.UnityEditor5.x.plist";
#else
            return "~/.config/unity3d/prefs";
#endif
        }
    }
}