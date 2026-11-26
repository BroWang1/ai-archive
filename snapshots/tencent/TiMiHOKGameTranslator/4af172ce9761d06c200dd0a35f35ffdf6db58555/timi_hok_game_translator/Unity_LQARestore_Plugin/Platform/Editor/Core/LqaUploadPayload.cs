// ==========================================
// 文件: LQARestore\Platform\Editor\Core\LqaUploadPayload.cs
// 模块: Platform.Editor (平台连接 编辑器侧)
// ==========================================

using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 平台连接 编辑器侧命名空间
/// </summary>
namespace LQARestore.Platform.Editor
{
    /// <summary>
    /// 上传数据的载荷构造器 (编辑器侧)
    /// 职责: 把一个 LQATool 采集产物目录 (含 ui_data_text.json + ScreenShot_*.png) 整理成
    ///   平台 POST /api/data/entity 需要的 data 对象 JSON, 并定位待上传的截图/背景图
    /// 平台建 data 接口从 data 对象里读取的必需/可选字段:
    ///   - name: 必填非空 (用采集目录名或 json 文件名);
    ///   - gameData.resourceVersion: 资源版本 (可选);
    ///   - phoneType: 机型 (可选);
    ///   - sizeX / sizeY: 屏幕宽高 (可选, 缺省 0);
    ///   - bg_data: 背景图 hex 字符串 (平台侧还原比对用);
    ///   其余字段原样保留 (平台会把整个 data gzip 存盘)
    /// 与其它采集源 dump 结构的差异 (关键):
    ///   某些采集源的 dump 会带 meta/version/device 字段并在上传前 pop 掉 —— 那是针对其自身结构
    ///   Unity 的 ui_data_text.json 是 UIDumpResult 结构 (appVersion/systemLanguage/screenWidth/screenHeight...),
    ///   没有 meta/version/device, 照搬那套 pop 会直接抛异常, 故这里改为从 Unity 实际字段映射:
    ///     resourceVersion < appVersion; sizeX/sizeY < screenWidth/screenHeight; phoneType < systemLanguage(兜底)
    ///   若平台对这些值有更严格要求, 可在此调整映射, 逻辑集中一处便于维护
    /// </summary>
    public static class LqaUploadPayload
    {
        /// <summary>
        /// 一个采集目录整理后的上传素材 (Build 的产物, 供上传流程逐字段消费)
        /// </summary>
        public class Payload
        {
            /// <summary>
            /// 补全后的 data 对象 JSON 文本 (喂给 UploadDataJson 作为 POST body)
            /// </summary>
            public string DataJson;

            /// <summary>
            /// 待上传的截图文件绝对路径 (喂给 UploadFile); 目录无截图时为空串
            /// </summary>
            public string ShotImagePath;

            /// <summary>
            /// 该条数据名 (取采集目录名, 仅用于日志展示与问题定位)
            /// </summary>
            public string Name;
        }

        /// <summary>
        /// 采集截图候选名 (按优先级挑一张作为上传的 shot 图: 完整图 > 文本 ID 图)
        /// </summary>
        private static readonly string[] ShotCandidates =
        {
            "ScreenShot_Full.png", "ScreenShot_TextId.png",
        };

        /// <summary>
        /// 背景图候选名 (按优先级挑一张作为 bg_data 来源: 无文字图优先, 其次专用背景图)
        /// </summary>
        private static readonly string[] BgCandidates =
        {
            "ScreenShot_NoText.png", "ScreenShot_BG.png",
        };

        /// <summary>
        /// 判断一个目录是否是可上传的采集产物目录 (至少含 ui_data_text.json)
        /// 供批量上传前的目录筛选/过滤使用, 避免把非采集目录送进 Build 触发异常
        /// </summary>
        public static bool IsDumpDir(string dir)
        {
            return !string.IsNullOrEmpty(dir) && Directory.Exists(dir) &&
                   File.Exists(Path.Combine(dir, "ui_data_text.json"));
        }

