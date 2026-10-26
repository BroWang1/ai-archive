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
  <a href="README_CN.md">中文</a>&nbsp;｜&nbsp;English
</p>

<p align="center">
  <img src="assets/logo-en.png" alt="Hy-Nomas" width="400"/>
</p>

<h1 align="center">Hy-Nomas: Towards Free-Form Interactive World Generation</h1>

<p align="center">BF16 weights for Diffusers · <code>HyNomasModularPipeline</code></p>

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

<video controls playsinline preload="metadata" width="100%" src="https://hy-nomas.hy.tencent.com/gallery/hy_nomas_promo.mp4"></video>

## Model Introduction

**Hy-Nomas** is a video world generation model that supports free-form, multi-turn interaction through text instructions and camera control. It generates a world one video segment at a time, allowing users to introduce objects, change styles and scenes, describe actions, or control the camera as generation continues.

The model combines a segment-autoregressive diffusion transformer (DiT), a Qwen text encoder, camera-conditioning modules, and a PixelUMM video decoder. A persistent key/value (KV) cache carries context between segments. This directory provides the distilled model in **BF16 Diffusers format**. The example below uses **4 denoising steps**, with **704 × 1280** output at **24 FPS**.

## Key Features

- **Free-form interaction:** Guide successive segments with instructions about subjects, actions, appearance, style, and environment.
- **Camera control:** Supply camera trajectories alongside text to control viewpoint and movement.
- **Continuous generation:** Reuse earlier context through a KV cache when extending the same world.
- **Distilled inference:** Generate each segment with 4 DiT denoising steps in the example below and decode its latents with a fine-tuned PixelUMM decoder.
- **Diffusers integration:** Load the bundled transformer, text encoder, tokenizer, scheduler, and decoder with `HyNomasModularPipeline`.

## Hy-Nomas-Bench

