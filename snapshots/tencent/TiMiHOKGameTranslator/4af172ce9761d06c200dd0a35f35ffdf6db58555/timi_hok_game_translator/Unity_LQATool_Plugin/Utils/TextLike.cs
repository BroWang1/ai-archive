// ==========================================
// 文件: LQATool\Utils\TextLike.cs
// 模块: Utils (工具箱)
// ==========================================

using System;
using System.Collections.Generic;
using System.Reflection;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 文本组件适配层: 屏蔽旧版 UGUI Text 与 TextMeshProUGUI 的差异
    ///   - 采集/染色/判定所需的多数成员 (color/canvasRenderer/canvas/transform) 都在公共基类 Graphic 上, 直接复用;
    ///   - 仅 "文本内容 text" 与 "富文本开关" 两处 API 名称/类型不同, 对 TMP 用反射屏蔽;
    ///   - 不直接引用 TMPro 程序集, 通过类型名匹配 + 反射访问, 使插件在未安装 TMP 的工程也能编译;
    /// </summary>
    public sealed class TextLike
    {
        /// <summary>
        /// 底层图形组件 (Text 或 TextMeshProUGUI), 公共成员经此访问
        /// </summary>
        public readonly Graphic graphic;

        /// <summary>
        /// 是否为 TMP 文本 (决定 text/richText 走反射还是强类型)
        /// </summary>
        public readonly bool isTmp;

        // 旧版 Text 的强类型引用 (isTmp=false 时非空)
        private readonly Text _uguiText;
        // TMP 的 text / richText 属性反射句柄 (isTmp=true 时非空)
        private readonly PropertyInfo _tmpTextProp;
        private readonly PropertyInfo _tmpRichTextProp;

        private TextLike(Graphic g, bool tmp, Text ugui, PropertyInfo tmpText, PropertyInfo tmpRich)
        {
            graphic = g;
            isTmp = tmp;
            _uguiText = ugui;
            _tmpTextProp = tmpText;
            _tmpRichTextProp = tmpRich;
        }

        /// <summary>
        /// 该文本所在的 Transform (作为可见性缓存的 key)
        /// </summary>
        public Transform transform => graphic.transform;

        /// <summary>
        /// 该文本所属的 Canvas (选相机时用)
        /// </summary>
        public Canvas canvas => graphic.canvas;

        /// <summary>
        /// CanvasRenderer (染色时拉满 alpha / NoText 时置 0)
        /// </summary>
        public CanvasRenderer canvasRenderer => graphic.canvasRenderer;

        /// <summary>
        /// 文本颜色 (染 ID 颜色), 直接走 Graphic.color
        /// </summary>
        public Color color
        {
            get => graphic.color;
            set => graphic.color = value;
        }

        /// <summary>
        /// 文本内容: Text 直取, TMP 走反射
        /// </summary>
        public string text
        {
            get
            {
                if (!isTmp) return _uguiText != null ? _uguiText.text : string.Empty;
                if (_tmpTextProp == null) return string.Empty;
                return _tmpTextProp.GetValue(graphic) as string ?? string.Empty;
            }
            set
            {
                if (!isTmp) { if (_uguiText != null) _uguiText.text = value; return; }
                if (_tmpTextProp != null && _tmpTextProp.CanWrite) _tmpTextProp.SetValue(graphic, value);
            }
        }

        /// <summary>
        /// 是否支持富文本: Text.supportRichText / TMP.richText
        /// </summary>
        public bool supportRichText
        {
            get
            {
                if (!isTmp) return _uguiText != null && _uguiText.supportRichText;
                if (_tmpRichTextProp == null) return false;
                object v = _tmpRichTextProp.GetValue(graphic);
                return v is bool b && b;
            }
        }

        /// <summary>
        /// 收集该文本涉及的所有 CanvasRenderer 到 buffer (会先 Clear):
        ///   - 旧版 Text: 仅自身;
        ///   - TMP: 自身 + 子物体 TMP_SubMeshUI 的渲染器 (fallback 字体/图集溢出时部分字形由子网格承载)
        /// </summary>
        public void CollectRenderers(List<CanvasRenderer> buffer)
        {
            buffer.Clear();
            if (graphic == null) return;

            if (!isTmp)
            {
                var cr = graphic.canvasRenderer;
                if (cr != null) buffer.Add(cr);
                return;
            }

            // TMP: 自身 + 子 SubMesh 的 CanvasRenderer (含未激活), 无 GC 重载写入 buffer
            graphic.GetComponentsInChildren(true, buffer);
        }

        // TMP 具体类型 -> (text 属性, richText 属性) 缓存, 避免每个组件重复反射
        private static readonly Dictionary<Type, PropertyInfo[]> _tmpPropCache = new Dictionary<Type, PropertyInfo[]>();

        /// <summary>
        /// 尝试把一个 Graphic 包装为 TextLike (仅旧版 Text 或 TMP 文本可包装成功)
        /// </summary>
        public static bool TryWrap(Graphic g, out TextLike result)
        {
            result = null;
            if (g == null) return false;

            // 旧版 UGUI Text
            if (g is Text ugui)
            {
                result = new TextLike(g, false, ugui, null, null);
                return true;
            }

            // TMP: 继承链上存在 TMP_Text 即认定 (覆盖 TextMeshProUGUI)
            if (IsTmpText(g.GetType()))
            {
                var props = GetTmpProps(g.GetType());
                result = new TextLike(g, true, null, props[0], props[1]);
                return true;
            }

            return false;
        }

        // 判断类型继承链上是否有 TMPro.TMP_Text
        private static bool IsTmpText(Type t)
        {
            for (Type cur = t; cur != null && cur != typeof(object); cur = cur.BaseType)
            {
                if (cur.Name == "TMP_Text" || cur.FullName == "TMPro.TMP_Text") return true;
            }
            return false;
        }

        // 取 (text, richText) 属性句柄, 带缓存
        private static PropertyInfo[] GetTmpProps(Type t)
        {
            if (_tmpPropCache.TryGetValue(t, out var cached)) return cached;

            const BindingFlags flags = BindingFlags.Public | BindingFlags.Instance;
            var arr = new PropertyInfo[]
            {
                t.GetProperty("text", flags),
                t.GetProperty("richText", flags),
            };
            _tmpPropCache[t] = arr;
            return arr;
        }
    }
}