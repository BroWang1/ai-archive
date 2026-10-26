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
  <a href="https://huggingface.co/tencent/Hy-Nomas/blob/main/README_CN.md">中文</a>&nbsp;｜&nbsp;English
</p>

<p align="center">
  <img src="assets/logo-en.png" alt="Hy-Nomas" width="400"/>
</p>

<h1 align="center">Hy-Nomas: Towards Free-Form Interactive World Generation</h1>

<p align="center">
  <a href="https://github.com/Tencent-Hunyuan/Hy-Nomas"><img src="https://img.shields.io/badge/GitHub-181717?style=flat-square&amp;logo=github&amp;logoColor=white" alt="GitHub"/></a>
  <a href="https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/main/Hy_Nomas_Tech_Report.pdf"><img src="https://img.shields.io/badge/Technical%20Report%20%28Coming%20Soon%29-B31B1B?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIiBzdHJva2UtbGluZWpvaW49InJvdW5kIj48cGF0aCBkPSJNMTQgMkg1djIwaDE0Vjd6TTE0IDJ2NWg1TTggMTJoOE04IDE2aDgiLz48L3N2Zz4%3D" alt="Technical Report (Coming Soon)"/></a>
  <a href="https://huggingface.co/datasets/tencent/Hy-Nomas-Bench"><img src="https://img.shields.io/badge/Benchmark-FFD21E?style=flat-square&amp;logo=huggingface&amp;logoColor=black" alt="Benchmark"/></a>
  <a href="https://hy-nomas.hy.tencent.com/"><img src="https://img.shields.io/badge/Project%20Website-666666?style=flat-square&amp;logo=data%3Aimage%2Fsvg%2Bxml%3Bbase64%2CPHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIyIj48Y2lyY2xlIGN4PSIxMiIgY3k9IjEyIiByPSIxMCIvPjxlbGxpcHNlIGN4PSIxMiIgY3k9IjEyIiByeD0iNCIgcnk9IjEwIi8%2BPHBhdGggZD0iTTIgMTJoMjAiLz48L3N2Zz4%3D" alt="Project Website"/></a>
  <a href="https://x.com/TencentHunyuan/status/2113676827114053892"><img src="https://img.shields.io/badge/X%20Post-000000?style=flat-square&amp;logo=x&amp;logoColor=white" alt="X Post"/></a>
</p>

<h3 align="center">
  🚀 <a href="https://hy-nomas.hy.tencent.com/">Try the Demo →</a>
</h3>

<br>

<video controls playsinline preload="metadata" width="100%" src="https://hy-nomas.hy.tencent.com/gallery/hy_nomas_promo.mp4"></video>

## Model Introduction

**Hy-Nomas** is a video world generation model that supports free-form, multi-turn interaction through text instructions and camera control. It generates a world one video segment at a time, allowing users to introduce objects, change styles and scenes, describe actions, or control the camera as generation continues.

The model combines a segment-autoregressive diffusion transformer (DiT), a Qwen text encoder, camera-conditioning modules, and a PixelUMM video decoder. A persistent key/value (KV) cache carries context between segments. The distilled inference configuration uses **8 denoising steps**, with **720 × 1280** output at **24 FPS**. A separate configuration supports video generation on a **single NVIDIA GeForce RTX 4090** using INT8 DiT weights, an INT8 KV cache, an FP8 decoder, and CPU offload.

## Key Features

- **Free-form interaction:** Guide successive segments with instructions about subjects, actions, appearance, style, and environment.
- **Camera control:** Supply camera trajectories alongside text to control viewpoint and movement.
- **Continuous generation:** Reuse earlier context through a KV cache when extending the same world.
- **Distilled inference:** Generate each segment with 8 DiT denoising steps and decode its latents with a fine-tuned PixelUMM decoder.
- **Flexible deployment:** Use the standard sequence-parallel configuration or the single-GPU configuration, and interact through the web demo.

## Hy-Nomas-Bench

We also release **[Hy-Nomas-Bench](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench)**, a suite of four benchmarks with **280 test cases** covering multi-turn free-form text interaction, camera navigation, interleaved text and camera control, and spatial memory. It evaluates interactive controllability and consistency during continuous world generation, providing structured prompts, interaction sequences, keyboard timelines, and reference camera trajectories. See the [Hy-Nomas-Bench dataset repository](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench) for downloads, data formats, and inference instructions.

