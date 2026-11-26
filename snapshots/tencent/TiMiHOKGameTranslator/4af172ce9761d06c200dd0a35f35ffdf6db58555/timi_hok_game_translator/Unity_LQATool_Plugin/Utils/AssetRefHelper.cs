// ==========================================
// 文件: LQATool\Utils\AssetRefHelper.cs
// 模块: Utils (工具箱)
// ==========================================

using UnityEngine;

// AssetDatabase 等资源数据库 API 仅存在于编辑器环境,
// 打包后的运行时并不包含, 故用条件编译隔离, 避免真机编译报错
#if UNITY_EDITOR
using UnityEditor;
#endif

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 资源引用格式化辅助类
    /// 提供两类静态方法:
    /// 1) FormatAssetRef —— 针对工程 Asset 资源 (预制体/贴图/材质等) 生成引用 JSON;
    /// 2) FormatSceneObjectRef —— 针对场景中的 GameObject / Component 生成引用 JSON;
    /// 全部为纯函数, 无状态, 故声明为 static
    /// </summary>
    public static class AssetRefHelper
    {
        /// <summary>
        /// 将一个工程资源对象格式化为 JSON 引用片段
        /// 输出格式:
        /// {"name": "...", "assetPath": "...", "guid": "...", "instanceID": 123}
        /// 其中 assetPath / guid 仅在编辑器环境且能查询到时才有值, 否则为 null
        /// </summary>
        /// <param name="asset">待格式化的 Unity 资源对象, 允许为 null</param>
        /// <returns>
        /// 合法的 JSON 字符串片段
        /// asset 为 null 时返回字符串 "null"
        /// </returns>
        public static string FormatAssetRef(Object asset)
        {
            // 判空保护: 传入空对象直接返回 JSON 字面量 null, 避免后续空引用
            if (asset == null) return "null";

            // 对象名称转义后加双引号, 得到合法的 JSON 字符串值
            string nameJson = $"\"{JsonBuilder.EscapeJson(asset.name)}\"";

            // assetPath / guid 默认置为 JSON 的 null (无引号),
            // 只有在编辑器下成功查询到时才会被覆盖为带引号的字符串
            string assetPathJson = "null";
            string guidJson = "null";

            #if UNITY_EDITOR

            // 通过资源数据库反查该对象在工程中的资源路径 (如 "Assets/Art/xxx.png")
            string assetPath = AssetDatabase.GetAssetPath(asset);
            if (!string.IsNullOrEmpty(assetPath))
            {
                // 拿到有效路径, 转义并加引号写入
                assetPathJson = $"\"{JsonBuilder.EscapeJson(assetPath)}\"";

                // 进一步由路径换取该资源的 GUID (工程内唯一标识, 跨机器稳定)
                string guid = AssetDatabase.AssetPathToGUID(assetPath);
                if (!string.IsNullOrEmpty(guid))
                {
                    guidJson = $"\"{JsonBuilder.EscapeJson(guid)}\"";
                }
            }

            #endif

            // InstanceID 是运行期的实例标识, 每次运行可能变化,
            // 但可用于本次会话内定位对象, 数值直接输出无需引号
            // (Unity 6000.4+ 原生 GetInstanceID() 已被标记为编译错误, 改走 GetStableInstanceId 做版本兼容)
            long instanceID = UIHelper.GetStableInstanceId(asset);

            // 拼装并返回最终的 JSON 对象片段
            return $"{{\"name\": {nameJson}, \"assetPath\": {assetPathJson}, \"guid\": {guidJson}, \"instanceID\": {instanceID}}}";
        }

        /// <summary>
        /// 将一个场景对象 (GameObject 或挂在其上的 Component) 格式化为 JSON 引用片段
        /// 输出格式:
        /// {"name": "...", "path": "...", "type": "...", "instanceID": 123}
        /// 其中 path 为对象在场景层级中的完整路径 (如 "Canvas/Panel/Button")
        /// </summary>
        /// <param name="obj">场景中的对象, 可为 GameObject、Component 或 null</param>
        /// <returns>
        /// 合法的 JSON 字符串片段
        /// 无法解析出宿主 GameObject 时返回 "null"
        /// </returns>
        public static string FormatSceneObjectRef(Object obj)
        {
            // 判空保护
            if (obj == null) return "null";

            // 统一把传入对象归结到它所属的宿主 GameObject 上
            GameObject hostGO = null;
            // 情况一: 传入的是组件, 取其挂载的 GameObject
            Component comp = obj as Component;
            if (comp != null)
            {
                hostGO = comp.gameObject;
            }
            else
            {
                // 情况二: 传入的本身就是 GameObject (as 失败则为 null)
                hostGO = obj as GameObject;
            }

            // 既不是 Component 也不是 GameObject (无从定位场景位置), 返回 null
            if (hostGO == null) return "null";

            // 宿主对象名称
            string nameJson = $"\"{JsonBuilder.EscapeJson(hostGO.name)}\"";
            // 借助 UIHelper 自底向上回溯父级, 生成完整层级路径
            string pathJson = $"\"{JsonBuilder.EscapeJson(UIHelper.GetGameObjectPath(hostGO))}\"";
            // 记录传入对象的实际类型名 (注意: 是 obj 的类型, 可能是具体组件类型而非 GameObject),
            // 用于区分引用的到底是哪个组件
            string typeJson = $"\"{JsonBuilder.EscapeJson(obj.GetType().Name)}\"";

            // 传入对象自身的运行期实例 ID
            // (Unity 6000.4+ 原生 GetInstanceID() 已被标记为编译错误, 改走 GetStableInstanceId 做版本兼容)
            long instanceID = UIHelper.GetStableInstanceId(obj);

            // 拼装并返回最终的 JSON 对象片段
            return $"{{\"name\": {nameJson}, \"path\": {pathJson}, \"type\": {typeJson}, \"instanceID\": {instanceID}}}";
        }
    }
}