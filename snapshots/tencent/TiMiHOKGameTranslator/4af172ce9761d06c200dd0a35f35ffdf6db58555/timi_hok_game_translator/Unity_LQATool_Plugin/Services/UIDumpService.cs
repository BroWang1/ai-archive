// ==========================================
// 文件: LQATool\Services\UIDumpService.cs
// 模块: Services (业务)
// ==========================================

using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.UI;
using LQATool.Utils;
using LQATool.Config;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// UIDumpService —— UI 转储服务的主入口 (分部类)
    ///
    /// 本文件负责编排一次完整的 UI Dump 流程, 产出一组用于 LQA (本地化质量保证) 分析的素材:
    ///   1. ScreenShot_Full.png —— 当前完整画面 (含文本)
    ///   2. ScreenShot_NoText.png —— 隐藏所有文本后的画面 (供与完整图做像素差分)
    ///   3. ScreenShot_TextId(_Pure).png —— 文本 ID 染色图 (可选调试输出, 见 TextIdMap 分部)
    ///   4. ScreenShot_Only_{Layer}.png / ScreenShot_BG.png —— 按图层拆分的截图 (可选)
    ///   5. UI 节点树 JSON (见 NodeTree 分部)
    /// 并借助 PixelVisibilityChecker 判定每个文本是否真正可见 (未被遮挡/裁剪)
    ///
    /// 其余底层能力拆分在同名分部类文件中:
    ///   - UIDumpService.Screenshot.cs : 相机/Overlay 画布配置与还原、RT 读回存 PNG
    ///   - UIDumpService.TextIdMap.cs : 文本 ID 染色图的生成
    ///   - UIDumpService.NodeTree.cs : UI 节点树遍历与 JSON 导出
    ///   - UIDumpService.GetNode.cs : 单节点数据提取
    /// </summary>
    public partial class UIDumpService
    {
        /// <summary>
        /// 相机关键属性的备份结构, 用于在截图前修改、截图后原样还原
        /// (实际使用见 UIDumpService.Screenshot.cs 的 SetupCamerasForLayerMask / RestoreCameras)
        /// </summary>
        private struct CameraState
        {
            /// <summary>
            /// 清屏标志 (SolidColor / Depth 等)
            /// </summary>
            public CameraClearFlags clearFlags;

            /// <summary>
            /// 相机背景色
            /// </summary>
            public Color backgroundColor;

            /// <summary>
            /// 渲染层掩码 (决定相机渲染哪些 Layer)
            /// </summary>
            public int cullingMask;

            /// <summary>
            /// 渲染目标纹理 (为 null 时渲染到屏幕)
            /// </summary>
            public RenderTexture targetTexture;
        }

        /// <summary>
        /// 执行一次完整的 UI 转储 (协程形式, 需要跨帧等待 WaitForEndOfFrame 以确保渲染完成)
        ///
        /// 流程概览:
        ///   1. 建输出目录并暂停游戏 (timeScale=0)、隐藏工具自身 UI
        ///   2. 截取完整画面
        ///   3. 临时隐藏所有文本 (含阴影), 截取无文本画面, 随后还原
        ///   4. 生成文本 ID 图并进行像素可见性判定
        ///   5. (可选) 输出可见性叠加图、按图层拆分的截图
        ///   6. 导出 UI 节点树 JSON
        ///   7. finally 中恢复现场: 时间流速、工具 UI、清缓存, 并回调 onComplete
        /// </summary>
        /// <param name="toolCanvas">工具自身的 Canvas, 截图时需隐藏/排除, 避免拍进工具面板</param>
        /// <param name="onComplete">流程结束后的回调 (成功或失败都会触发)</param>
        public IEnumerator ExecuteDump(Canvas toolCanvas, Action onComplete)
        {
            // 以当前时间生成唯一时间戳, 作为本次 Dump 输出目录名的一部分
            string timestamp = DateTime.Now.ToString("yyyy_MM_dd_HH_mm_ss");
            // 输出目录位于持久化数据路径下: persistentDataPath/LQATool/UIDump_yyyy_MM_dd_HH_mm_ss
            string dirPath = Path.Combine(Application.persistentDataPath, "LQATool", $"UIDump_{timestamp}");
            if (!Directory.Exists(dirPath)) Directory.CreateDirectory(dirPath);

            // 备份并暂停游戏时间, 冻结画面, 保证多次截图捕获的是同一帧内容
            float originalTimeScale = Time.timeScale;
            Time.timeScale = 0f;

            // 隐藏工具自身的 UI, 避免它出现在截图里
            toolCanvas.enabled = false;

            // 等到本帧渲染结束, 使 "隐藏工具 UI" 已经生效再截图
            yield return new WaitForEndOfFrame();

            // 记录当前屏幕分辨率, 作为后续所有 截图/RT 的尺寸
            int width = Screen.width;
            int height = Screen.height;

            // 收集本次需要参与 "可见性判定" 的候选文本 (排除工具自身画布内的文本)
            List<TextLike> dumpTexts = UITextCollector.CollectVisibilityCandidates(toolCanvas);

            // 1. 截取完整画面 (含文本)
            try
            {
                SaveTexture(new Rect(0, 0, width, height), Path.Combine(dirPath, "ScreenShot_Full.png"), TextureFormat.RGB24);
            }
            catch (Exception e)
            {
                Debug.LogError($"[LQATool][UIDumpService] 截取完整画面失败: {e.Message}\n{e.StackTrace}");
            }

            // 记录被隐藏文本的原始 CanvasRenderer alpha, 用于截完无文本图后还原
            var textAlphaBackups = new List<KeyValuePair<CanvasRenderer, float>>();
            // 记录被隐藏文本阴影 (Shadow/Outline) 的原始颜色, 用于还原
            var shadowColorBackups = new List<KeyValuePair<Shadow, Color>>();

            // 2. 临时隐藏所有候选文本及其阴影 (通过把 alpha 置 0)
            try
            {
                // 复用缓冲区, 避免每个文本一次 List 分配
                var rendererBuf = new List<CanvasRenderer>();
                foreach (var t in dumpTexts)
                {
                    // t.graphic 为底层图形组件 (Text 或 TMP)
                    if (t.graphic != null && t.graphic.enabled)
                    {
                        // 收集该文本的所有渲染器 (TMP 含子 SubMesh), 逐个隐藏并备份
                        // (仅隐藏主体 CanvasRenderer 会漏掉 fallback 字体的子网格, 导致 NoText 图残留文字)
                        t.CollectRenderers(rendererBuf);
                        foreach (var cr in rendererBuf)
                        {
                            if (cr == null) continue;
                            textAlphaBackups.Add(new KeyValuePair<CanvasRenderer, float>(cr, cr.GetAlpha()));
                            cr.SetAlpha(0f);
                        }

                        // Shadow/Outline 仅旧版 Text 常见; TMP 无此组件, GetComponents 返回空数组自然跳过
                        Shadow[] shadows = t.graphic.GetComponents<Shadow>();
                        foreach (var shadow in shadows)
                        {
                            if (shadow != null && shadow.enabled)
                            {
                                shadowColorBackups.Add(new KeyValuePair<Shadow, Color>(shadow, shadow.effectColor));
                                Color sc = shadow.effectColor;
                                sc.a = 0f;
                                shadow.effectColor = sc;
                            }
                        }
                    }
                }
            }
            catch (Exception e)
            {
                Debug.LogError($"[LQATool][UIDumpService] 隐藏文本组件失败: {e.Message}\n{e.StackTrace}");
            }

            // 等一帧, 让 "隐藏文本" 的改动真正反映到画面上
            yield return new WaitForEndOfFrame();

            // 3. 截取无文本画面 (与 Full 图差分, 可用于判断文本占位/可见性)
            try
            {
                SaveTexture(new Rect(0, 0, width, height), Path.Combine(dirPath, "ScreenShot_NoText.png"), TextureFormat.RGB24);
            }
            catch (Exception e)
            {
                Debug.LogError($"[LQATool][UIDumpService] 截取无文本画面失败: {e.Message}\n{e.StackTrace}");
            }

            // 还原被隐藏的阴影颜色 (对象可能已销毁, 判空)
            foreach (var kvp in shadowColorBackups)
            {
                if (kvp.Key != null) kvp.Key.effectColor = kvp.Value;
            }

            // 还原被隐藏文本 (含 TMP SubMesh) 的 CanvasRenderer alpha (对象可能已销毁, 判空)
            foreach (var kvp in textAlphaBackups)
            {
                if (kvp.Key != null) kvp.Key.SetAlpha(kvp.Value);
            }

            // 等一帧, 确保文本还原后再进行后续基于渲染的处理
            yield return new WaitForEndOfFrame();

            // 4~5 文本 ID 图 / 可见性判定 / 分层截图 / JSON 导出
            try
            {
                // 创建离屏渲染用的 RenderTexture (带 alpha 通道, 24 位深度)
                RenderTexture rt = new RenderTexture(width, height, 24, RenderTextureFormat.ARGB32);
                // 取场景所有相机 (按 depth 升序), 若场景无相机则创建临时相机兜底 (tempCam)
                Camera[] cameras = GetSortedCameras(out Camera tempCam);
                // 最上层相机 (depth 最大), 用于承载临时切换为 Camera 模式的 Overlay 画布
                Camera topCamera = cameras[cameras.Length - 1];

                // 文本 ID 图相关的输出:
                //   textIdMap —— 常规染色 ID 图逐像素颜色
                //   pureTextIdMap —— 隐藏非文本图形后的纯净 ID 图
                //   textToId —— 文本 Transform → 分配到的 ID
                Color32[] textIdMap = null;
                Color32[] pureTextIdMap = null;
                Dictionary<Transform, int> textToId = null;
                try
                {
                    textIdMap = CaptureTextIdMap(cameras, topCamera, rt, width, height, toolCanvas, dumpTexts, dirPath, out textToId, out pureTextIdMap);
                }
                catch (Exception e)
                {
                    // 染色图捕获失败时: 置空 ID 图, 后续可见性判定会把所有文本按不可见处理 (安全降级)
                    textIdMap = null;
                    pureTextIdMap = null;
                    Debug.LogError($"[LQATool][UIDumpService] 文本 ID 图捕获失败 (本次将无法判定可见性, 所有文本按不可见处理): {e.Message}\n{e.StackTrace}");
                }

                // 基于 ID 图 + 像素差分, 为本场景构建 "文本是否可见" 的判定缓存
                try
                {
                    PixelVisibilityChecker.BuildCacheForScene(
                        dirPath,
                        dumpTexts,
                        textIdMap,
                        pureTextIdMap,
                        textToId,
                        LQAUILayerConfig.PixelDiffColorThreshold,  // 像素颜色差异阈值
                        LQAUILayerConfig.PixelDiffMaskVisibleRatio,  // 判定为可见所需的最小像素占比
                        LQAUILayerConfig.PureMaskAlphaThreshold  // 纯色掩码有效足迹的最小 alpha
                    );
                }
                catch (Exception e)
                {
                    Debug.LogError($"[LQATool][UIDumpService] 像素差分判定失败 (缓存为空, 所有文本按不可见处理): {e.Message}\n{e.StackTrace}");
                }

                // (可选) 输出可见性叠加调试图, 便于人工核对判定结果
                if (LQAUILayerConfig.EmitVisibilityDebug)
                {
                    try
                    {
                        PixelVisibilityChecker.SaveVisibilityOverlay(dirPath, width, height);
                    }
                    catch (Exception e)
                    {
                        Debug.LogError($"[LQATool][UIDumpService] 可见性叠加图输出失败: {e.Message}\n{e.StackTrace}");
                    }
                }

                // 5. (可选) 按图层拆分截图: 每个配置图层单独出一张, 再出一张剩余背景图
                if (LQAUILayerConfig.EmitLayerScreenshots)
                {
                    // 所有有效配置图层的合并掩码 (用于最后反推 "背景" 掩码)
                    int configuredLayerMask = 0;
                    // 配置中真实存在于工程的图层列表 (图层名, 单图层掩码)
                    var validLayers = new List<KeyValuePair<string, int>>();

                    // 逐个解析配置的图层名: 存在则加入列表并累加到合并掩码, 不存在则告警跳过
                    foreach (string layerName in LQAUILayerConfig.UILayerNames)
                    {
                        int layerIndex = LayerMask.NameToLayer(layerName);
                        if (layerIndex >= 0)
                        {
                            int layerMask = 1 << layerIndex;
                            validLayers.Add(new KeyValuePair<string, int>(layerName, layerMask));
                            configuredLayerMask |= layerMask;
                        }
                        else
                        {
                            Debug.LogWarning($"[LQATool][UIDumpService] LQAUILayerConfig 中配置的 Layer \"{layerName}\" 在当前工程中不存在, 已跳过");
                        }
                    }

                    // 为每个有效图层单独渲染一张 "只含该图层" 的透明截图
                    foreach (var layerPair in validLayers)
                    {
                        string layerName = layerPair.Key;
                        int singleLayerMask = layerPair.Value;

                        // 配置相机只渲染该图层 + 处理 Overlay 画布, 渲染到 RT 后存 PNG, 再逐一还原
                        RenderLayerMaskToPng(cameras, rt, topCamera, toolCanvas, singleLayerMask,
                            width, height, Path.Combine(dirPath, $"ScreenShot_Only_{layerName}.png"));
                    }

                    // 再输出一张 "背景图": 即所有配置图层以外的内容
                    if (configuredLayerMask != 0)
                    {
                        // 背景图 = 所有配置图层以外的内容 (掩码按位取反)
                        int bgMask = ~configuredLayerMask;
                        RenderLayerMaskToPng(cameras, rt, topCamera, toolCanvas, bgMask,
                            width, height, Path.Combine(dirPath, "ScreenShot_BG.png"));
                    }
                    else
                    {
                        // 没有任何有效图层配置时的兜底: 背景图直接渲染全部图层 (layerMask = -1)
                        Debug.LogWarning("[LQATool][UIDumpService] LQAUILayerConfig.UILayerNames 中没有任何有效的图层配置, ScreenShot_BG.png 将包含所有图层的渲染结果");
                        RenderLayerMaskToPng(cameras, rt, topCamera, toolCanvas, -1,
                            width, height, Path.Combine(dirPath, "ScreenShot_BG.png"));
                    }
                }

                // 销毁离屏 RT, 释放显存
                UnityEngine.Object.Destroy(rt);
                // 若使用了兜底临时相机, 连同其 GameObject 一并销毁
                if (tempCam != null) UnityEngine.Object.Destroy(tempCam.gameObject);

                // 6. 遍历 UI 节点树并导出为 JSON (排除工具自身画布)
                GenerateJsonData(toolCanvas, dirPath);
            }
            catch (Exception e)
            {
                Debug.LogError($"[LQATool][UIDumpService] 转储失败: {e.Message}\n{e.StackTrace}");
            }
            finally
            {
                // 7. 无论成功或失败都必须恢复现场:
                // 还原游戏时间流速
                Time.timeScale = originalTimeScale;
                // 清理可见性判定缓存, 避免残留影响下次 Dump
                PixelVisibilityChecker.ClearCache();
                // 重新显示工具自身 UI
                toolCanvas.enabled = true;
                // 触发完成回调 (可能为 null)
                onComplete?.Invoke();

                Debug.Log($"[LQATool][UIDumpService] 转储完成! 路径: {dirPath}");
            }
        }
    }
}