## Model Architecture

Hy-Nomas performs diffusion in a compressed video latent space and autoregression across video segments. Text, camera motion, and cached history condition the generation of each new segment.

![Hy-Nomas framework: structured prompts, video latents, and camera trajectories feed dual-stream MMDiT blocks with segment-wise causal joint attention, timestep modulation, camera cross-attention, and a persistent KV cache.](assets/method_framework_h.png)

*Hy-Nomas framework. The inference configuration uses 54 dual-stream MMDiT blocks (N = 54). Purple, blue, and green indicate the text, video, and camera paths, respectively.*

The figure's video-encoder path illustrates how video is represented as DCAE-V latents. In the text-to-video inference flow below, each new segment starts from Gaussian noise in that latent space and uses the KV cache for generated history. The MLLM is the Qwen text encoder, and the default video decoder is the fine-tuned PixelUMM described below.

### Text and Camera Conditioning

**Text conditioning.** The text encoder uses the language-model component of **Qwen/Qwen2.5-VL-7B-Instruct**. Its 3,584-dimensional hidden states pass through a two-layer token refiner and are projected into the DiT's 2,048-dimensional hidden space. Segment-specific prompts let users change the requested content as generation proceeds.

**Online prompt enhancement.** In the web demo, **Nomas-PE** first converts user instructions into structured generation prompts. It is a separate service from the text encoder and is required by the demo. Offline inference can read prepared prompt files directly.

**Camera conditioning.** The inference configuration uses `extrinsics_attn`. Normalized 4 × 4 camera extrinsic matrices are grouped over four video frames and flattened into 64-dimensional inputs, aligning camera features with the temporal compression of the video latents. Learned pose embeddings and projections implement the figure's **Pose Encoder → Camera Proj** path. At each double-stream block, video tokens query the projected camera features through cross-attention after the video MLP. With `per_chunk_camera_attn=true` and `camera_chunk_size=1`, camera attention is aligned to individual latent frames.

### Segment-Autoregressive Diffusion Transformer

The generation backbone is a **dense multimodal diffusion transformer (MMDiT)**. Video latents enter through **Patch Embed**, while refined text tokens enter a separate stream. The **Timestep Embed** supplies noise-level conditioning: each block uses it to modulate the two streams with learned shifts, scales, and residual gates.

Within a block, text and video interact through **segment-wise causal joint attention**, with 3D RoPE encoding video positions and the layer's KV cache supplying context from earlier segments. The two streams then pass through separate MLPs. **Camera cross-attention** updates the video branch using video queries and camera keys/values. Text features continue to the next block; after the last block, the output head uses only the video stream to predict latent-space flow velocity. The sampler uses these predictions to denoise the segment before video decoding.

The model architecture is illustrated in the following table:

| Property | Configuration |
|:---|:---|
| Model identifier | `Hy-Nomas` |
| Transformer blocks | 54 double-stream blocks; 0 single-stream blocks |
| Hidden size | 2,048 |
| Attention heads | 16 heads; 128 dimensions per head |
| Feed-forward expansion | 4×; intermediate size 8,192 |
| Latent input / output channels | 32 / 32 |
| Latent patch size, time × height × width | 1 × 1 × 1 |
| Position encoding | 3D RoPE; temporal/height/width dimensions `[16, 56, 56]`; theta 256 |
| Text conditioning | 3,584-dimensional Qwen features; two-layer token refiner |
| Camera conditioning | Extrinsic embeddings with cross-attention in the double-stream blocks |
| Denoising prediction | Flow velocity; Euler ODE sampling in the inference configuration |

At each turn, the DiT denoises the current segment while attending to all past KV cache and the current conditioning. Attention is causal across segments, so future segments are not required to generate the current one. Cached attention keys and values are reused when generation advances to the next segment.

The standard configuration keeps the full history (`max_cache_segments=null`, sliding window disabled). The single-GPU configuration selects a bounded set of historical latent frames for GPU attention and retains an archive on CPU. Its default history budget is **18 latent frames**; that budget applies to historical context, not to the length of the current segment.

