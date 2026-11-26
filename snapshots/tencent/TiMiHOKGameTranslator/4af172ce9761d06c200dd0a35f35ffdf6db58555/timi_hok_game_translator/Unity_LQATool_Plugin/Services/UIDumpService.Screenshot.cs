// ==========================================
// 文件: LQATool\Services\UIDumpService.Screenshot.cs
// 模块: Services (业务)
// ==========================================

using System;
using System.IO;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// LQATool 业务层命名空间
/// </summary>
namespace LQATool.Services
{
    /// <summary>
    /// UIDumpService 的截图子模块 (分部类)
    /// 类的整体职责说明见主定义文件 UIDumpService.cs
    /// 本文件仅封装截图过程中的底层操作: 相机 (Camera) 的临时配置与还原、覆盖层画布 (Overlay Canvas) 的模式切换与还原,
    /// 以及渲染纹理 (RenderTexture) 的像素读回并编码为 PNG
    /// </summary>
    public partial class UIDumpService
    {
        /// <summary>
        /// 从 "当前激活的渲染目标" 中读回像素, 并编码为 PNG 写入磁盘
        /// 说明: ReadPixels 读取的是当前 RenderTexture.active (或屏幕帧缓冲) 的内容,
        /// 因此调用前必须先把目标 RT 设为 active (见 SaveTextureFromRT)
        /// </summary>
        /// <param name="rect">读取区域 (以像素为单位, 原点在左下角), 通常为整张纹理的尺寸</param>
        /// <param name="path">PNG 文件的完整输出路径</param>
        /// <param name="format">临时纹理格式, RGBA32 可保留 alpha 通道输出透明图</param>
        private void SaveTexture(Rect rect, string path, TextureFormat format)
        {
            // 创建一块与读取区域等大的临时纹理, 最后一个参数 false 表示不生成 mipmap
            Texture2D tex = new Texture2D((int)rect.width, (int)rect.height, format, false);

            // 把当前激活渲染目标 rect 区域的像素读入 tex, 写入位置为 tex 的 (0,0)
            tex.ReadPixels(rect, 0, 0);
            // 提交像素改动, 使 ReadPixels 的结果在 tex 中生效
            tex.Apply();

            // 编码为 PNG 字节流并一次性写入文件
            File.WriteAllBytes(path, tex.EncodeToPNG());
            // 临时纹理用完立即销毁, 避免占用内存/显存
            UnityEngine.Object.Destroy(tex);
        }

        /// <summary>
        /// 将指定 RenderTexture 的内容保存为 PNG
        /// 相比 SaveTexture, 本方法额外负责设置/清理 RenderTexture.active, 使读回作用于该 RT
        /// </summary>
        /// <param name="rt">源渲染纹理</param>
        /// <param name="width">读取宽度 (像素)</param>
        /// <param name="height">读取高度 (像素)</param>
        /// <param name="path">PNG 文件的完整输出路径</param>
        /// <param name="format">保存格式, 透明图使用 RGBA32</param>
        private void SaveTextureFromRT(RenderTexture rt, int width, int height, string path, TextureFormat format)
        {
            // 将该 RT 设为当前激活渲染目标, 后续 ReadPixels 才会读取它的内容
            RenderTexture.active = rt;
            // 从 (0,0) 起读取整张 RT 并保存
            SaveTexture(new Rect(0, 0, width, height), path, format);
            // 还原 active, 避免影响后续其他渲染读回操作
            RenderTexture.active = null;
        }

        /// <summary>
        /// 获取场景中所有相机, 并按 depth 从小到大排序 (depth 越大越在上层, 越后渲染)
        /// 若场景中一个相机都没有, 则创建一个临时相机兜底, 保证截图流程可继续
        /// </summary>
        /// <param name="tempCam">
        /// 出参: 兜底创建的临时相机引用, 若场景本就有相机则为 null
        /// 调用方在截图结束后需负责销毁这个临时相机 (连同其 GameObject)
        /// </param>
        /// <returns>按 depth 升序排列的相机数组</returns>
        private Camera[] GetSortedCameras(out Camera tempCam)
        {
            // 查找场景内所有 Camera 组件 (不含未激活对象上的相机)
            Camera[] cameras = UnityEngine.Object.FindObjectsOfType<Camera>();
            // 按 depth 升序排序: 保证渲染顺序与实际叠加顺序一致
            Array.Sort(cameras, (a, b) => a.depth.CompareTo(b.depth));

            tempCam = null;

            // 极端情况: 场景没有任何相机, 创建一个临时相机作为兜底
            if (cameras.Length == 0)
            {
                GameObject camObj = new GameObject("LQATool_TempCamera");
                tempCam = camObj.AddComponent<Camera>();
                cameras = new Camera[] { tempCam };
            }

            return cameras;
        }