We also release **[Hy-Nomas-Bench](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench)**, a suite of four benchmarks with **280 test cases** covering multi-turn free-form text interaction, camera navigation, interleaved text and camera control, and spatial memory. It evaluates interactive controllability and consistency during continuous world generation, providing structured prompts, interaction sequences, keyboard timelines, and reference camera trajectories. See the [Hy-Nomas-Bench dataset repository](https://huggingface.co/datasets/tencent/Hy-Nomas-Bench) for downloads, data formats, and inference instructions.

## Model Architecture

Hy-Nomas performs diffusion in a compressed video latent space and autoregression across video segments. Text, camera motion, and cached history condition the generation of each new segment.

![Hy-Nomas framework: structured prompts, video latents, and camera trajectories feed dual-stream MMDiT blocks with segment-wise causal joint attention, timestep modulation, camera cross-attention, and a persistent KV cache.](assets/method_framework_h.png)

*Hy-Nomas framework. The inference configuration uses 54 dual-stream MMDiT blocks (N = 54). Purple, blue, and green indicate the text, video, and camera paths, respectively.*

The figure's video-encoder path illustrates how video is represented as DCAE-V latents. In the text-to-video inference flow below, each new segment starts from Gaussian noise in that latent space and uses the KV cache for generated history. The MLLM is the Qwen text encoder, and the default video decoder is the fine-tuned PixelUMM described below.

### Text and Camera Conditioning

**Text conditioning.** The text encoder uses the language-model component of **Qwen/Qwen2.5-VL-7B-Instruct**. Its 3,584-dimensional hidden states pass through a two-layer token refiner and are projected into the DiT's 2,048-dimensional hidden space. Segment-specific prompts let users change the requested content as generation proceeds.

**Online prompt enhancement.** The original web demo uses **Nomas-PE**, a separate service that converts user instructions into structured generation prompts. This Diffusers pipeline accepts plain text or prepared structured prompts directly and does not run Nomas-PE.

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

The Diffusers pipeline retains the attention KV cache across segments. Continued generation can reuse the state returned by an earlier call; the usage guide below describes this workflow.

### Video Latents and PixelUMM Decoder

Hy-Nomas uses **DCAE-V `f32t4c32` latents**: 32 channels, 32× spatial compression in each dimension, and 4× temporal compression. The DiT produces latents in this representation. The default inference pipeline decodes them with a **fine-tuned PixelUMM decoder**.

The decoder uses a transformer with **36 layers**, a **4,096-dimensional hidden size**, **32 query heads**, and **8 KV heads**. It conditions pixel reconstruction on the generated DCAE-V latents and processes RGB video in 4 × 16 × 16 tubelets. The configuration uses **one PixelUMM decoding step**, with temporal windows of 10 latent frames and an overlap of 5 latent frames. This decoding step is separate from the DiT's 4 denoising steps in the example below.

Architecture values are specified in the [DiT model definitions](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/modules/__init__.py), [DiT implementation](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/dit/nomas_cpt.py), [PixelUMM implementation](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/hymm/models/vae/pixelumm_decoder/model.py), and [inference configuration](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/configs/experiment/inference.yaml).

## Model Assets

This directory contains the BF16 Diffusers conversion of the distilled Hy-Nomas model, serialized with `HyNomasModularPipeline.save_pretrained()`.

| Component | Directory / file | Contents |
|:---|:---|:---|
| Pipeline | `modular_model_index.json` | Component classes and loading configuration |
| Transformer | `transformer/` | Distilled `HyNomasTransformer3DModel`, BF16 Safetensors shards and configuration |
| Video decoder | `decoder/` | Fine-tuned `PixelUMMDecoder`, BF16 Safetensors shards and configuration |
| Text encoder | `text_encoder/` | `Qwen2_5_VLTextModel`, BF16 Safetensors shards and configuration |
| Tokenizer | `tokenizer/` | Qwen tokenizer files |
| Scheduler | `scheduler/` | `FlowMatchEulerDiscreteScheduler` configuration |

The [original model repository](https://huggingface.co/tencent/Hy-Nomas) provides the native checkpoints, quantized variants, adapters, and Nomas-PE assets. Those additional assets are not included in this Diffusers directory.

## Usage

### Inference with Diffusers

Upgrade your diffusers to use `HyNomasModularPipeline`.

```bash
pip install -e "diffusers[hy-nomas] @ git+https://github.com/jiaxiangc/diffusers.git@hy-nomas"
```

Hy-Nomas supports multi-turn interactive generation. This example generates two five-second segments with four denoising steps per segment. Set `model_path` to your downloaded `Hy-Nomas-Diffusers` directory.

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

Each prompt describes one segment. Action timestamps are relative to the start of that segment, so both segments use `00:00.000`–`00:05.000`. At 24 FPS, `num_frames=240` and `segment_latent_lengths=[30, 30]` generate ten seconds in total. These are prepared structured prompts; the pipeline does not call a prompt-enhancement service.

### Reference Attention

The example uses PyTorch SDPA by default. To match the native implementation's attention backends, install its compatible FlashAttention 2, FlashAttention 3, and MagiAttention kernels following the [Hy-Nomas repository](https://github.com/Tencent-Hunyuan/Hy-Nomas), then enable them after loading the models and before generation:

```python
pipe.transformer.enable_reference_attention(text_backend="flash_varlen", deterministic=True)
```

These optional kernels are not installed by the `hy-nomas` extra. See the [Diffusers Hy-Nomas guide](https://github.com/jiaxiangc/diffusers/blob/hy-nomas/docs/source/en/api/pipelines/hy_nomas.md) for plain-text prompts, camera control, continued generation, and the conditions for matching the native implementation.

## Runtime Considerations

- The example loads the BF16 components onto one CUDA GPU; memory use also depends on resolution, segment length, and cached history. The original INT8/FP8 RTX 4090 configuration is a separate native deployment.
- The 24 FPS setting controls playback rate. Generation speed depends on the hardware and inference settings.
- Retaining history across segments increases KV cache memory use.

## License

Hy-Nomas is licensed under Apache-2.0. Please refer to this repository's [LICENSE](LICENSE) file for the applicable terms. Third-party models and components remain subject to their respective licenses.

## Acknowledgement

We thank the teams behind [Gemma 4](https://deepmind.google/models/gemma/gemma-4/), [Qwen3.8](https://qwen.ai/blog?id=qwen3.8), [Kimi-K3](https://github.com/MoonshotAI/Kimi-K3), [DC-AE](https://github.com/dc-ai-projects/DC-Gen), and [MagiAttention](https://github.com/SandAI-org/MagiAttention) for their valuable contributions to the community and the models, research, and tools that support this project.

## Contact

For questions, non-security bug reports, or suggestions, open an issue in the [Hy-Nomas repository](https://github.com/Tencent-Hunyuan/Hy-Nomas/issues) or contact [hy_nomas@tencent.com](mailto:hy_nomas@tencent.com). Report suspected security vulnerabilities through the repository's [security guidance](https://github.com/Tencent-Hunyuan/Hy-Nomas/blob/HEAD/SECURITY.md).
