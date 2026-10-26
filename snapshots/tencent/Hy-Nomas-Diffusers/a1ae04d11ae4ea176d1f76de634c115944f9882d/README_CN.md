---
license: apache-2.0
library_name: diffusers
base_model: tencent/Hy-Nomas
license_link: https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE
tags:
  - hy-nomas
  - world-model
  - video-generation
  - interactive-video-generation
  - camera-control
  - autoregressive
  - diffusion-transformer
  - pytorch
---

<p align="left">
  <a href="README.md">English</a>&nbsp;｜&nbsp;中文
</p>

<p align="center">
  <img src="assets/logo-zh.png" alt="Hy-Nomas" width="400"/>
</p>

<h1 align="center">Hy-Nomas: Towards Free-Form Interactive World Generation</h1>

<p align="center">Diffusers BF16 权重 · <code>HyNomasModularPipeline</code></p>

<p align="center">
  <a href="https://github.com/Tencent-Hunyuan/Hy-Nomas"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub"/></a>
  <a href="https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/main/Hy_Nomas_Tech_Report.pdf"><img src="https://img.shields.io/badge/%E6%8A%80%E6%9C%AF%E6%8A%A5%E5%91%8A%20%28Coming%20Soon%29-B31B1B?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMTQgMkg1djIwaDE0Vjd6TTE0IDJ2NWg1TTggMTJoOE04IDE2aDgiLz48L3N2Zz4%3D" alt="技术报告 (Coming Soon)"/></a>
  <a href="https://huggingface.co/datasets/tencent/Hy-Nomas-Bench"><img src="https://img.shields.io/badge/%E8%AF%84%E6%B5%8B%E5%9F%BA%E5%87%86-FFD21E?style=flat-square&amp;logo=huggingface&amp;logoColor=black" alt="评测基准"/></a>
  <a href="https://hy-nomas.hy.tencent.com/"><img src="https://img.shields.io/badge/Project%20Website-666666?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIj48Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSIxMCIvPjxlbGxpcHNlIGN4PSIxMiIgY3k9IjEyIiByeD0iNCIgcnk9IjEwIi8%2BPHBhdGggZD0iTTIgMTJoMjAiLz48L3N2Zz4%3D" alt="Project Website"/></a>
  <a href="https://x.com/TencentHunyuan/status/2113676827114053892"><img src="https://img.shields.io/badge/X%20Post-000000?style=flat-square&amp;logo=x&amp;logoColor=white" alt="X Post"/></a>
</p>

<h3 align="center">
  🚀 <a href="https://hy-nomas.hy.tencent.com/">体验演示 →</a>
</h3>


<video controls playsinline preload="metadata" width="100%" src="https://hy-nomas.hy.tencent.com/gallery/hy_nomas_promo.mp4"></video>

## 模型介绍

**Hy-Nomas** 是一个支持自由形式、多轮交互的视频世界生成模型，可通过文本指令和相机控制信号逐段生成视频世界。用户可以在生成过程中引入物体、改变风格和场景、描述动作，或控制相机运动。

模型结合分段自回归扩散 Transformer（DiT）、Qwen 文本编码器、相机条件模块和 PixelUMM 视频解码器，通过持久化的 Key/Value（KV）cache 在片段之间保留上下文。本目录提供蒸馏模型的 **BF16 Diffusers 权重**。下方示例使用 **4 步去噪**，输出分辨率为 **704 × 1280**，帧率为 **24 FPS**。

## 核心特性

- **自由形式交互：** 通过多轮指令控制主体、动作、外观、风格和环境。
- **相机控制：** 将相机轨迹与文本提示词一起作为条件，控制视角与镜头运动。
- **连续生成：** 通过 KV cache 复用历史上下文，在同一世界中持续生成后续片段。
- **蒸馏推理：** 下方示例中，每个片段使用 4 步 DiT 去噪，再由微调版 PixelUMM 将潜变量解码为视频。
- **Diffusers 集成：** 通过 `HyNomasModularPipeline` 加载随附的 Transformer、文本编码器、分词器、调度器和解码器。

