---
license: apache-2.0
license_link: https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE
library_name: hy-nomas
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
  <a href="https://huggingface.co/tencent/Hy-Nomas">English</a>&nbsp;｜&nbsp;中文
</p>

<p align="center">
  <img src="assets/logo-zh.png" alt="Hy-Nomas" width="400"/>
</p>

<h1 align="center">Hy-Nomas: Towards Free-Form Interactive World Generation</h1>

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

模型由分段自回归扩散 Transformer（DiT）、Qwen 文本编码器、相机条件模块和 PixelUMM 视频解码器组成，通过持久化的键值（KV）缓存在片段之间传递上下文。蒸馏推理预设采用 **8 步去噪**，默认输出分辨率为 **720 × 1280**，视频帧率为 **24 FPS**。另提供 **NVIDIA GeForce RTX 4090 单卡**视频推理配置，结合 INT8 DiT 权重、INT8 KV cache、FP8 解码器和 CPU offload 降低显存占用。

## 核心特性

- **自由形式交互：** 通过多轮指令控制主体、动作、外观、风格和环境。
- **相机控制：** 将相机轨迹与文本提示词一起作为条件，控制视角与镜头运动。
- **连续生成：** 通过 KV cache 复用历史上下文，在同一世界中持续生成后续片段。
- **蒸馏推理：** 每个片段使用 8 步 DiT 去噪，再由微调版 PixelUMM 将潜变量解码为视频。
- **灵活部署：** 支持标准序列并行配置、单卡配置和 Web 交互式演示。

## Hy-Nomas-Bench

我们同时发布 **[Hy-Nomas-Bench](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench)**，包含 **280 个测试案例**，覆盖多轮自由形式文本交互、相机导航、文本与相机交替控制，以及空间记忆四项基准，用于评估视频世界模型在连续生成过程中的交互可控性与一致性。数据集提供结构化提示词、交互序列、按键时间线和参考相机轨迹。数据下载、格式说明及推理指南请参阅 [Hy-Nomas-Bench 数据集仓库](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench)。

## 模型架构

Hy-Nomas 在压缩的视频潜空间中进行扩散去噪，在视频片段之间进行自回归生成。文本、相机运动和缓存的历史共同作为新片段的生成条件。

![Hy-Nomas 中文框架：结构化提示词、视频潜变量和相机轨迹输入双流 MMDiT，通过分段因果联合注意力、时间步调制、相机交叉注意力和持久化 KV cache 生成视频片段。](assets/method_framework_h_cn.png)

*Hy-Nomas 整体框架。推理预设使用 54 个双流 MMDiT 块（N = 54）；紫色、蓝色和绿色分别表示文本、视频和相机路径。*

图中的视频编码路径展示了视频如何表示为 DCAE-V 潜变量。下方文本生成视频的推理流程从该潜空间中的高斯噪声开始生成每个新片段，并通过 KV cache 获取已生成的历史上下文。图中的“多模态大模型”对应 Qwen 文本编码器，默认视频解码器使用下文介绍的微调版 PixelUMM。

### 文本与相机条件

**文本条件。** 文本编码器使用 **Qwen/Qwen2.5-VL-7B-Instruct** 的语言模型部分，其 3,584 维隐藏状态通过两层 token refiner，映射到 DiT 的 2,048 维隐藏空间。各片段使用相应的提示词，用户可随生成过程更新内容要求。

**在线提示词增强。** Web 演示首先通过 **Nomas-PE** 将用户指令转换为结构化生成提示词。它独立于文本编码器，以单独的服务运行，是演示的必要依赖。离线推理可以直接读取已准备好的提示词文件。

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

标准预设保留完整历史（`max_cache_segments=null`，关闭滑动窗口）。单卡预设为 GPU 注意力选择有限数量的历史潜变量帧，并在 CPU 上保留历史存档。默认历史预算为 **18 个潜变量帧**，该预算限制的是历史上下文，不限制当前片段长度。

### 视频潜变量与 PixelUMM 解码器

Hy-Nomas 使用 **DCAE-V `f32t4c32` 潜变量**，包含 32 个通道，空间高、宽各压缩 32 倍，时间压缩 4 倍。DiT 生成该表示下的潜变量，默认推理流程使用**微调版 PixelUMM 解码器**将其还原为视频。

解码器包含 **36 层 Transformer**，隐藏维度为 **4,096**，采用 **32 个 Query 头**和 **8 个 KV 头**。它以生成的 DCAE-V 潜变量为条件重建像素，将 RGB 视频划分为 4 × 16 × 16 的时空块（tubelet）。预设使用 **1 步 PixelUMM 解码**，时间窗口为 10 个潜变量帧，相邻窗口重叠 5 个潜变量帧。该解码步数与 DiT 的 8 步去噪分别配置。

