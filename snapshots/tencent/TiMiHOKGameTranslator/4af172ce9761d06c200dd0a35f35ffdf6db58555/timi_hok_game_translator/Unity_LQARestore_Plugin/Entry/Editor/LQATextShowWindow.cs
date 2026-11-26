// ==========================================
// 文件: LQARestore\Entry\Editor\LQATextShowWindow.cs
// 模块: Entry.Editor (入口层 编辑器侧)
// ==========================================

using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using LQARestore.Core.Json;
using LQARestore.Core.Editor;

/// <summary>
/// LQARestore 入口层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Entry.Editor
{
    /// <summary>
    /// "文本显隐标记" 编辑器窗口
    /// 职责:
    ///   1. 让用户独立选择一份 dump 的 ui_data_text.json, 解析后平铺列出其中所有含文本的节点
    ///      (每行展示: 显示勾选 / 原始判定 / name / textContent);
    ///   2. 提供关键字搜索, 按 name 或 textContent 实时过滤列表;
    ///   3. 对每条文本用 "显示" 勾选框决定还原时是否显示, 保存时把 manualShow 写回对应节点并回写原 JSON;
    /// 语义 (与还原侧约定一致):
    ///   - manualShow = true 表示还原时显示该文本;
    ///   - manualShow = false 表示还原时不重建该节点 (隐藏);
    ///   - 某条文本尚无 manualShow 字段时, 勾选状态默认取其自身的 isVisuallyVisible (显示语义一致),
    ///     保存后即为该文本补上 manualShow 字段;
    /// 还原侧 (LQARestore.Core.TextNodeBuilder): 节点有 manualShow 则以其为准, 无则回退 isVisuallyVisible
    /// 设计要点:
    ///   - 本窗口直接持有 MiniJson 解析出的节点字典引用 (TextEntry.nodeDict), 标记就地写在字典上,
    ///     无需靠 name/path 二次查找, 保存时整棵树用 JsonWriter 重新序列化回写, 天然精确;
    ///   - textContent 常含换行 (\n) 或超长富文本, 直接用单行 Label 会重叠/溢出,
    ///     故列表统一折成 "单行预览" (换行 -> ↵, 超长截断 + 省略号), 并以固定单行高度 + 裁剪样式绘制,
    ///     预览串在加载时预计算并缓存 (见 TextEntry.preview), 避免 OnGUI 每帧重算; 完整原文通过悬停 Tooltip 查看
    /// </summary>
    public class LQATextShowWindow : EditorWindow
    {
        /// <summary>
        /// 平铺后的单条文本记录
        /// 关键点: nodeDict 直接持有 MiniJson 解析出的节点字典引用, 保存时就地写标记 (无需按 name/path 反查)
        /// </summary>
        private class TextEntry
        {
            /// <summary>
            /// 节点 GameObject 名称 (对应 JSON 节点的 name 字段)
            /// </summary>
            public string name;

            /// <summary>
            /// 文本完整原文 (对应 ObjectData.Text.textContent), 用于 Tooltip 展示与搜索匹配
            /// </summary>
            public string textContent;

            /// <summary>
            /// 预计算的单行预览串 (换行折成 ↵ / 超长截断)
            /// 在加载 (Collect) 时算一次并缓存, 供 OnGUI 每帧直接使用, 避免每帧重复 Replace/Substring 产生临时字符串
            /// </summary>
            public string preview;

            /// <summary>
            /// 采集侧的像素可见性判定结果 (对应 ObjectData.Text.isVisuallyVisible)
            /// 只读, 作为 "原始判定" 列展示; 采集侧缓存无记录时保守判为不可见 (false)
            /// </summary>
            public bool isVisuallyVisible;

            /// <summary>
            /// 该节点在解析对象树中的字典引用 (manualShow 标记直接写在其根层)
            /// </summary>
            public Dictionary<string, object> nodeDict;

            /// <summary>
            /// 当前 "显示" 勾选状态 (true = 还原时显示该文本)
            /// </summary>
            public bool manualShow;
        }

        /// <summary>
        /// 当前已打开的 JSON 文件完整路径 (保存时回写至此); 未加载时为 null
        /// </summary>
        private string _jsonPath;

        /// <summary>
        /// MiniJson 解析出的 JSON 根对象 (通常为 Dictionary)
        /// 保存时对其整棵树做序列化回写; 为 null 表示尚未成功加载
        /// </summary>
        private object _root;

        /// <summary>
        /// 平铺后的全部文本记录 (只读字段, 内容通过 Clear/Add 复用同一实例)
        /// </summary>
        private readonly List<TextEntry> _entries = new List<TextEntry>();

        /// <summary>
        /// 搜索关键字 (为空时不过滤)
        /// </summary>
        private string _search = "";

        /// <summary>
        /// 列表区域的滚动位置
        /// </summary>
        private Vector2 _scroll;

        /// <summary>
        /// 单行、末尾裁剪 (TextClipping.Clip) 的标签样式
        /// GUIStyle 不能在构造期/序列化期创建, 故懒初始化于 OnGUI 首次绘制时
        /// </summary>
        private GUIStyle _ellipsisStyle;

        /// <summary>
        /// 打开窗口的静态入口 (供 LQARestoreMenu 的菜单项 "文本显隐标记..." 调用)
        /// 获取 (或聚焦) 一个工具窗口, 设置最小尺寸, 立即弹出文件选择框加载 JSON, 再显示窗口
        /// </summary>
        public static void Open()
        {
            // utility = true 表示浮动工具窗 (不可停靠); 第三个参数 focus = true 打开即获得焦点
            var win = GetWindow<LQATextShowWindow>(true, "LQA 文本显隐标记", true);
            // 固定尺寸 620 x 400 并居中: 保证 4 列 (显示/原始判定/name/textContent) 有足够展开空间
            LqaWindowLayout.ApplyFixedCentered(win, 900, 600);
            // 打开即引导用户选文件加载
            win.PickAndLoad();
            win.Show();
        }

        /// <summary>
        /// 弹出文件选择框选取 JSON, 选中后触发解析与平铺
        /// 用户取消选择 (返回空路径) 时静默返回, 不做任何处理
        /// </summary>
        private void PickAndLoad()
        {
            // 限定只显示 json 文件; 用户取消时 OpenFilePanel 返回空字符串
            string path = EditorUtility.OpenFilePanel("选择 Dump 的 ui_data_text.json", "", "json");
            if (string.IsNullOrEmpty(path)) return;
            LoadJson(path);
        }

        /// <summary>
        /// 读取并解析指定路径的 JSON, 递归收集所有含 Text.textContent 的节点到 _entries
        /// 整个过程包裹在 try/catch 中: 任何解析异常都不让编辑器崩溃, 仅弹窗告知并把状态复位
        /// </summary>
        /// <param name="path">待加载的 JSON 文件完整路径</param>
        private void LoadJson(string path)
        {
            // 先清空上一次的加载状态, 保证本次从干净状态开始 (失败时也不残留旧数据)
            _entries.Clear();
            _root = null;
            _jsonPath = null;

            // 防御性校验: 文件不存在直接弹窗返回 (正常情况下 OpenFilePanel 不会返回不存在的文件)
            if (!File.Exists(path))
            {
                EditorUtility.DisplayDialog("LQA 文本显隐标记", "文件不存在", "OK");
                return;
            }

            try
            {
                // 解析 JSON, 根必须是一个对象 (字典), 否则视为格式错误
                _root = MiniJson.Parse(File.ReadAllText(path));
                var rootDict = _root as Dictionary<string, object>;
                if (rootDict == null) throw new System.Exception("JSON 根不是对象");

                // 遍历顶层 nodes 数组, 逐个作为根递归收集含文本的节点
                var nodes = rootDict.Get<List<object>>("nodes");
                if (nodes != null)
                {
                    foreach (var n in nodes)
                        if (n is Dictionary<string, object> nodeDict)
                            Collect(nodeDict);
                }

                // 逐条处理: 缺失 manualShow 的文本, 勾选状态默认取其自身 isVisuallyVisible
                // (已在 Collect 中通过 GetInnerBool("manualShow", vis) 完成, 此处无需额外收尾;
                //  最终落盘时 Save 会为每个文本都写入 manualShow)

                // 全部成功后才记录路径, 保证 _jsonPath 与 _root/_entries 状态一致
                _jsonPath = path;
                Debug.Log($"[LQARestore][LQATextShowWindow] 已加载 {_entries.Count} 条文本, 来源: {path}");
            }
            catch (System.Exception e)
            {
                // 解析失败: 记录错误 + 弹窗提示, 并把 _root 复位为 null (界面回到 "未加载" 态)
                Debug.LogError($"[LQARestore][LQATextShowWindow] 解析失败: {e.Message}");
                EditorUtility.DisplayDialog("LQA 文本显隐标记", $"解析失败: {e.Message}", "OK");
                _root = null;
            }
        }

        /// <summary>
        /// 递归遍历节点树, 把含 Text.textContent 的节点收集为 TextEntry 加入 _entries
        /// 收集时顺带预计算单行预览串并读取 manualShow 初值, 避免后续在绘制期重复计算
        /// </summary>
        /// <param name="nodeDict">当前节点的字典数据 (含 ObjectData / ChildNodes 等)</param>
        private void Collect(Dictionary<string, object> nodeDict)
        {
            // 只有存在 ObjectData 下 Text/TMP 的 textContent 的节点才是 "文本节点", 才需要收集
            // 文本属性块: 旧版 Text 走 "Text" 键, TMP 走 "TMP" 键 (与还原侧 TextNodeBuilder 口径一致)
            var objectData = nodeDict.Get<Dictionary<string, object>>("ObjectData");
            var textProps = objectData.Get<Dictionary<string, object>>("Text")
                            ?? objectData.Get<Dictionary<string, object>>("TMP");
            if (textProps != null)
            {
                string content = textProps.Get<string>("textContent");
                if (content != null)
                {
                    // 采集侧缓存无记录时保守判为不可见, 故这里默认取 false 与其口径一致
                    bool vis = textProps.GetInnerBool("isVisuallyVisible", false);
                    _entries.Add(new TextEntry
                    {
                        name = nodeDict.Get<string>("name") ?? "Unnamed",
                        textContent = content,
                        // 预览串在加载时算一次并缓存, 供 OnGUI 每帧直接使用 (避免每帧 Replace/Substring)
                        preview = MakePreview(content),
                        isVisuallyVisible = vis,
                        // 直接持有该节点字典引用, 保存时就地写 manualShow
                        nodeDict = nodeDict,
                        // 有 manualShow 则读它, 无则默认取自身 isVisuallyVisible (显示语义一致)
                        manualShow = nodeDict.GetInnerBool("manualShow", vis)
                    });
                }
            }

            // 递归子节点 (无论当前节点是否含文本, 子孙仍可能含文本)
            var children = nodeDict.Get<List<object>>("ChildNodes");
            if (children != null)
            {
                foreach (var c in children)
                    if (c is Dictionary<string, object> cd)
                        Collect(cd);
            }
        }

        /// <summary>
        /// Unity EditorWindow 的 IMGUI 绘制回调, 每次界面刷新时被调用
        /// 依次绘制: 顶部工具行 (打开/保存) → 搜索行 → 表头 → 可滚动的文本列表
        /// </summary>
        private void OnGUI()
        {
            // 懒初始化单行裁剪样式: 超出列宽直接裁剪, 不换行, 避免多行文本撑高行、溢出到相邻行
            if (_ellipsisStyle == null)
            {
                _ellipsisStyle = new GUIStyle(EditorStyles.label)
                {
                    clipping = TextClipping.Clip,
                    wordWrap = false
                };
            }

            // 顶部工具行: 打开文件 + 保存 + 当前文件名
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("打开 JSON...", GUILayout.Width(100))) PickAndLoad();

                // 未加载 (无 _root) 时禁用 "保存", 防止空数据误写
                using (new EditorGUI.DisabledScope(_root == null))
                {
                    if (GUILayout.Button("保存", GUILayout.Width(80))) Save();
                }

                // 右侧顶到边显示当前文件名 (仅文件名, 未加载时显示占位提示)
                GUILayout.FlexibleSpace();
                GUILayout.Label(string.IsNullOrEmpty(_jsonPath) ? "(未加载)" : Path.GetFileName(_jsonPath),
                    EditorStyles.miniLabel);
            }

            // 尚未成功加载: 给出提示并结束本次绘制 (不画搜索/列表)
            if (_root == null)
            {
                EditorGUILayout.HelpBox("请先打开一份 Dump 的 ui_data_text.json 文件", MessageType.Info);
                return;
            }

            // 搜索行
            using (new EditorGUILayout.HorizontalScope())
            {
                GUILayout.Label("搜索", GUILayout.Width(32));
                _search = EditorGUILayout.TextField(_search);
            }

            // 表头 (各列宽度需与下方数据行保持一致, 以对齐)
            using (new EditorGUILayout.HorizontalScope(EditorStyles.toolbar))
            {
                GUILayout.Label("显示", GUILayout.Width(40));
                GUILayout.Label("原始判定", GUILayout.Width(80));
                GUILayout.Label("name", GUILayout.Width(180));
                GUILayout.Label("textContent");
            }

            // 文本列表 (可滚动)
            _scroll = EditorGUILayout.BeginScrollView(_scroll);
            // 统一的单行行高, 保证每行高度固定、彼此不重叠
            float rowHeight = EditorGUIUtility.singleLineHeight;
            foreach (var e in _entries)
            {
                // 搜索过滤: 关键字非空且既不匹配 name 也不匹配 textContent 时跳过该行 (忽略大小写)
                if (!string.IsNullOrEmpty(_search) &&
                    e.name.IndexOf(_search, System.StringComparison.OrdinalIgnoreCase) < 0 &&
                    e.textContent.IndexOf(_search, System.StringComparison.OrdinalIgnoreCase) < 0)
                    continue;

                using (new EditorGUILayout.HorizontalScope(GUILayout.Height(rowHeight)))
                {
                    // 显示勾选框 (勾选 = 还原时显示该文本), 固定单行高度
                    e.manualShow = EditorGUILayout.Toggle(e.manualShow,
                        GUILayout.Width(40), GUILayout.Height(rowHeight));

                    // 原始判定列: 只读展示 "✓ 可见" / "✗ 不可见", 用绿色/红色区分, 直观对照人工 "显示" 决策
                    var prevColor = GUI.color;
                    GUI.color = e.isVisuallyVisible ? new Color(0.55f, 0.9f, 0.55f) : new Color(0.95f, 0.55f, 0.55f);
                    EditorGUILayout.LabelField(e.isVisuallyVisible ? "✓ 可见" : "✗ 不可见",
                        _ellipsisStyle, GUILayout.Width(80), GUILayout.Height(rowHeight));
                    GUI.color = prevColor;

                    // name 列: 单行裁剪显示, 悬停 Tooltip 看完整名称
                    EditorGUILayout.LabelField(new GUIContent(e.name, e.name),
                        _ellipsisStyle, GUILayout.Width(180), GUILayout.Height(rowHeight));

                    // textContent 列: 显示预计算的单行预览 (缓存于 e.preview), 悬停 Tooltip 显示完整原文
                    EditorGUILayout.LabelField(
                        new GUIContent(e.preview, e.textContent),
                        _ellipsisStyle, GUILayout.Height(rowHeight));
                }
            }
            EditorGUILayout.EndScrollView();
        }

        /// <summary>
        /// 把多行/超长文本折成适合单行显示的预览串:
        ///   - 换行 \r\n / \n / \r 统一替换为可见符号 ↵ (避免行高突变与相邻行重叠);
        ///   - 制表符替换为空格;
        ///   - 超过 maxLen 时截断并补省略号 (完整原文仍可通过 Tooltip 查看)
        /// </summary>
        /// <param name="s">原始 textContent (可为 null/空)</param>
        /// <param name="maxLen">预览最大字符数, 超出则截断, 默认 120</param>
        /// <returns>单行预览串; 输入为空时返回空字符串</returns>
        private static string MakePreview(string s, int maxLen = 120)
        {
            // 空值保护: null/空串直接返回 "", 避免后续 Replace 抛异常
            if (string.IsNullOrEmpty(s)) return "";
            // 依次折叠各类换行与制表符为可读的单行形式 (\r\n 必须先于 \n/\r 处理, 避免产生两个 ↵)
            string oneLine = s.Replace("\r\n", " ↵ ")
                              .Replace("\n", " ↵ ")
                              .Replace("\r", " ↵ ")
                              .Replace("\t", " ");
            // 超长截断并补省略号
            return oneLine.Length > maxLen ? oneLine.Substring(0, maxLen) + " …" : oneLine;
        }

        /// <summary>
        /// 保存: 把各条 "显示" 勾选状态写回其节点字典, 再序列化整棵树回写原文件
        /// 需求约定: 保存时为每个文本节点都写入 manualShow 字段 (无论 true/false), 以显式固化显示/隐藏决策
        /// 写盘包裹在 try/catch 中, 失败仅弹窗提示不崩溃
        /// </summary>
        private void Save()
        {
            // 状态未就绪 (无根对象或无目标路径) 直接返回
            if (_root == null || string.IsNullOrEmpty(_jsonPath)) return;

            // 逐条把当前勾选状态写入对应节点字典 (nodeDict 是解析树中的引用, 就地修改即反映到 _root)
            foreach (var e in _entries)
            {
                e.nodeDict["manualShow"] = e.manualShow;
            }

            try
            {
                // 用 JsonWriter 把整棵树序列化 (排版/数字格式复刻采集侧, 见 JsonWriter) 后覆盖写回原文件
                File.WriteAllText(_jsonPath, JsonWriter.Serialize(_root));
                Debug.Log($"[LQARestore][LQATextShowWindow] 已保存 manualShow 到: {_jsonPath}");
                EditorUtility.DisplayDialog("LQA 文本显隐标记", "保存成功", "OK");
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[LQARestore][LQATextShowWindow] 保存失败: {e.Message}");
                EditorUtility.DisplayDialog("LQA 文本显隐标记", $"保存失败: {e.Message}", "OK");
            }
        }
    }
}