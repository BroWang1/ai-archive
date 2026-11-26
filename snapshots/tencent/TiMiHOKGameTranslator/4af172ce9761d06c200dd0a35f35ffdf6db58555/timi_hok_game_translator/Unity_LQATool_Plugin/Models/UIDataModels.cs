// ==========================================
// 文件: LQATool\Models\UIDataModels.cs
// 模块: Models (数据模型)
// ==========================================

using System;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// LQATool 数据模型层命名空间
/// </summary>
namespace LQATool.Models
{
    /// <summary>
    /// UI 节点数据: 对应场景 Hierarchy 中的单个 GameObject 节点
    /// 多个 UINodeData 通过 ChildNodes 递归嵌套, 构成一棵完整的 UI 节点树
    /// </summary>
    [Serializable]
    public class UINodeData
    {
        /// <summary>
        /// GameObject 名称 (对应 Hierarchy 中显示的名字)
        /// </summary>
        public string name;

        /// <summary>
        /// 节点在 Hierarchy 中的完整路径 (如 "Canvas/Panel/Button"), 便于人工定位
        /// </summary>
        public string path;

        /// <summary>
        /// 主要组件类型 (如 Text / Image / Button), 供外部解析工具识别控件种类
        /// </summary>
        public string objectType;

        /// <summary>
        /// 该节点自身是否含有文本, 供 "文本/图片剪枝树" 剪枝时判断节点去留
        /// </summary>
        public bool hasText;

        /// <summary>
        /// 该节点自身是否含有图片 (Image / RawImage), 供 "文本/图片剪枝树" 剪枝时一并保留图片节点
        /// </summary>
        public bool hasImage;

        /// <summary>
        /// 组件属性数据, 两层字典结构: 组件名 -> (属性名 -> 已格式化的 JSON 片段值)
        /// 例如: ObjectData["RectTransform"]["anchoredPosition"] = "{\"x\":0,\"y\":0}"
        /// 由 AddComponentProperty 写入, JsonBuilder 据此输出嵌套 JSON 对象
        /// </summary>
        public Dictionary<string, Dictionary<string, string>> ObjectData = new Dictionary<string, Dictionary<string, string>>();

        /// <summary>
        /// 子节点列表, 递归构成节点树
        /// </summary>
        public List<UINodeData> ChildNodes = new List<UINodeData>();

        /// <summary>
        /// 向 ObjectData 添加/覆盖一条组件属性
        /// 若对应组件的内层字典尚不存在, 会自动创建
        /// </summary>
        /// <param name="componentName">组件名 (外层 Key), 如 "Transform" / "Text"</param>
        /// <param name="propertyKey">属性名 (内层 Key), 如 "localScale"</param>
        /// <param name="propertyJsonValue">已格式化好的属性值 (JSON 片段字符串)</param>
        public void AddComponentProperty(string componentName, string propertyKey, string propertyJsonValue)
        {
            // 取出该组件对应的内层字典, 不存在则新建并挂入外层字典
            if (!ObjectData.TryGetValue(componentName, out var inner))
            {
                inner = new Dictionary<string, string>();
                ObjectData[componentName] = inner;
            }

            // 写入 (或覆盖) 属性值
            inner[propertyKey] = propertyJsonValue;
        }

        /// <summary>
        /// 尝试从 ObjectData 读取指定组件的指定属性值
        /// </summary>
        /// <param name="componentName">组件名 (外层 Key)</param>
        /// <param name="propertyKey">属性名 (内层 Key)</param>
        /// <param name="propertyJsonValue">输出参数: 命中时返回属性值, 未命中时为 null</param>
        /// <returns>组件与属性都存在时返回 true, 否则返回 false</returns>
        public bool TryGetComponentProperty(string componentName, string propertyKey, out string propertyJsonValue)
        {
            propertyJsonValue = null;
            // 外层命中组件 且 内层命中属性, 两者皆成立才算读取成功
            return ObjectData.TryGetValue(componentName, out var inner) && inner.TryGetValue(propertyKey, out propertyJsonValue);
        }
    }

    /// <summary>
    /// UI 导出结果: 一次 Dump 操作的完整产物
    /// 包含运行环境元数据 (分辨率 / 语言 / 画质等) 与场景 UI 节点树 nodes
    /// 会被 JsonBuilder 序列化为 ui_data_all.json (全量) 或 ui_data_text.json (文本/图片剪枝树)
    /// </summary>
    [Serializable]
    public class UIDumpResult
    {
        /// <summary>
        /// 当前激活场景的名称
        /// </summary>
        public string sceneName;

        /// <summary>
        /// 游戏客户端版本号 (Player Settings → Version)
        /// </summary>
        public string appVersion;

        /// <summary>
        /// Unity 引擎版本号
        /// </summary>
        public string unityVersion;

        /// <summary>
        /// 屏幕宽度 (像素)
        /// </summary>
        public int screenWidth;

        /// <summary>
        /// 屏幕高度 (像素)
        /// </summary>
        public int screenHeight;

        /// <summary>
        /// 屏幕 DPI (设备物理像素密度)
        /// </summary>
        public float screenDpi;

        /// <summary>
        /// 系统语言
        /// </summary>
        public string systemLanguage;

        /// <summary>
        /// 当前激活的 Layer 名称数组
        /// </summary>
        public string[] activeLayerNames;

        /// <summary>
        /// 屏幕方向 (如横屏 / 竖屏)
        /// </summary>
        public string orientation;

        /// <summary>
        /// 安全区域 (刘海屏等的可用显示区域)
        /// </summary>
        public Rect safeArea;

        /// <summary>
        /// 画质等级索引
        /// </summary>
        public int qualityLevel;

        /// <summary>
        /// 画质等级名称
        /// </summary>
        public string qualityLevelName;

        /// <summary>
        /// 颜色空间 (Linear / Gamma), 两端不一致时纯色块会明显偏亮或偏暗
        /// </summary>
        public string colorSpace;

        /// <summary>
        /// 目标帧率 (-1 表示未限制)
        /// </summary>
        public int targetFrameRate;

        /// <summary>
        /// 场景 UI 节点树的根节点列表 (通常每个 Canvas 对应一棵子树)
        /// </summary>
        public List<UINodeData> nodes = new List<UINodeData>();
    }
}