架构参数见 [DiT 模型定义](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/modules/__init__.py)、[DiT 实现](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/nomas_cpt.py)、[PixelUMM 实现](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/vae/pixelumm_decoder/model.py)及[推理配置](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/configs/experiment/inference.yaml)。

## 模型资源

根据所用推理配置，选择匹配的生成模型与解码器权重。

| 组件 | 模型资源 | 用途 | 本仓库中的路径 |
|:---|:---|:---|:---|
| DiT | **蒸馏 DiT（FP32）** | 用于 8 步推理和交互式演示的主要检查点；标准配置以 BF16 加载 DiT。 | `DiT/distilled/diffusion_pytorch_model_ema_0_995.safetensors` |
| DiT | **量化蒸馏 DiT（INT8）** | 用于单卡配置的量化检查点；权重以 INT8 存储，DiT 线性运算仍采用 BF16。 | `DiT/distilled_int8/diffusion_pytorch_model_ema_0_995_int8.safetensors` |
| DiT | **基础自回归 DiT（FP32）** | 未蒸馏模型；下方的 8 步推理示例应使用蒸馏模型。 | `DiT/base_ar/diffusion_pytorch_model_fp32.safetensors` |
| 适配器 | **Cinematic LoRA** | 可选的视觉质量适配器，适用于兼容的浮点 DiT。 | `DiT/lora_weights/cinematic/` |
| 适配器 | **Robotics LoRA** | 在 [RealSource-World](https://huggingface.co/datasets/RealmanRobot/RealSource-World) 真实世界机械臂数据集上训练的 LoRA 适配器，合并到蒸馏 DiT 中，以增强生成世界的机器人仿真能力。 | `DiT/lora_weights/dual_arm_robotics/` |
| 视频自编码器 | **DCAE-V** | 定义 32 通道的压缩视频表示，并提供视频编码和解码功能。 | `VAE/DCAE-V/dc-ae-v-1.0-f32t4c32-bf16.pt` |
| 视频解码器 | **微调后的 PixelUMM 解码器** | 默认用于解码生成的 DCAE-V 潜变量。 | `VAE/PixelUMM_FT/diffusion_pytorch_model.safetensors` |
| 视频解码器 | **量化后的 PixelUMM 解码器（FP8）** | 用于低显存配置的解码器检查点。 | `VAE/PixelUMM_FT_FP8/diffusion_pytorch_model_fp8.safetensors` |
| 提示词增强 | **Nomas-PE** | 独立的在线服务，将用户指令转换为供 Web 演示使用的结构化提示词。 | `PE/` |

标准离线推理需要**蒸馏 DiT**、**匹配的 PixelUMM 权重**和 **Qwen 文本编码器**。单卡预设需要兼容的 **INT8 DiT** 与 **FP8 PixelUMM** 组合。INT8 加载器不支持在推理时额外加载独立的 LoRA 适配器。

从本仓库下载所需模型资源，并保留 `DiT/`、`VAE/` 和 `PE/` 的目录结构。下方推理命令通过 `HY_NOMAS_MODEL_DIR` 指定下载后的模型仓库根目录。文本编码器由 Hugging Face 自动从 `Qwen/Qwen2.5-VL-7B-Instruct` 下载，并复用本地缓存。如已有本地副本，可在命令后添加 `model.text_encoder.model_name=/path/to/Qwen2.5-VL-7B-Instruct`。

## 使用指南

### 环境配置

使用 [Hy-Nomas 代码仓库](https://github.com/Tencent-Hunyuan/Hy-Nomas) 进行推理：

```bash
git clone https://github.com/Tencent-Hunyuan/Hy-Nomas.git
cd Hy-Nomas
```

可选择以下两种环境配置方式。**强烈推荐使用我们发布的预打包 Docker 镜像**，其中已包含 Python 环境、PyTorch 和所需的 CUDA 注意力内核。

#### 方案一：预打包 Docker 镜像（推荐）

准备一台安装了兼容 NVIDIA 驱动、Docker 和 NVIDIA Container Toolkit 的 Linux 主机。在代码仓库根目录运行：

```bash
export HY_NOMAS_IMAGE="hynomasoss/hynomasoss:cu130"

docker pull "$HY_NOMAS_IMAGE"
docker run --rm -it --gpus all --ipc=host --network=host \
  -v "$PWD:/workspace/Hy-Nomas" \
  -w /workspace/Hy-Nomas \
  "$HY_NOMAS_IMAGE" bash
```

后续命令在容器内执行，使用镜像预装的 Python 环境。将模型资源放在挂载的仓库目录下，或额外挂载模型目录；下方启动命令应使用容器内可见的路径。

#### 方案二：手动安装

准备 Linux、Python 3.12+、uv、兼容的 NVIDIA 驱动、CUDA 13.0 Toolkit（`nvcc`）和 C++ 编译器。在代码仓库根目录运行：

```bash
uv sync --extra all
source .venv/bin/activate
```

`all` 可选依赖组包含 PyTorch 2.10.0（CUDA 13.0）、FlashAttention 2、FlashAttention 3 和 MagiAttention。`pyproject.toml` 已配置 PyTorch CUDA 包源和官方 FA3 源码，并为注意力内核禁用构建隔离，使其构建时能够使用当前环境中的 PyTorch。内核编译可能需要一些时间。

### 模型路径

在运行推理的环境中，将 `HY_NOMAS_MODEL_DIR` 设置为本地模型仓库根目录；该目录应包含上表所列的权重路径。使用 Docker 时，请填写容器内可见的路径。

```bash
export HY_NOMAS_MODEL_DIR="/path/to/Hy-Nomas-models"
```

下方命令仍在 Hy-Nomas **代码仓库根目录**运行，通过此变量读取模型仓库中的权重和示例提示词。

### 准备提示词

离线推理支持包含多个视频生成请求的 JSON 列表。每个请求可包含多个 `segments`。片段及其 `contained_actions` 中的 `start_time` 和 `end_time` 均使用 `MM:SS.mmm`（分钟:秒.毫秒）格式的字符串。下方示例包含两个各 5 秒的片段，时间范围分别为 0–5 秒和 5–10 秒。首个片段描述初始世界，后续片段通过 `description_change` 描述世界如何变化。

下方推理命令使用模型仓库中随附的[提示词示例文件](examples/prompts.json)。如需自定义内容，可按以下格式保存 JSON，并通过 `inference.prompt=/path/to/prompts.json` 指定文件：

```json
[
  {
    "test_id": "forest_world",
    "Style": "Cinematic fantasy",
    "perspective_view": "Third-person view",
    "subject_list": [
      {
        "subject_id": "fox",
        "display_name": "a small orange fox",
        "subject_attribute": "Orange fur, white chest, and a fluffy tail."
      }
    ],
    "segments": [
      {
        "start_time": "00:00.000",
        "end_time": "00:05.000",
        "visual_description_long": "A small orange fox stands on a stone path in a luminous forest. Blue fireflies drift between the trees.",
        "contained_actions": [
          {"start_time": "00:00.000", "end_time": "00:05.000", "action_description": "The fox walks slowly along the path."}
        ]
      },
      {
        "start_time": "00:05.000",
        "end_time": "00:10.000",
        "description_change": "Glowing blue flowers open beside the path as the fox continues forward.",
        "contained_actions": [
          {"start_time": "00:05.000", "end_time": "00:10.000", "action_description": "The fox passes the flowers and looks around."}
        ]
      }
    ]
  }
]
```

预设通过事件时间戳计算片段长度（`inference.video_length=event`）。示例中的动作时间戳使用同一条视频时间轴，程序会将其转换为各片段的局部时间。

### 标准推理

标准预设采用 **8 路序列并行**（`sp_size=8`）和分布式 PixelUMM 解码，因此默认启动需要一个推理组内的八张 GPU。在代码仓库根目录执行：

```bash
bash scripts/inference/inference_from_config.sh configs/experiment/inference.yaml \
  dit_weight="$HY_NOMAS_MODEL_DIR/DiT/distilled/diffusion_pytorch_model_ema_0_995.safetensors" \
  model.vae.checkpoint="$HY_NOMAS_MODEL_DIR/VAE/PixelUMM_FT/diffusion_pytorch_model.safetensors" \
  inference.prompt="$HY_NOMAS_MODEL_DIR/examples/prompts.json" \
  inference.save_path=./outputs/distill
```

生成的视频保存在 `inference.save_path` 下，预设还会保存生成的潜变量和提示词文本。

| 设置 | 默认值 | 覆盖参数 |
|:---|:---|:---|
| 输出分辨率，高 × 宽 | 720 × 1280 | `'inference.video_size=[480,832]'` |
| 输出视频帧率 | 24 FPS | `inference.video_fps=24` |
| DiT 去噪步数 | 8 | `inference.infer_steps_video=8` |
| 求解器 | Euler ODE | `inference.solver_type=euler` |
| 文本 / 相机引导强度 | 1.0 / 1.0 | `inference.cfg_scale_video=1.0 inference.camera_cfg_scale=1.0` |
| 随机种子 | 42 | `inference.seed=42` |
| 相机平移 / 旋转强度 | 1.0 / 2.5 | `inference.trajectory_translation_scale=1.0 inference.trajectory_rotation_scale=2.5` |

进行相机控制生成时，可添加 `inference.camera_trajectory=/path/to/camera.npz`。轨迹文件包含形状为 `[N, 4, 4]` 的 camera-to-world 矩阵 `c2ws`，以及形状为 `[N, 3, 3]` 的相机内参 `intrinsics`；轨迹应与目标视频时长和帧率对齐。仓库提供[相机轨迹工具](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/camera/geometry/generate_npz_trajectories.py)。

### 单卡低显存推理

使用 `configs/experiment/single_gpu_low_mem_inference.yaml` 在 **NVIDIA GeForce RTX 4090 单卡**上推理。该配置继承标准预设的模型架构、提示词处理、分辨率、帧率及 8 步 DiT 去噪设置，并调整内存管理和执行方式：

- **INT8 DiT 与 KV 存储：** 使用 INT8 存储 DiT 权重及缓存的 Key/Value，DiT 线性层和注意力仍采用 BF16 计算。
- **有限的 GPU 历史上下文：** 使用 `temporal_context` 策略选择最多 18 个历史潜变量帧，将历史存档保存在 CPU 上。
- **CPU offload：** 文本编码器、DiT 和解码器在各自处理阶段移入 GPU，完成后移回 CPU。
- **单卡内核：** DiT 使用 FlexAttention，解码器使用 CUTLASS FP8，并设置 `sp_size=1`。

准备兼容的 INT8 DiT 与 FP8 PixelUMM 权重。启动脚本通过 `nvidia-smi` 统计 GPU 数量，请在 **`nvidia-smi` 仅能看到一张 GPU** 的主机或容器中执行：

```bash
bash scripts/inference/inference_from_config.sh configs/experiment/single_gpu_low_mem_inference.yaml \
  dit_weight="$HY_NOMAS_MODEL_DIR/DiT/distilled_int8/diffusion_pytorch_model_ema_0_995_int8.safetensors" \
  model.vae.checkpoint="$HY_NOMAS_MODEL_DIR/VAE/PixelUMM_FT_FP8/diffusion_pytorch_model_fp8.safetensors" \
  inference.prompt="$HY_NOMAS_MODEL_DIR/examples/prompts.json" \
  inference.save_path=./outputs/single_gpu
```

系统内存需要容纳卸载的模型以及随生成增长的历史存档。CPU–GPU 数据传输会增加延迟。峰值显存还取决于输出分辨率和当前片段长度；历史帧预算不限制当前片段的显存占用。

### 交互式演示

访问[在线交互式演示](https://hy-nomas.hy.tencent.com/)，创建世界，通过文本指令或相机路径继续生成，并下载视频。

本地部署请参阅 [Web 演示部署指南](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/apps/README.md)，其中包含前端、网关、GPU 工作进程、单卡模式和多机部署说明。**Web 演示需要 Nomas-PE**，其服务资源单独计算；上文的单卡支持指视频推理部分。演示在片段边界进行流式解码。

## 运行说明

- 完整历史推理会随生成持续增加上下文和缓存内存占用。单卡预设限制 GPU 上活跃的历史上下文，其 CPU 历史存档仍可增长。
- 24 FPS 指输出视频的播放帧率。实际生成速度取决于硬件、分辨率、片段长度、历史上下文和所选配置。
- 8 步示例需要蒸馏 DiT 及匹配的解码器。文中的架构和采样参数来自配置，不代表性能评测结果。

## 许可证

Hy-Nomas 采用 Apache-2.0 许可证，适用条款请参阅本仓库的 [LICENSE](https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE) 文件。第三方模型和组件仍遵循各自的许可证。

## 致谢

感谢 [Gemma 4](https://deepmind.google/models/gemma/gemma-4/)、[Qwen3.8](https://qwen.ai/blog?id=qwen3.8)、[Kimi-K3](https://github.com/MoonshotAI/Kimi-K3)、[DC-AE](https://github.com/dc-ai-projects/DC-Gen) 和 [MagiAttention](https://github.com/SandAI-org/MagiAttention) 团队为社区作出的贡献，以及为本项目提供支持的模型、研究成果和工具。

## 联系我们

如有一般问题、非安全缺陷或建议，欢迎在 [Hy-Nomas 仓库](https://github.com/Tencent-Hunyuan/Hy-Nomas/issues)提交 issue，或通过 [hy_nomas@tencent.com](mailto:hy_nomas@tencent.com) 联系我们。疑似安全漏洞请按照仓库的[安全问题报告指南](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/SECURITY.md)私下报告。
