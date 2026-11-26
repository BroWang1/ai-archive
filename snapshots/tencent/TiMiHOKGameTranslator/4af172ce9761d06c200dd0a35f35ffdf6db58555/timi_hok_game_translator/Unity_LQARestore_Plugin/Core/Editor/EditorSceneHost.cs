// ==========================================
// 文件: LQARestore\Core\Editor\EditorSceneHost.cs
// 模块: Core.Editor (核心层 编辑器侧)
// ==========================================

using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using LQARestore.Core;

/// <summary>
/// LQARestore 核心层 编辑器侧命名空间
/// </summary>
namespace LQARestore.Core.Editor
{
    /// <summary>
    /// 场景宿主的编辑器实现, 实现 ISceneHost
    /// 职责:
    ///   - 新建承载还原对象的空场景;
    ///   - 反射设置 Game 视图分辨率, 使预览/截图与原始画面对齐;
    ///   - 用临时正交相机 + RenderTexture 把当前画面截图保存为 PNG;
    ///   - 把场景标记为脏, 让编辑器识别到内容变化;
    /// 设计要点:
    ///   - 把 EditorSceneManager / GameView 反射 / 相机渲染等编辑器专属操作集中在此,
    ///     使核心还原流程只依赖 ISceneHost 抽象而与平台解耦;
    ///   - GameView 相关 API 均为内部类型, 只能通过反射访问;
    ///   - 分辨率设置失败仅影响预览对齐, 做容错不中断还原; 截图涉及的临时对象在 finally 中彻底清理;
    /// </summary>
    public class EditorSceneHost : ISceneHost
    {
        /// <summary>
        /// 当前由本宿主新建/持有的还原场景, 供 MarkDirty 标记使用
        /// </summary>
        private UnityEngine.SceneManagement.Scene _scene;

        /// <summary>
        /// 新建一个空的单场景 (含默认对象) 作为还原容器, 并命名后记录到 _scene
        /// </summary>
        /// <param name="sceneName">新场景名称</param>
        public void NewRestoreScene(string sceneName)
        {
            _scene = EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            _scene.name = sceneName;
        }

        /// <summary>
        /// 设置 Game 视图分辨率 (ISceneHost.SetResolution 的实现)
        /// 通过反射操作内部类型 UnityEditor.GameViewSizes/GameViewSize: 先查找是否已有同尺寸,
        /// 没有则新增一个 FixedResolution 自定义尺寸, 最后选中它
        /// 该操作仅为改善预览对齐, 失败会被捕获并降级为警告, 不影响截图导出
        /// </summary>
        /// <param name="width">目标宽度 (像素), 非正数时直接忽略</param>
        /// <param name="height">目标高度 (像素), 非正数时直接忽略</param>
        /// <param name="label">新尺寸在 GameView 列表中的显示标签</param>
        public void SetResolution(int width, int height, string label)
        {
            if (width <= 0 || height <= 0) return;

            try
            {
                // GameView 相关类型均为编辑器程序集中的内部类型, 只能反射拿取
                var editorAsm      = typeof(EditorWindow).Assembly;
                var sizesType      = editorAsm.GetType("UnityEditor.GameViewSizes");
                var gvSizeType     = editorAsm.GetType("UnityEditor.GameViewSize");
                var gvSizeTypeEnum = editorAsm.GetType("UnityEditor.GameViewSizeType");

                // GameViewSizes 是 ScriptableSingleton<GameViewSizes>, 取其单例
                var singletonType = typeof(ScriptableSingleton<>).MakeGenericType(sizesType);
                var instance = singletonType
                    .GetProperty("instance", BindingFlags.Public | BindingFlags.Static)
                    .GetValue(null, null);

                // 当前分组 (随激活的 Build Target: Standalone / Android / iOS ...)
                var currentGroupType = sizesType.GetProperty("currentGroupType").GetValue(instance, null);
                var group = sizesType.GetMethod("GetGroup").Invoke(instance, new object[] { currentGroupType });
                var groupType = group.GetType();

                // 预取组内操作方法: 数量 / 按索引取尺寸 / 新增自定义尺寸
                var getTotalCount   = groupType.GetMethod("GetTotalCount");
                var getGameViewSize = groupType.GetMethod("GetGameViewSize");
                var addCustomSize   = groupType.GetMethod("AddCustomSize");

                var widthProp  = gvSizeType.GetProperty("width");
                var heightProp = gvSizeType.GetProperty("height");

                // 先查是否已存在同尺寸
                int index = -1;
                int total = (int)getTotalCount.Invoke(group, null);
                for (int i = 0; i < total; i++)
                {
                    var size = getGameViewSize.Invoke(group, new object[] { i });
                    if ((int)widthProp.GetValue(size, null) == width &&
                        (int)heightProp.GetValue(size, null) == height)
                    {
                        index = i;
                        break;
                    }
                }

                // 不存在则新增一个 FixedResolution (=1) 自定义尺寸
                if (index < 0)
                {
                    var ctor = gvSizeType.GetConstructor(
                        new[] { gvSizeTypeEnum, typeof(int), typeof(int), typeof(string) });
                    var fixedRes = Enum.ToObject(gvSizeTypeEnum, 1);
                    var newSize = ctor.Invoke(new object[] { fixedRes, width, height, label });
                    addCustomSize.Invoke(group, new[] { newSize });
                    // 新增后它排在列表末尾, 索引即为 总数-1
                    index = (int)getTotalCount.Invoke(group, null) - 1;
                }

                // 选中该尺寸 (GameView.selectedSizeIndex 为内部属性)
                var gameViewType = editorAsm.GetType("UnityEditor.GameView");
                var gameView = EditorWindow.GetWindow(gameViewType);
                gameViewType
                    .GetProperty("selectedSizeIndex",
                        BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)
                    .SetValue(gameView, index, null);

                Debug.Log($"[LQARestore][EditorSceneHost] 已将 Game 视图分辨率设为 {width}x{height} (index={index})");
            }
            catch (Exception e)
            {
                // 设 Game 视图分辨率纯粹为改善预览对齐, 失败不影响 Restore.png 导出
                Debug.LogWarning($"[LQARestore][EditorSceneHost] 设置 Game 视图分辨率失败: {e.Message}");
            }
        }

