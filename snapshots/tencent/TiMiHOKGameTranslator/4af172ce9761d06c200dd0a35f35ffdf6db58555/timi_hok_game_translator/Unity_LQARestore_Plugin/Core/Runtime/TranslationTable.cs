// ==========================================
// 文件: LQARestore\Core\Runtime\TranslationTable.cs
// 模块: Core (核心层)
// ==========================================

using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using LQARestore.Core.Json;

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 翻译表: 加载 i18n_translation_xx.json (示例), 按 keyHash / original 为还原文本提供译文
    /// 判定顺序 (Resolve):
    ///   1. 有 keyHash 且 entries 命中且其 translation 非空 → 用该 translation;
    ///   2. 否则用 textContent 完全匹配所有 entries.original 相等的条目, 收集其 translation 为候选;
    ///   3. 候选取 translation 最长者 (长度相同取靠后遍历到的), 非空则用之;
    ///   4. 仍为空 → 回退显示原始 textContent 字符串;
    /// </summary>
    public class TranslationTable
    {
        /// <summary>
        /// keyHash → 该条目字典 (含 original / translation), 供规则 1 的 O(1) 命中
        /// </summary>
        private readonly Dictionary<string, Dictionary<string, object>> _byKeyHash;

        /// <summary>
        /// original → 该原文对应的所有 translation (按文件出现顺序), 供规则 2/3 的候选匹配
        /// </summary>
        private readonly Dictionary<string, List<string>> _byOriginal;

        private TranslationTable(
            Dictionary<string, Dictionary<string, object>> byKeyHash,
            Dictionary<string, List<string>> byOriginal)
        {
            _byKeyHash = byKeyHash;
            _byOriginal = byOriginal;
        }

        /// <summary>
        /// 从 i18n_translation_xx.json (示例) 加载翻译表; 路径无效或解析失败时返回 null (仅告警, 不抛异常)
        /// </summary>
        /// <param name="path">i18n_translation_xx.json (示例) 的完整路径</param>
        /// <returns>加载成功的翻译表, 失败返回 null (调用方据此回退到原文还原)</returns>
        public static TranslationTable Load(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return null;
            try
            {
                var root = MiniJson.Parse(File.ReadAllText(path)) as Dictionary<string, object>;
                var entries = root.Get<Dictionary<string, object>>("entries");
                if (entries == null) throw new Exception("缺少 entries 字段");

                var byKeyHash = new Dictionary<string, Dictionary<string, object>>();
                var byOriginal = new Dictionary<string, List<string>>();
                foreach (var kv in entries)
                {
                    if (!(kv.Value is Dictionary<string, object> entry)) continue;
                    byKeyHash[kv.Key] = entry;

                    // original 缺失的条目无法参与原文匹配, 跳过其 original 索引 (仍保留 keyHash 索引)
                    string original = entry.Get<string>("original");
                    if (original == null) continue;
                    string translation = entry.Get<string>("translation") ?? "";
                    if (!byOriginal.TryGetValue(original, out var list))
                    {
                        list = new List<string>();
                        byOriginal[original] = list;
                    }
                    list.Add(translation);
                }
                Debug.Log($"[LQARestore][TranslationTable] 已加载翻译表: {path} (entries={byKeyHash.Count})");
                return new TranslationTable(byKeyHash, byOriginal);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[LQARestore][TranslationTable] 加载失败: {path}, {e.Message}");
                return null;
            }
        }

        /// <summary>
        /// 解析最终文本 (判定顺序见类注释)
        /// </summary>
        /// <param name="keyHash">节点 XxxxLocalize.keyHash, 无则传空</param>
        /// <param name="textContent">节点 Text/TMP.textContent (兜底文本)</param>
        /// <returns>最终用于还原/导出的文本</returns>
        public string Resolve(string keyHash, string textContent)
        {
            // 1. keyHash 命中且译文非空 → 直接用; 命中但译文为空则继续往下走候选匹配
            if (!string.IsNullOrEmpty(keyHash) && _byKeyHash.TryGetValue(keyHash, out var entry))
            {
                string t = entry.Get<string>("translation");
                if (!string.IsNullOrEmpty(t)) return t;
            }

            // 2/3. textContent 完全匹配 original 收集候选, 取最长译文 (等长取靠后); textContent 为空则跳过
            if (!string.IsNullOrEmpty(textContent) && _byOriginal.TryGetValue(textContent, out var candidates))
            {
                string best = null;
                foreach (var t in candidates)
                {
                    if (string.IsNullOrEmpty(t)) continue;
                    // >= 保证长度相同时后遍历到的覆盖前者
                    if (best == null || t.Length >= best.Length) best = t;
                }
                if (!string.IsNullOrEmpty(best)) return best;
            }

            // 4. 兜底: 显示原始 textContent
            return textContent ?? "";
        }
    }
}