### Video Latents and PixelUMM Decoder

Hy-Nomas uses **DCAE-V `f32t4c32` latents**: 32 channels, 32× spatial compression in each dimension, and 4× temporal compression. The DiT produces latents in this representation. The default inference pipeline decodes them with a **fine-tuned PixelUMM decoder**.

The decoder uses a transformer with **36 layers**, a **4,096-dimensional hidden size**, **32 query heads**, and **8 KV heads**. It conditions pixel reconstruction on the generated DCAE-V latents and processes RGB video in 4 × 16 × 16 tubelets. The configuration uses **one PixelUMM decoding step**, with temporal windows of 10 latent frames and an overlap of 5 latent frames. This decoding step is separate from the DiT's 8 denoising steps.

Architecture values are specified in the [DiT model definitions](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/modules/__init__.py), [DiT implementation](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/nomas_cpt.py), [PixelUMM implementation](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/vae/pixelumm_decoder/model.py), and [inference configuration](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/configs/experiment/inference.yaml).

## Model Assets

Select compatible generation and decoding checkpoints for the inference configuration you use.

| Component | Asset | Role | Path in this repository |
|:---|:---|:---|:---|
| DiT | **Distilled DiT (FP32)** | Main checkpoint for 8-step inference and the interactive demo; the standard configuration loads the DiT in BF16. | `DiT/distilled/diffusion_pytorch_model_ema_0_995.safetensors` |
| DiT | **Quantized Distilled DiT (INT8)** | Quantized checkpoint for the single-GPU configuration; weights are stored in INT8 and DiT linear computation remains BF16. | `DiT/distilled_int8/diffusion_pytorch_model_ema_0_995_int8.safetensors` |
| DiT | **Base autoregressive DiT (FP32)** | Non-distilled model; use the distilled model with the 8-step examples below. | `DiT/base_ar/diffusion_pytorch_model_fp32.safetensors` |
| Adapter | **Cinematic LoRA** | Optional visual-quality adapter for a compatible floating-point DiT. | `DiT/lora_weights/cinematic/` |
| Adapter | **Robotics LoRA** | LoRA adapter trained on the [RealSource-World](https://huggingface.co/datasets/RealmanRobot/RealSource-World) real-world robotic-arm dataset, to be merged into the distilled DiT to enhance the robotics simulation capability of generated worlds. | `DiT/lora_weights/dual_arm_robotics/` |
| Video autoencoder | **DCAE-V** | Defines the 32-channel compressed video representation and provides video encoding and decoding. | `VAE/DCAE-V/dc-ae-v-1.0-f32t4c32-bf16.pt` |
| Video decoder | **Fine-tuned PixelUMM** | Default decoder for generated DCAE-V latents. | `VAE/PixelUMM_FT/diffusion_pytorch_model.safetensors` |
| Video decoder | **Quantized PixelUMM (FP8)** | Decoder checkpoint for the low-memory configuration. | `VAE/PixelUMM_FT_FP8/diffusion_pytorch_model_fp8.safetensors` |
| Prompt enhancement | **Nomas-PE** | Separate online service that converts user instructions into structured prompts for the web demo. | `PE/` |

Standard offline inference requires the **distilled DiT**, a **matching PixelUMM checkpoint**, and the **Qwen text encoder**. The single-GPU configuration requires the compatible **INT8 DiT** and **FP8 PixelUMM** pair. The INT8 loader does not support loading a separate LoRA adapter at inference time.

Download the applicable assets from this repository, preserving the `DiT/`, `VAE/`, and `PE/` directory layout. The inference commands below use `HY_NOMAS_MODEL_DIR` to locate the downloaded model repository. The text encoder is automatically downloaded from `Qwen/Qwen2.5-VL-7B-Instruct` by Huggingface and reused from the local cache. To use an existing local copy, append `model.text_encoder.model_name=/path/to/Qwen2.5-VL-7B-Instruct`.

## Usage

### Environment Setup

Run inference with the [Hy-Nomas code repository](https://github.com/Tencent-Hunyuan/Hy-Nomas):

```bash
git clone https://github.com/Tencent-Hunyuan/Hy-Nomas.git
cd Hy-Nomas
```

Choose one of the following two setup options. **We strongly recommend the pre-packaged Docker image**, which provides the Python environment, PyTorch, and the required CUDA attention kernels together.

#### Option 1: Pre-packaged Docker Image (Recommended)

Prepare a Linux host with a compatible NVIDIA driver, Docker, and NVIDIA Container Toolkit. Run these commands from the code repository root:

```bash
export HY_NOMAS_IMAGE="hynomasoss/hynomasoss:cu130"

docker pull "$HY_NOMAS_IMAGE"
docker run --rm -it --gpus all --ipc=host --network=host \
  -v "$PWD:/workspace/Hy-Nomas" \
  -w /workspace/Hy-Nomas \
  "$HY_NOMAS_IMAGE" bash
```

Run the remaining commands inside the container, using its pre-installed Python environment. Place model assets under the mounted repository or add a volume mount for your model directory; use the paths visible inside the container in the launch commands below.

#### Option 2: Manual Installation

Prepare Linux, Python 3.12+, uv, a compatible NVIDIA driver, the CUDA 13.0 Toolkit (`nvcc`), and a C++ compiler. Run the following from the code repository root:

```bash
uv sync --extra all
source .venv/bin/activate
```

The `all` extra includes PyTorch 2.10.0 (CUDA 13.0), FlashAttention 2, FlashAttention 3, and MagiAttention. `pyproject.toml` configures the PyTorch CUDA index, the official FA3 source, and disables build isolation for the attention kernels so their builds can use the environment's PyTorch. Kernel compilation may take some time.

### Model Paths

In the environment used for inference, set `HY_NOMAS_MODEL_DIR` to the local model repository root containing the weight paths listed above. When using Docker, use a path visible inside the container.

```bash
export HY_NOMAS_MODEL_DIR="/path/to/Hy-Nomas-models"
```

Run the commands below from the Hy-Nomas **code repository root**. They use this variable to read the weights and example prompts from the model repository.

### Prepare Prompts

Offline inference accepts a JSON list of video-generation requests. Each request can contain multiple `segments`. Both segments and their `contained_actions` use `start_time` and `end_time` strings in `MM:SS.mmm` format (minutes:seconds.milliseconds). The example below contains two 5-second segments covering 0–5 seconds and 5–10 seconds. The first segment describes the initial world, and later segments use `description_change` to describe how it should evolve.

The inference commands below use the bundled [example prompt file](examples/prompts.json) in the model repository. For custom content, save a JSON file in the following format and set `inference.prompt=/path/to/prompts.json`:

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

The configuration derives segment lengths from event timestamps (`inference.video_length=event`). Action timestamps in this example use the same video timeline; the configuration normalizes them to each segment internally.

### Standard Inference

The standard configuration uses **8-way sequence parallelism** (`sp_size=8`) and distributed PixelUMM decoding. Its default launch therefore requires eight GPUs in one inference group. Run from the code repository root:

```bash
bash scripts/inference/inference_from_config.sh configs/experiment/inference.yaml \
  dit_weight="$HY_NOMAS_MODEL_DIR/DiT/distilled/diffusion_pytorch_model_ema_0_995.safetensors" \
  model.vae.checkpoint="$HY_NOMAS_MODEL_DIR/VAE/PixelUMM_FT/diffusion_pytorch_model.safetensors" \
  inference.prompt="$HY_NOMAS_MODEL_DIR/examples/prompts.json" \
  inference.save_path=./outputs/distill
```

Generated videos are written under `inference.save_path`. The configuration also saves generated latents and prompt text.

| Setting | Default | Override |
|:---|:---|:---|
| Output resolution, height × width | 720 × 1280 | `'inference.video_size=[480,832]'` |
| Output video frame rate | 24 FPS | `inference.video_fps=24` |
| DiT denoising steps | 8 | `inference.infer_steps_video=8` |
| Solver | Euler ODE | `inference.solver_type=euler` |
| Text / camera guidance scale | 1.0 / 1.0 | `inference.cfg_scale_video=1.0 inference.camera_cfg_scale=1.0` |
| Random seed | 42 | `inference.seed=42` |
| Camera translation / rotation strength | 1.0 / 2.5 | `inference.trajectory_translation_scale=1.0 inference.trajectory_rotation_scale=2.5` |

For camera-controlled generation, append `inference.camera_trajectory=/path/to/camera.npz`. The trajectory file contains camera-to-world matrices `c2ws` with shape `[N, 4, 4]` and camera `intrinsics` with shape `[N, 3, 3]`; align it with the requested video duration and frame rate. The repository includes [camera trajectory utilities](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/camera/geometry/generate_npz_trajectories.py).

### Single-GPU Low-Memory Inference

Use `configs/experiment/single_gpu_low_mem_inference.yaml` for **single NVIDIA GeForce RTX 4090** inference. This configuration inherits the standard architecture, prompt processing, resolution, frame rate, and 8-step DiT schedule, and changes memory management and execution:

- **INT8 DiT and KV storage:** Store DiT weights and cached keys/values in INT8 while retaining BF16 DiT linear and attention computation.
- **Bounded GPU history:** Select up to 18 historical latent frames using `temporal_context` sampling, with earlier history archived on CPU.
- **CPU offload:** Move the text encoder, DiT, and decoder to the GPU for their processing stages and return them to CPU afterward.
- **Single-GPU kernels:** Use FlexAttention for the DiT, CUTLASS FP8 for the decoder, and `sp_size=1`.

Prepare the compatible INT8 DiT and FP8 PixelUMM checkpoints. Run on a host or in a container exposing **one GPU to `nvidia-smi`**, which the launcher uses to count GPUs:

```bash
bash scripts/inference/inference_from_config.sh configs/experiment/single_gpu_low_mem_inference.yaml \
  dit_weight="$HY_NOMAS_MODEL_DIR/DiT/distilled_int8/diffusion_pytorch_model_ema_0_995_int8.safetensors" \
  model.vae.checkpoint="$HY_NOMAS_MODEL_DIR/VAE/PixelUMM_FT_FP8/diffusion_pytorch_model_fp8.safetensors" \
  inference.prompt="$HY_NOMAS_MODEL_DIR/examples/prompts.json" \
  inference.save_path=./outputs/single_gpu
```

System RAM must accommodate the offloaded models and the growing history archive. CPU–GPU transfers add latency. Peak GPU memory also depends on output resolution and the current segment length; the history budget does not cap current-segment memory.

### Interactive Demo

Try the [online interactive demo](https://hy-nomas.hy.tencent.com/) to start a world, continue it with text instructions or camera paths, and download the generated video.

For local deployment, follow the [web demo deployment guide](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/apps/README.md). It covers the frontend, gateway, GPU workers, single-GPU mode, and multiple-host deployment. **Nomas-PE is required for the web demo** and uses separate serving resources; the single-GPU claim above applies to video inference. The demo enables streaming decoding at segment boundaries.

## Runtime Considerations

- Full-history inference retains more context as generation continues and consumes increasing cache memory. The single-GPU configuration bounds the active GPU history while its CPU archive can continue to grow.
- The 24 FPS setting specifies the output video's playback frame rate. Generation speed depends on hardware, resolution, segment length, history, and the selected configuration.
- The 8-step examples require the distilled DiT and its compatible decoder. Architecture and sampling defaults are configuration details, rather than benchmark results.

## License

Hy-Nomas is licensed under Apache-2.0. Please refer to this repository's [LICENSE](https://huggingface.co/tencent/Hy-Nomas/blob/main/LICENSE) file for the applicable terms. Third-party models and components remain subject to their respective licenses.

## Acknowledgement

We thank the teams behind [Gemma 4](https://deepmind.google/models/gemma/gemma-4/), [Qwen3.8](https://qwen.ai/blog?id=qwen3.8), [Kimi-K3](https://github.com/MoonshotAI/Kimi-K3), [DC-AE](https://github.com/dc-ai-projects/DC-Gen), and [MagiAttention](https://github.com/SandAI-org/MagiAttention) for their valuable contributions to the community and the models, research, and tools that support this project.

## Contact

For questions, non-security bug reports, or suggestions, open an issue in the [Hy-Nomas repository](https://github.com/Tencent-Hunyuan/Hy-Nomas/issues) or contact [hy_nomas@tencent.com](mailto:hy_nomas@tencent.com). Report suspected security vulnerabilities through the repository's [security guidance](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/SECURITY.md).
