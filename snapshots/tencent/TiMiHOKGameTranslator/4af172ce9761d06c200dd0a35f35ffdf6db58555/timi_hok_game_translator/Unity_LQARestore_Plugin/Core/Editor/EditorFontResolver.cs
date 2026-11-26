// ==========================================
// 文件: LQARestore\Core\Editor\EditorFontResolver.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using LQARestore.Core;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// 编辑器环境下的字体解析器, 实现 IFontResolver
    /// 职责:
    ///   - 把 dump JSON 中的字体引用 (fontRef) 还原为工程内真实的 Font 资源;
    ///   - 兼容两种采集来源: 编辑器采集 (含 assetPath/guid) 与 Android 采集 (仅剩字体名);
    /// 设计要点:
    ///   - 三级解析顺序: 先按精确路径/guid 加载, 失败再退化为按字体名在工程内反查;
    ///   - 对 Unity 内置字体 (unity_builtin_extra / 全零 guid) 做特殊处理, 走 Resources.GetBuiltinResource;
    ///   - 按名字反查代价较高, 用实例字典缓存结果 (含未找到的 null), 避免重复扫描 AssetDatabase;
    /// </summary>
    public class EditorFontResolver : IFontResolver
    {
        // ==========================================
        // 缓存
        // ==========================================

        /// <summary>
        /// 字体名 -> Font 的缓存 (实例字段, 每个 resolver 独立一份)
        /// 缓存中允许存 null, 用于记住 "这个名字确实找不到", 避免对同一缺失字体反复扫描工程
        /// </summary>
        private readonly Dictionary<string, Font> _fontCache = new Dictionary<string, Font>();

        // ==========================================
        // 公开 API: IFontResolver 实现
        // ==========================================

        /// <summary>
        /// 把字体引用解析为工程内的 Font 资源, 解析不到时返回 null (由上层回退默认字体)
        /// </summary>
        /// <param name="fontRef">dump JSON 中的字体引用字典, 可能含 name / assetPath / guid 字段</param>
        /// <returns>解析到的 Font, 找不到返回 null</returns>
        public Font Resolve(Dictionary<string, object> fontRef)
        {
            if (fontRef == null) return null;

            // 1) 编辑器采集的 dump: 有 assetPath/guid, 走原精确加载
            var byPath = LoadAssetSmart<Font>(fontRef);
            if (byPath != null) return byPath;

            // 2) Android 采集: assetPath/guid 均为 null, 只剩字体名, 按名字在工程内反查
            string assetName = fontRef.Get<string>("name");
            if (string.IsNullOrEmpty(assetName)) return null;

            // 命中缓存直接返回 (含 "曾经没找到" 的 null 结果)
            if (_fontCache.TryGetValue(assetName, out var cached)) return cached;

            // 未缓存则扫描工程, 无论找到与否都写回缓存
            Font found = FindFontByNameInProject(assetName);
            _fontCache[assetName] = found;

            if (found == null)
                Debug.LogWarning($"[LQARestore][EditorFontResolver] 工程内未找到字体 '{assetName}', 回退默认字体, 中文可能显示为方块, 请确认该字体资源存在于当前工程的 Assets 下");
            return found;
        }

        // ==========================================
        // 内部辅助: 按名字反查 / 精确加载 / 内置资源判定
        // ==========================================

        /// <summary>
        /// 按字体名在整个工程内反查对应的 Font 资源 (用于 Android 采集只剩名字的场景)
        /// </summary>
        /// <param name="fontName">字体名, 可能带扩展名 (如 "xxx.ttf")</param>
        /// <returns>名字精确匹配的 Font, 找不到返回 null</returns>
        private Font FindFontByNameInProject(string fontName)
        {
            // 去掉可能带的扩展名 (如 "xxx.ttf" -> "xxx")
            string bare = Path.GetFileNameWithoutExtension(fontName);
            if (string.IsNullOrEmpty(bare)) return null;

            // FindAssets 为模糊匹配, 需再做一次精确名校验, 避免命中相似名 (如 ...Bold)
            foreach (var g in AssetDatabase.FindAssets($"t:Font {bare}"))
            {
                string path = AssetDatabase.GUIDToAssetPath(g);
                var f = AssetDatabase.LoadAssetAtPath<Font>(path);
                // 资源名或文件名任一与 bare 忽略大小写相等才算命中, 排除模糊匹配的近似项
                if (f != null &&
                    (string.Equals(f.name, bare, StringComparison.OrdinalIgnoreCase) ||
                     string.Equals(Path.GetFileNameWithoutExtension(path), bare, StringComparison.OrdinalIgnoreCase)))
                    return f;
            }
            return null;
        }

        /// <summary>
        /// 按引用中的 assetPath/guid 精确加载资源, 并对 Unity 内置资源做特殊处理
        /// </summary>
        /// <typeparam name="T">要加载的资源类型 (当前仅对 Font 做了内置资源分支)</typeparam>
        /// <param name="assetRef">资源引用字典, 含 name / assetPath / guid 字段</param>
        /// <returns>加载到的资源, 失败返回 null</returns>
        private T LoadAssetSmart<T>(Dictionary<string, object> assetRef) where T : UnityEngine.Object
        {
            if (assetRef == null) return null;

            string assetName = assetRef.Get<string>("name");
            string assetPath = assetRef.Get<string>("assetPath");
            string guid      = assetRef.Get<string>("guid");

            // 内置资源无法用 AssetDatabase 按路径加载, 需走 Resources.GetBuiltinResource
            if (IsBuiltinResource(assetPath, guid))
            {
                if (string.IsNullOrEmpty(assetName)) return null;

                if (typeof(T) == typeof(Font))
                {
                    // 内置字体需带 .ttf 后缀才能被 GetBuiltinResource 识别, 缺失则补上
                    string fontFile = assetName.EndsWith(".ttf", StringComparison.OrdinalIgnoreCase) ? assetName : assetName + ".ttf";
                    var f = Resources.GetBuiltinResource<Font>(fontFile);
                    if (f != null) return f as T;
                    return null;
                }

                // 目前仅支持内置 Font, 其它内置类型不处理
                return null;
            }

            // 非内置资源: 必须有路径才能加载
            if (string.IsNullOrEmpty(assetPath)) return null;
            return AssetDatabase.LoadAssetAtPath<T>(assetPath);
        }

        /// <summary>
        /// 判定给定引用是否指向 Unity 内置资源
        /// 依据: 路径含 "unity_builtin_extra", 或 guid 全为 0/f (内置资源的特征 guid)
        /// </summary>
        /// <param name="assetPath">资源路径, 可能为 null</param>
        /// <param name="guid">资源 guid, 可能为 null</param>
        /// <returns>是内置资源返回 true</returns>
        private bool IsBuiltinResource(string assetPath, string guid)
        {
            // 路径命中内置资源文件名
            if (!string.IsNullOrEmpty(assetPath)
                && assetPath.IndexOf("unity_builtin_extra", StringComparison.OrdinalIgnoreCase) >= 0)
                return true;

            // guid 全部由 0 / f 组成 (大小写不限) 也视为内置资源的特征 guid
            if (!string.IsNullOrEmpty(guid))
            {
                bool allZeroOrF = true;
                for (int i = 0; i < guid.Length; i++)
                {
                    char c = guid[i];
                    if (c != '0' && c != 'f' && c != 'F') { allZeroOrF = false; break; }
                }
                if (allZeroOrF) return true;
            }

            return false;
        }
    }
}