        /// <summary>
        /// 将当前场景渲染并截图保存为 PNG (ISceneHost.CaptureToPng 的实现)
        /// 流程: 建临时正交相机 → 把 ScreenSpaceOverlay 的 Canvas 临时切成 ScreenSpaceCamera
        /// (Overlay 模式不进相机渲染, 切换后才能被 RT 捕获) → 强制刷新布局 → 渲染到 RT →
        /// 读像素编码为 PNG 落盘; finally 中还原 Canvas 并销毁所有临时对象
        /// </summary>
        /// <param name="outPngPath">输出 PNG 的完整路径</param>
        /// <param name="width">渲染纹理/截图宽度 (像素)</param>
        /// <param name="height">渲染纹理/截图高度 (像素)</param>
        public void CaptureToPng(string outPngPath, int width, int height)
        {
            GameObject camGo = null;
            Camera     camera = null;
            RenderTexture rt = null;
            Texture2D  tex = null;

            // 备份被临时改成 ScreenSpaceCamera 的 Overlay Canvas, 用于还原
            var overlayBackup = new List<Tuple<Canvas, RenderMode, Camera, float>>();

            try
            {
                // 临时正交相机
                camGo  = new GameObject("LQA_CaptureCam");
                camera = camGo.AddComponent<Camera>();
                camera.clearFlags      = CameraClearFlags.SolidColor;
                camera.backgroundColor = Color.black;
                camera.orthographic    = true;
                camera.nearClipPlane   = 0.01f;
                camera.farClipPlane    = 100f;

                // 把所有 Overlay Canvas 临时切到 ScreenSpaceCamera, 才能被相机渲染进 RT
                foreach (var c in UnityEngine.Object.FindObjectsOfType<Canvas>())
                {
                    if (!c.enabled || c.renderMode != RenderMode.ScreenSpaceOverlay) continue;
                    // 先记录原始渲染参数, 供 finally 还原
                    overlayBackup.Add(new Tuple<Canvas, RenderMode, Camera, float>(
                        c, c.renderMode, c.worldCamera, c.planeDistance));
                    c.renderMode    = RenderMode.ScreenSpaceCamera;
                    c.worldCamera   = camera;
                    // 强制刷新布局, 保证文本网格已生成 (编辑模式必需)
                    c.planeDistance = camera.nearClipPlane + 0.01f;
                }

                // 强制刷新布局, 保证文本网格已生成 (编辑模式必需)
                Canvas.ForceUpdateCanvases();

                // 渲染到离屏 RenderTexture
                rt = new RenderTexture(width, height, 24);
                camera.targetTexture = rt;
                camera.Render();

                // 从 RT 读回像素到 Texture2D
                RenderTexture.active = rt;
                tex = new Texture2D(width, height, TextureFormat.RGB24, false);
                tex.ReadPixels(new Rect(0, 0, width, height), 0, 0);
                tex.Apply();
                RenderTexture.active = null;

                File.WriteAllBytes(outPngPath, tex.EncodeToPNG());
                Debug.Log($"[LQARestore][EditorSceneHost] 已保存还原画面: {outPngPath}");
            }
            catch (Exception e)
            {
                Debug.LogError($"[LQARestore][EditorSceneHost] 保存 Restore.png 失败: {e.Message}\n{e.StackTrace}");
            }
            finally
            {
                // 还原 Overlay Canvas 的原始渲染参数 (对象可能已被销毁, 需判空)
                foreach (var b in overlayBackup)
                {
                    if (b.Item1 != null)
                    {
                        b.Item1.renderMode    = b.Item2;
                        b.Item1.worldCamera   = b.Item3;
                        b.Item1.planeDistance = b.Item4;
                    }
                }
                // 编辑模式下必须用 DestroyImmediate (非播放态 Destroy 不会立即生效)
                if (camera != null) camera.targetTexture = null;
                RenderTexture.active = null;
                if (rt   != null) { rt.Release(); UnityEngine.Object.DestroyImmediate(rt); }
                if (tex  != null) UnityEngine.Object.DestroyImmediate(tex);
                if (camGo != null) UnityEngine.Object.DestroyImmediate(camGo);
            }
        }

        /// <summary>
        /// 将当前还原场景标记为脏, 使编辑器识别到内容变更 (一般在还原完成、截图之前调用)
        /// </summary>
        public void MarkDirty()
        {
            EditorSceneManager.MarkSceneDirty(_scene);
        }
    }
}