## Hy-Nomas-Bench

我们同时发布 **[Hy-Nomas-Bench](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench)**，包含 **280 个测试案例**，覆盖多轮自由形式文本交互、相机导航、文本与相机交替控制，以及空间记忆四项基准，用于评估视频世界模型在连续生成过程中的交互可控性与一致性。数据集提供结构化提示词、交互序列、按键时间线和参考相机轨迹。数据下载、格式说明及推理指南请参阅 [Hy-Nomas-Bench 数据集仓库](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench)。

## 模型架构

Hy-Nomas 在压缩的视频潜空间中进行扩散去噪，在视频片段之间进行自回归生成。文本、相机运动和缓存的历史共同作为新片段的生成条件。

![Hy-Nomas 中文框架：结构化提示词、视频潜变量和相机轨迹输入双流 MMDiT，通过分段因果联合注意力、时间步调制、相机交叉注意力和持久化 KV cache 生成视频片段。](assets/method_framework_h_cn.png)

*Hy-Nomas 整体框架。推理预设使用 54 个双流 MMDiT 块（N = 54）；紫色、蓝色和绿色分别表示文本、视频和相机路径。*

图中的视频编码路径展示了视频如何表示为 DCAE-V 潜变量。下方文本生成视频的推理流程从该潜空间中的高斯噪声开始生成每个新片段，并通过 KV cache 获取已生成的历史上下文。图中的“多模态大模型”对应 Qwen 文本编码器，默认视频解码器使用下文介绍的微调版 PixelUMM。

### 文本与相机条件

**文本条件。** 文本编码器使用 **Qwen/Qwen2.5-VL-7B-Instruct** 的语言模型部分，其 3,584 维隐藏状态通过两层 token refiner，映射到 DiT 的 2,048 维隐藏空间。各片段使用相应的提示词，用户可随生成过程更新内容要求。

**在线提示词增强。** 原生 Web 演示通过独立的 **Nomas-PE** 服务将用户指令转换为结构化生成提示词。本 Diffusers pipeline 直接接收纯文本或已准备好的结构化提示词，不会运行 Nomas-PE。

**相机条件。** 推理预设采用 `extrinsics_attn`：将归一化的 4 × 4 相机外参矩阵按四个视频帧分组，展平为 64 维输入，与视频潜变量的时间压缩比例对齐。可学习的位姿嵌入和投影对应图中的**位姿编码器 → 相机投影**路径。在每个双流块中，视频 token 经过视频 MLP 后，通过交叉注意力查询投影后的相机特征。`per_chunk_camera_attn=true`、`camera_chunk_size=1` 表示相机注意力按单个潜变量帧对齐。

### 分段自回归扩散 Transformer

生成主干是一个**稠密多模态扩散 Transformer（MMDiT）**。视频潜变量经过**时空块嵌入**进入视频流，细化后的文本 token 进入独立的文本流。**时间步嵌入**提供当前噪声水平的条件，各块据此生成偏移、缩放和残差门控，对两个分支分别进行调制。

在每个块中，文本与视频通过**分段因果联合注意力**交换信息，使用 3D RoPE 编码视频位置，并从该层的 KV cache 读取历史片段上下文。随后，两个分支分别经过各自的 MLP。**相机交叉注意力**以视频 token 为 Query、相机特征为 Key/Value，进一步更新视频分支。文本特征继续传入下一块；经过最后一块后，输出头仅使用视频分支预测潜空间中的 flow velocity，采样器据此完成片段去噪，再进行视频解码。

模型架构如下表所示：

