// ==========================================
// 文件: LQARestore\Core\Runtime\ISceneHost.cs
// 模块: Core (核心层)
// ==========================================

/// <summary>
/// LQARestore 核心层命名空间
/// </summary>
namespace LQARestore.Core
{
    /// <summary>
    /// 场景宿主抽象: 负责与 Unity 场景/相机/GameView 交互的一组底层能力,
    /// 包括: 新建场景 / 设置分辨率 / 截图 / 标记场景为脏
    /// 设计目的: 将平台相关操作 (EditorSceneManager、GameView 反射、相机渲染等)
    ///           与核心还原流程解耦, 核心逻辑只依赖此接口而不依赖具体实现
    /// 默认 Editor 实现 (EditorSceneHost) 采用 EditorSceneManager 建场景、
    /// 反射 UnityEditor.GameView 设置分辨率、临时正交相机 + RenderTexture 截图
    /// </summary>
    public interface ISceneHost
    {
        /// <summary>
        /// 新建一个用于文本还原的空场景, 并命名
        /// 调用后当前场景会被替换为这个干净场景, 作为后续还原对象的承载容器
        /// </summary>
        /// <param name="sceneName">新场景的名称, 例如 "LQA_Restore_Scene"</param>
        void NewRestoreScene(string sceneName);

        /// <summary>
        /// 设置 Game 视图 (预览) 的分辨率
        /// 通常传入 dump 中记录的原始屏幕宽高, 使还原预览与截图对齐原始画面
        /// 说明: 该操作仅用于改善预览/截图的对齐效果; 即便设置失败也不应中断
        ///       整个还原流程 (实现中应对失败做容错处理)
        /// </summary>
        /// <param name="width">目标分辨率宽度 (像素), 应为正数, 否则实现可忽略</param>
        /// <param name="height">目标分辨率高度 (像素), 应为正数, 否则实现可忽略</param>
        /// <param name="label">该分辨率在 GameView 尺寸列表中的显示标签, 例如 "LQA_Restore"</param>
        void SetResolution(int width, int height, string label);

        /// <summary>
        /// 将当前场景画面渲染并截图保存为 PNG 文件
        /// 用于产出还原结果图 (Restore.png) 以便与原始 dump 画面对比
        /// 实现要点 (以 EditorSceneHost 为例): 使用临时正交相机 + RenderTexture 渲染,
        /// 并将 ScreenSpaceOverlay 的 Canvas 临时切换为 ScreenSpaceCamera 以便被相机捕获,
        /// 截图完成后需还原这些临时改动
        /// </summary>
        /// <param name="outPngPath">输出 PNG 文件的完整路径，例如 dumpDir/Restore.png。</param>
        /// <param name="width">截图/渲染纹理的宽度 (像素)。</param>
        /// <param name="height">截图/渲染纹理的高度 (像素)。</param>
        void CaptureToPng(string outPngPath, int width, int height);

        /// <summary>
        /// 将当前场景标记为 "脏" (已修改)
        /// 使 Unity 编辑器识别到场景内容发生变化, 从而允许保存等操作
        /// 一般在完成对象还原之后、截图之前调用
        /// </summary>
        void MarkDirty();
    }
}