        /// <summary>
        /// 为 "按图层截图" 配置所有相机, 并把每个相机的原始状态备份返回
        /// 具体改动: 统一渲染到同一张 RT、背景清为全透明、按需只保留目标 Layer, 并串联清屏标志
        /// </summary>
        /// <param name="cameras">已按 depth 升序排列的相机数组</param>
        /// <param name="rt">统一的渲染目标纹理</param>
        /// <param name="layerMask">目标图层掩码 (当 preserveCullingMask 为 false 时生效)</param>
        /// <param name="preserveCullingMask">
        /// 为 true 时保留相机原有 cullingMask (不按图层过滤), 用于需要渲染相机全部内容的场景
        /// </param>
        /// <returns>相机 -> 原始状态 的映射, 供 RestoreCameras 还原</returns>
        private Dictionary<Camera, CameraState> SetupCamerasForLayerMask(
            Camera[] cameras, RenderTexture rt, int layerMask, bool preserveCullingMask = false)
        {
            var states = new Dictionary<Camera, CameraState>();

            for (int i = 0; i < cameras.Length; i++)
            {
                // 先备份当前相机的关键属性, 后续才能原样还原
                states[cameras[i]] = new CameraState
                {
                    clearFlags = cameras[i].clearFlags,
                    backgroundColor = cameras[i].backgroundColor,
                    cullingMask = cameras[i].cullingMask,
                    targetTexture = cameras[i].targetTexture
                };

                // 仅在不要求保留原掩码时, 才把渲染层限制为目标图层
                if (!preserveCullingMask)
                    cameras[i].cullingMask = layerMask;

                // 背景清为全透明, 保证输出的是带 alpha 通道的透明图
                cameras[i].backgroundColor = Color.clear;

                // 第一个 (最底层) 相机用 SolidColor 清屏建立透明底,
                // 其余相机只清深度 (Depth), 以便逐层叠加而不擦掉前面已渲染的内容
                cameras[i].clearFlags = (i == 0) ? CameraClearFlags.SolidColor : CameraClearFlags.Depth;

                // 所有相机统一渲染到同一张 RT
                cameras[i].targetTexture = rt;
            }

            return states;
        }

        /// <summary>
        /// 根据备份的状态还原所有相机, 撤销 SetupCamerasForLayerMask 的破坏性修改
        /// 若不还原, 截图结束后游戏画面会异常 (黑屏或只剩 UI)
        /// </summary>
        /// <param name="states">SetupCamerasForLayerMask 返回的原始状态映射</param>
        private void RestoreCameras(Dictionary<Camera, CameraState> states)
        {
            foreach (var kvp in states)
            {
                // 相机可能在截图期间被销毁, 需判空后再还原
                if (kvp.Key != null)
                {
                    kvp.Key.clearFlags = kvp.Value.clearFlags;
                    kvp.Key.backgroundColor = kvp.Value.backgroundColor;
                    kvp.Key.cullingMask = kvp.Value.cullingMask;
                    kvp.Key.targetTexture = kvp.Value.targetTexture;
                }
            }
        }

        /// <summary>
        /// 驱动所有相机按顺序手动渲染一帧到指定 RT
        /// 使用 Camera.Render() 主动触发离屏渲染, 而不依赖引擎的自动渲染循环
        /// </summary>
        /// <param name="cameras">已按 depth 升序排列的相机数组</param>
        /// <param name="rt">目标渲染纹理</param>
        private void RenderCamerasToRT(Camera[] cameras, RenderTexture rt)
        {
            foreach (var cam in cameras)
            {
                // 暂存该相机当前的渲染目标 (调用方通常已设为 rt, 这里再兜底保存/还原一次)
                var oldTarget = cam.targetTexture;
                cam.targetTexture = rt;

                // 立即执行一次离屏渲染, 结果写入 rt
                cam.Render();

                // 还原该相机自身的渲染目标
                cam.targetTexture = oldTarget;
            }
        }

