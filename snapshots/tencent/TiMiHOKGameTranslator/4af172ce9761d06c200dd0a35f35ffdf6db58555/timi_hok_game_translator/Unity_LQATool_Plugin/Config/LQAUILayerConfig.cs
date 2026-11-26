// ==========================================
// 文件: LQATool\Config\LQAUILayerConfig.cs
// 模块: Config (配置)
// ==========================================

using System.Collections.Generic;

/// <summary>
/// LQATool 配置层命名空间
/// </summary>
namespace LQATool.Config
{
    /// <summary>
    /// LQATool UI 相关的全局静态配置
    /// 集中存放 "分层截图" 与 "文本像素可见性判定" 两类流程所需的常量参数与调试开关,
    /// 供 UIDumpService / PixelVisibilityChecker 等服务在运行时读取
    /// </summary>
    public static class LQAUILayerConfig
    {
        /// <summary>
        /// 需要 "单独分层截图" 的 UI 图层 (Layer) 名称列表
        /// UIDumpService 会遍历本列表, 对其中每个在工程里真实存在的 Layer,
        /// 单独渲染出一张透明图 ScreenShot_Only_{LayerName}.png
        /// 所有未列入本列表的图层则合并渲染为背景图 ScreenShot_BG.png
        /// 注意: 列表中若配置了工程中不存在的 Layer 名, 会被自动跳过并打印警告
        /// Dump 时会对本列表做一次快照, 作为 "本次输出了哪些分层截图" 的权威清单
        /// 说明: 上述分层图与背景图的实际落盘受 EmitLayerScreenshots 开关控制,
        /// 该开关关闭时本列表仅用于快照记录, 不再触发任何分层/背景截图的渲染与写盘
        /// </summary>
        public static readonly List<string> UILayerNames = new List<string>
        {
            "UI",

            "UI_System",
            "UI_Background",
        };

        /// <summary>
        /// 文本可见性判定的 "差异占比" 阈值 (取值 0~1)
        /// 判定逻辑: 在文本的屏幕足迹范围内, 统计 "有文本" 与 "无文本" 两张图的差异像素数,
        /// 当差异像素数 / 足迹像素总数 大于该比例时, 才判定该文本为可见
        /// 当前 0.10 表示: 至少要有 10% 的足迹像素发生显著变化才算可见
        /// </summary>
        public const float PixelDiffMaskVisibleRatio = 0.10f;

        /// <summary>
        /// 单像素 "颜色差异显著" 的判定阈值
        /// 对同一像素在 "有文本" 与 "无文本" 两图中的 RGB 三通道差值求和,
        /// 该和值大于此阈值时, 才认为这个像素发生了显著变化 (计入差异像素数)
        /// 值越小越敏感, 越容易把细微色差算作差异
        /// </summary>
        public const int PixelDiffColorThreshold = 12;

        /// <summary>
        /// 纯色 ID 掩码 "有效足迹像素" 的最小 alpha 阈值 (0~255)
        /// 纯色 ID 图背景透明、文字以不透明 ID 色渲染; 抗锯齿会让字形边缘像素呈半透明,
        /// 仅 alpha >= 本值的像素才计入文本足迹参与判定 (用于筛掉边缘羽化的脏像素)
        /// 128 相当于要求覆盖率 >= 50%; 对小字号/细笔画文本 (如 16px 中文) 可调低 (如 64),
        /// 以纳入更多边缘像素, 避免足迹被筛空导致误判为不可见
        /// </summary>
        public const int PureMaskAlphaThreshold = 128;

        /// <summary>
        /// 调试开关: 是否把文本 ID 图 (含纯色版) 额外另存为 PNG, 便于人工核对文本足迹映射
        /// 关闭后仅在内存中参与判定, 不落盘调试图
        /// </summary>
        public const bool EmitTextIdMapDebug = true;

        /// <summary>
        /// 调试开关: 是否输出可见性判定的中间过程数据与可视化叠加图
        /// (叠加图中 绿=可见 / 红=可见但露出像素少 / 橙=不可见), 用于排查判定结果
        /// </summary>
        public const bool EmitVisibilityDebug = true;

        /// <summary>
        /// 输出开关: 是否落盘全量 UI 节点树 ui_data_all.json
        /// 与 ui_data_text.json 的差异仅在于节点范围: 本文件保留每个根 Canvas 下的全部节点,
        /// 而 text 版只保留含文本或图片的节点及其祖先路径, 两者对每个节点记录的字段口径完全一致
        /// (除 name / Transform / RectTransform / GameObject 等通用信息外, 也含 Text / Image 等组件的专有属性)
        /// 关闭后仅跳过本文件写盘, 内存中的全量树仍会构建 (它是 text 版的过滤来源),
        /// 不影响 ui_data_text.json 的写盘 (由 EmitTextUIDataJson 独立控制)
        /// </summary>
        public const bool EmitFullUIDataJson = false;

        /// <summary>
        /// 输出开关: 是否落盘文本/图片剪枝版 UI 节点树 ui_data_text.json
        /// 该文件只保留含文本或图片的节点及其祖先路径, 是 EmitFullUIDataJson 全量树的过滤子集
        /// 关闭后仅跳过本文件写盘, 内存中的文本树仍会构建, 不影响全量树 ui_data_all.json 的生成
        /// </summary>
        public const bool EmitTextUIDataJson = true;

        /// <summary>
        /// 输出开关: 是否落盘分层截图 (ScreenShot_Only_{Layer}.png) 与背景截图 (ScreenShot_BG.png)
        /// 这几张图为纯产物, 无任何下游流程读回消费, 仅供人工核对分层效果
        /// 关闭后整段分层/背景渲染与写盘逻辑都会跳过 (顺带省一轮 GPU 回读与磁盘 IO),
        /// 不影响 ScreenShot_Full / ScreenShot_NoText 及像素可见性判定、JSON 生成、工程还原
        /// </summary>
        public const bool EmitLayerScreenshots = false;
    }
}