| 属性 | 配置 |
|:---|:---|
| 模型标识 | `Hy-Nomas` |
| Transformer 层数 | 54 个双流块；0 个单流块 |
| 隐藏维度 | 2,048 |
| 注意力头 | 16 个头；每头 128 维 |
| 前馈网络扩展比例 | 4 倍；中间维度 8,192 |
| 潜变量输入 / 输出通道 | 32 / 32 |
| 潜变量 patch 大小，时间 × 高 × 宽 | 1 × 1 × 1 |
| 位置编码 | 3D RoPE；时间 / 高 / 宽维度为 `[16, 56, 56]`；theta 为 256 |
| 文本条件 | 3,584 维 Qwen 特征；两层 token refiner |
| 相机条件 | 相机外参嵌入，通过双流块中的交叉注意力注入 |
| 去噪预测 | 预测 flow velocity；推理预设采用 Euler ODE 采样 |

每轮生成时，DiT 通过注意力访问全部历史 KV cache 和当前条件，对当前片段进行去噪。片段之间采用因果注意力，因此生成当前片段无需访问未来片段。进入下一片段时，复用已缓存的 Key 和 Value。

Diffusers pipeline 跨片段保留注意力 KV cache。连续生成时，可以复用上一次调用返回的状态；下方使用指南提供了这一流程的说明。

### 视频潜变量与 PixelUMM 解码器

Hy-Nomas 使用 **DCAE-V `f32t4c32` 潜变量**，包含 32 个通道，空间高、宽各压缩 32 倍，时间压缩 4 倍。DiT 生成该表示下的潜变量，默认推理流程使用**微调版 PixelUMM 解码器**将其还原为视频。

解码器包含 **36 层 Transformer**，隐藏维度为 **4,096**，采用 **32 个 Query 头**和 **8 个 KV 头**。它以生成的 DCAE-V 潜变量为条件重建像素，将 RGB 视频划分为 4 × 16 × 16 的时空块（tubelet）。预设使用 **1 步 PixelUMM 解码**，时间窗口为 10 个潜变量帧，相邻窗口重叠 5 个潜变量帧。该解码步数与下方示例中 DiT 的 4 步去噪分别配置。

架构参数见 [DiT 模型定义](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/modules/__init__.py)、[DiT 实现](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/nomas_cpt.py)、[PixelUMM 实现](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/vae/pixelumm_decoder/model.py)及[推理配置](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/configs/experiment/inference.yaml)。

## 模型资源

本目录包含蒸馏版 Hy-Nomas 的 BF16 Diffusers 权重，通过 `HyNomasModularPipeline.save_pretrained()` 保存。

| 组件 | 目录 / 文件 | 内容 |
|:---|:---|:---|
| Pipeline | `modular_model_index.json` | 组件类型与加载配置 |
| Transformer | `transformer/` | 蒸馏版 `HyNomasTransformer3DModel`，含 BF16 Safetensors 分片和配置 |
| 视频解码器 | `decoder/` | 微调版 `PixelUMMDecoder`，含 BF16 Safetensors 分片和配置 |
| 文本编码器 | `text_encoder/` | `Qwen2_5_VLTextModel`，含 BF16 Safetensors 分片和配置 |
| 分词器 | `tokenizer/` | Qwen 分词器文件 |
| 调度器 | `scheduler/` | `FlowMatchEulerDiscreteScheduler` 配置 |

