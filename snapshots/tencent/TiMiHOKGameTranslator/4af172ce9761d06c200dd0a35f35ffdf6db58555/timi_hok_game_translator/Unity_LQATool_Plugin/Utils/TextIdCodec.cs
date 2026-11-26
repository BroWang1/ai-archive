// ==========================================
// 文件: LQATool\Utils\TextIdCodec.cs
// 模块: Utils (工具箱)
// ==========================================

using UnityEngine;

/// <summary>
/// LQATool 工具箱层命名空间
/// </summary>
namespace LQATool.Utils
{
    /// <summary>
    /// 文本 ID 与颜色 (Color32) 之间的编解码工具
    /// 
    /// 用途: 把一个整数 ID 编码成一种 RGB 颜色, 用于对界面元素做可视化着色标记
    ///       之后通过采样该颜色, 再解码还原出原始 ID
    /// 
    /// 原理: 将 R/G/B 的 3 个通道分别当作一位 "9 进制数字"
    ///       每个通道被离散成 Levels(=9) 个档位, 档位取值为 Base + 序号 * Step
    ///       因此可编码的 ID 总数为 9 * 9 * 9 = 729 (见 Capacity)
    /// </summary>
    public static class TextIdCodec
    {
        /// <summary>
        /// 通道档位的起始值 (序号 0 对应的通道值), 选 56 是为了避开 0 附近的极端值, 留出容差空间
        /// </summary>
        private const int Base = 56;

        /// <summary>
        /// 相邻 2 个档位之间的通道间距, 间距越大, 抗采样误差能力越强
        /// </summary>
        private const int Step = 24;

        /// <summary>
        /// 每个通道的离散档位数量 (即每 1 位的进制) 9 档 => 3 通道共 9^3 种组合
        /// </summary>
        private const int Levels = 9;

        /// <summary>
        /// 解码时允许的最大通道偏差 (取步长的一半) 超过该偏差视为无效颜色
        /// </summary>
        private const int Tolerance = Step / 2;

        /// <summary>
        /// 可编码的 ID 总容量: Levels^3 = 729, 有效 ID 范围为 1 ~ Capacity
        /// </summary>
        public const int Capacity = Levels * Levels * Levels;

        /// <summary>
        /// 将整数 ID 编码为颜色
        /// </summary>
        /// <param name="id">待编码的 ID, 取值范围应为 1 ~ Capacity</param>
        /// <returns>
        /// 对应的不透明颜色 (Alpha 固定为 255)
        /// 说明: 实际返回类型为 Color32, 见下方
        /// </returns>
        public static Color32 Encode(int id)
        {
            // 转成 0 基索引, 便于按 9 进制拆分 (ID=1 对应 v=0)
            int v = id - 1;

            // 取最低位数字作为 R 通道档位序号 (个位)
            int ri = v % Levels;
            // 取次低位数字作为 G 通道档位序号 (十位)
            int gi = (v / Levels) % Levels;
            // 取最高位数字作为 B 通道档位序号 (百位)
            int bi = (v / (Levels * Levels)) % Levels;

            // 将每个档位序号映射到实际通道值: Base + 序号 * Step
            // 序号范围 0~8 => 通道值范围 56~248, 均在 [0,255] 内
            return new Color32(
                (byte)(Base + ri * Step),
                (byte)(Base + gi * Step),
                (byte)(Base + bi * Step),
                255  // Alpha 固定不透明
            );
        }

        /// <summary>
        /// 将颜色的 RGB 分量解码回整数 ID
        /// </summary>
        /// <returns>
        /// 成功返回 1 ~ Capacity 的 ID
        /// 任一通道无法匹配到合法档位时返回 0 (无效)
        /// </returns>
        public static int Decode(byte r, byte g, byte b)
        {
            // 分别把 3 个通道值就近还原为档位序号 (含容差校验)
            int ri = NearestLevel(r);
            int gi = NearestLevel(g);
            int bi = NearestLevel(b);

            // 任一通道校验失败即认为整体无效
            if (ri < 0 || gi < 0 || bi < 0) return 0;

            // 按 9 进制加权组合 3 位数字, 并 +1 还原为从 1 开始的 ID
            return ri + gi * Levels + bi * Levels * Levels + 1;
        }

        /// <summary>
        /// 将单个通道值就近映射为合法档位序号
        /// </summary>
        /// <param name="channel">通道值 (0~255)</param>
        /// <returns>
        /// 合法时返回 0 ~ Levels-1 的档位序号
        /// 越界或偏差过大返回 -1
        /// </returns>
        private static int NearestLevel(int channel)
        {
            // 反推最接近的档位序号: (通道值 - Base) / Step 四舍五入
            int idx = Mathf.RoundToInt((channel - Base) / (float)Step);

            // 序号必须落在 [0, Levels) 内, 否则无效
            if (idx < 0 || idx >= Levels) return -1;

            // 计算该档位对应的 "标准通道值"
            int quantized = Base + idx * Step;

            // 实测值与标准值偏差超过容差 => 认为不是我们编码出来的颜色, 判为无效
            if (Mathf.Abs(channel - quantized) > Tolerance) return -1;

            return idx;
        }
    }
}