        /// <summary>
        /// 把一个采集目录整理成上传素材, 失败抛异常 (调用方捕获并计入失败)
        /// </summary>
        public static Payload Build(string dir)
        {
            string jsonPath = Path.Combine(dir, "ui_data_text.json");
            if (!File.Exists(jsonPath))
                throw new Exception("目录缺少 ui_data_text.json");

            string raw = File.ReadAllText(jsonPath, Encoding.UTF8);
            // 清洗非法数字字面量 (nan/inf 一类不是合法 JSON 数字), 统一替成 0,
            // 否则后续 MiniJson.Parse 会解析失败; 顺序上先替带符号/带括号的长写法, 再替短写法
            raw = raw.Replace("-nan(ind)", "0").Replace("nan(ind)", "0")
                     .Replace("-nan", "0").Replace("nan", "0")
                     .Replace("-inf", "0").Replace("inf", "0");

            object parsed = MiniJson.Parse(raw);
            var root = parsed as Dictionary<string, object>;
            if (root == null)
                throw new Exception("ui_data_text.json 不是合法的 JSON 对象");

            // name: 平台侧要求必填非空, 优先用采集目录名 (最能标识这条数据的来源),
            // 目录名意外为空时回退到固定的 json 文件名占位
            string name = new DirectoryInfo(dir).Name;
            if (string.IsNullOrEmpty(name)) name = "ui_data_text.json";
            root["name"] = name;

            // gameData.resourceVersion <- appVersion
            // Unity 采集侧没有独立的资源版本字段, 用 appVersion 映射充当;
            // 若 gameData 已带该键则尊重原值不覆盖, appVersion 为空时也不写入
            string appVersion = root.GetInnerString("appVersion", "");
            var gameData = root.Get<Dictionary<string, object>>("gameData");
            if (gameData == null) { gameData = new Dictionary<string, object>(); root["gameData"] = gameData; }
            if (!string.IsNullOrEmpty(appVersion) && !gameData.ContainsKey("resourceVersion"))
                gameData["resourceVersion"] = appVersion;

            // sizeX / sizeY <- screenWidth / screenHeight
            // 平台按此值还原画布尺寸; 采集侧缺字段时 GetInnerInt 回退 0 (平台侧视为未知宽高)
            root["sizeX"] = root.GetInnerInt("screenWidth", 0);
            root["sizeY"] = root.GetInnerInt("screenHeight", 0);

            // phoneType: 采集侧无真实机型字段, 用 systemLanguage 兜底 (仅占位, 平台侧为可选字段);
            // 若原 data 已带 phoneType 则保留原值不覆盖
            if (!root.ContainsKey("phoneType"))
                root["phoneType"] = root.GetInnerString("systemLanguage", "");

            // bg_data: 平台侧还原比对时用的背景图。目录里存在候选背景图时, 读原始字节转 hex 写入;
            // 没有背景图则不写该键 (平台侧按缺省处理)
            string bgPath = FindFirst(dir, BgCandidates);
            if (!string.IsNullOrEmpty(bgPath))
                root["bg_data"] = ToHex(File.ReadAllBytes(bgPath));

            // 把补全/映射完的 data 对象序列化回 JSON 文本, 作为最终 POST body
            string dataJson = JsonWriter.Serialize(root);

            // 按候选优先级定位一张截图作为上传的 shot 图 (可能为空串, 由上传流程决定是否跳过传图)
            string shot = FindFirst(dir, ShotCandidates);

            return new Payload { DataJson = dataJson, ShotImagePath = shot, Name = name };
        }

        /// <summary>
        /// 在目录里按候选名顺序找第一张存在的文件, 命中即返回其绝对路径; 全部不存在返回 ""
        /// 用于在多个可能的截图/背景图文件名之间按优先级择一
        /// </summary>
        private static string FindFirst(string dir, string[] candidates)
        {
            foreach (var c in candidates)
            {
                string p = Path.Combine(dir, c);
                if (File.Exists(p)) return p;
            }
            return "";
        }

        /// <summary>
        /// 字节转 hex 字符串 (小写, 与平台约定的图片 hex 编码口径保持一致, 保证平台侧解析一致)
        /// 空数据返回 ""; 使用 StringBuilder 预分配 2 倍长度避免频繁扩容
        /// </summary>
        private static string ToHex(byte[] data)
        {
            if (data == null || data.Length == 0) return "";
            var sb = new StringBuilder(data.Length * 2);
            foreach (byte b in data) sb.Append(b.ToString("x2"));
            return sb.ToString();
        }
    }
}