        /// <summary>
        /// 临时把场景中所有 ScreenSpaceOverlay 模式的 Canvas 切换为 ScreenSpaceCamera 模式
        /// 原因: Overlay 画布直接贴屏幕、绕过相机, 无法被 RenderTexture 捕获
        /// 切成 Camera 模式并挂到最上层相机后, 才能一并渲染进 RT
        /// 同时会记录每个被修改画布的原始状态, 供 RestoreOverlayCanvases 还原
        /// </summary>
        /// <param name="topCam">最上层相机, 作为切换后画布的 worldCamera</param>
        /// <param name="ignoreCanvas">需要跳过的画布 (通常是工具自身的 UI 画布, 避免被截入)</param>
        /// <returns>被修改画布的原始状态列表 (Canvas, 原 renderMode, 原 worldCamera, 原 planeDistance)</returns>
        private List<Tuple<Canvas, RenderMode, Camera, float>> SetupOverlayCanvases(Camera topCam, Canvas ignoreCanvas)
        {
            var states = new List<Tuple<Canvas, RenderMode, Camera, float>>();

            foreach (var c in UnityEngine.Object.FindObjectsOfType<Canvas>())
            {
                // 跳过要忽略的画布和未启用的画布
                if (c == ignoreCanvas || !c.enabled) continue;

                if (c.renderMode == RenderMode.ScreenSpaceOverlay)
                {
                    // 备份原始状态: 画布本身 + 渲染模式 + 世界相机 + 平面距离
                    states.Add(new Tuple<Canvas, RenderMode, Camera, float>(
                        c, c.renderMode, c.worldCamera, c.planeDistance));

                    // 切换为 Camera 模式并绑定到最上层相机, 使其可被 RT 捕获
                    c.renderMode = RenderMode.ScreenSpaceCamera;
                    c.worldCamera = topCam;

                    // 平面距离略大于近裁剪面, 保证画布位于相机可视范围内且贴近屏幕
                    c.planeDistance = topCam.nearClipPlane + 0.01f;
                }
            }

            return states;
        }

        /// <summary>
        /// 根据备份状态还原所有被修改过的 Overlay 画布, 撤销 SetupOverlayCanvases 的改动
        /// </summary>
        /// <param name="states">SetupOverlayCanvases 返回的原始状态列表</param>
        private void RestoreOverlayCanvases(List<Tuple<Canvas, RenderMode, Camera, float>> states)
        {
            foreach (var state in states)
            {
                // 画布可能已被销毁, 需判空后再还原
                if (state.Item1 != null)
                {
                    state.Item1.renderMode = state.Item2;  // 还原渲染模式
                    state.Item1.worldCamera = state.Item3;  // 还原世界相机
                    state.Item1.planeDistance = state.Item4;  // 还原平面距离
                }
            }
        }

        /// <summary>
        /// 按指定图层掩码渲染一帧并保存为透明 PNG (RGBA32)
        /// 封装 "配置相机 → 切换 Overlay 画布 → 渲染到 RT → 存图 → 还原现场" 的固定流程,
        /// 供分层截图 (单图层 / 背景层 / 全图层兜底) 复用
        /// </summary>
        /// <param name="cameras">场景所有相机 (已按 depth 升序排序)</param>
        /// <param name="rt">离屏渲染用的 RenderTexture</param>
        /// <param name="topCamera">最上层相机 (承载临时切换为 Camera 模式的 Overlay 画布)</param>
        /// <param name="toolCanvas">工具自身的 Canvas, 需排除, 避免拍进工具面板</param>
        /// <param name="layerMask">目标图层掩码 (-1 表示全部图层)</param>
        /// <param name="width">读取宽度 (像素)</param>
        /// <param name="height">读取高度 (像素)</param>
        /// <param name="path">PNG 输出的完整路径</param>
        private void RenderLayerMaskToPng(
            Camera[] cameras, RenderTexture rt, Camera topCamera, Canvas toolCanvas,
            int layerMask, int width, int height, string path)
        {
            var camStates = SetupCamerasForLayerMask(cameras, rt, layerMask);
            var overlayStates = SetupOverlayCanvases(topCamera, toolCanvas);
            RenderCamerasToRT(cameras, rt);
            SaveTextureFromRT(rt, width, height, path, TextureFormat.RGBA32);
            RestoreCameras(camStates);
            RestoreOverlayCanvases(overlayStates);
        }
    }
}