[原始模型仓库](https://huggingface.co/tencent/Hy-Nomas)提供原生检查点、量化版本、适配器和 Nomas-PE 资源；这些额外资源不包含在本 Diffusers 目录中。

## 使用指南

### 使用 Diffusers 推理

升级 diffusers 以使用 `HyNomasModularPipeline`。

```bash
pip install -e "diffusers[hy-nomas] @ git+https://github.com/jiaxiangc/diffusers.git@hy-nomas"
```

Hy-Nomas 支持多轮交互生成。以下示例生成两个各五秒的片段，每个片段使用四步去噪。请将 `model_path` 替换为下载后的 `Hy-Nomas-Diffusers` 目录。

```python
import json

import torch
from diffusers import HyNomasModularPipeline
from diffusers.utils import export_to_video

model_path = "/path/to/Hy-Nomas-Diffusers"
pipe = HyNomasModularPipeline.from_pretrained(model_path)
pipe.load_components(dtype=torch.bfloat16)
pipe.to(device="cuda", dtype=torch.bfloat16)

prompts = [
    {
        "Style": "Cinematic fantasy", "perspective_view": "Third-person view",
        "subject_list": [{
            "subject_id": "fox", "display_name": "a small orange fox",
            "subject_attribute": "Orange fur, white chest, and a fluffy tail.",
        }],
        "segments": [{
            "visual_description_long": (
                "A small orange fox stands on a stone path in a luminous forest. "
                "Blue fireflies drift between the trees."
            ),
            "contained_actions": [{
                "start_time": "00:00.000", "end_time": "00:05.000",
                "action_description": "The fox walks slowly along the path.",
            }],
        }],
    },
    {
        "segments": [{
            "description_change": "Glowing blue flowers open beside the path as the fox continues forward.",
            "contained_actions": [{
                "start_time": "00:00.000", "end_time": "00:05.000",
                "action_description": "The fox passes the flowers and looks around.",
            }],
        }],
    },
]

videos = pipe(
    prompt=[json.dumps(prompt) for prompt in prompts],
    height=704,
    width=1280,
    num_frames=240,
    segment_latent_lengths=[30, 30],
    fps=24,
    num_inference_steps=4,
    generator=torch.Generator("cpu").manual_seed(42),
    output="videos",
)
export_to_video(videos[0], "hy_nomas_video.mp4", fps=24, quality=None)
```

每个 prompt 描述一个片段。动作时间戳相对于当前片段的起点，因此两个片段都使用 `00:00.000`–`00:05.000`。在 24 FPS 下，`num_frames=240` 与 `segment_latent_lengths=[30, 30]` 对应总计十秒的视频。示例直接输入准备好的结构化提示词，pipeline 不会调用提示词增强服务。

### 对齐原生注意力实现

示例默认使用 PyTorch SDPA。如需对齐原生实现的注意力后端，请按照 [Hy-Nomas 仓库](https://github.com/Tencent-Hunyuan/Hy-Nomas)安装兼容的 FlashAttention 2、FlashAttention 3 和 MagiAttention 内核，然后在模型加载后、开始生成前启用：

```python
pipe.transformer.enable_reference_attention(text_backend="flash_varlen", deterministic=True)
```

`hy-nomas` 可选依赖组不会安装这些可选内核。纯文本提示词、相机控制、连续生成及与原生实现对齐的条件，请参阅 [Diffusers Hy-Nomas 指南](https://github.com/jiaxiangc/diffusers/blob/hy-nomas/docs/source/en/api/pipelines/hy_nomas.md)。

## 运行说明

- 示例将 BF16 组件加载到一张 CUDA GPU 上；显存占用还取决于分辨率、片段长度和历史缓存。原生 INT8/FP8 RTX 4090 配置属于单独的部署方案。
- 24 FPS 控制视频播放帧率；实际生成速度取决于硬件和推理设置。
- 跨片段保留历史上下文会增加 KV cache 的内存占用。

## 许可证

Hy-Nomas 采用 Apache-2.0 许可证，适用条款请参阅本仓库的 [LICENSE](LICENSE) 文件。第三方模型和组件仍遵循各自的许可证。

## 致谢

感谢 [Gemma 4](https://deepmind.google/models/gemma/gemma-4/)、[Qwen3.8](https://qwen.ai/blog?id=qwen3.8)、[Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)、[DC-AE](https://github.com/dc-ai-projects/DC-Gen) 和 [MagiAttention](https://github.com/SandAI-org/MagiAttention) 团队为社区作出的贡献，以及为本项目提供支持的模型、研究成果和工具。

## 联系我们

如有一般问题、非安全缺陷或建议，欢迎在 [Hy-Nomas 仓库](https://github.com/Tencent-Hunyuan/Hy-Nomas/issues)提交 issue，或通过 [hy_nomas@tencent.com](mailto:hy_nomas@tencent.com) 联系我们。疑似安全漏洞请按照仓库的[安全问题报告指南](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/SECURITY.md)私下报告。
