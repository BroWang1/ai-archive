---
license: other
license_name: apache-2.0-and-cc-by-nc-4.0
license_link: https://github.com/inclusionAI/CodeWorldModel#acknowledgements-and-license
language:
- en
pipeline_tag: video-to-video
tags:
- video-generation
- world-model
- controllable-generation
- causal-dit
- streaming
---

<p align="center">
  <img src="assets/teaser.jpg" width="100%" alt="Code World Model 2.0 overview: diverse proxies, action-driven branching, adaptive proxy granularity, long-horizon 360° orbit, subject and camera control, and real gameplay proxies rendered by Invoker-Render">
</p>

<h1 align="center">Code World Model 2.0: Towards Infinite Controllable Video Generation</h1>

<p align="center">
  <b>Invoker-Render</b>: proxy-conditioned video rendering
</p>

<p align="center">
  <a href="https://arxiv.org/abs/2611.22925">arXiv</a> |
  <a href="https://www.inclusion-ai.org/CodeWorldModel/">Homepage</a> |
  <a href="https://github.com/inclusionAI/CodeWorldModel">GitHub</a>
</p>

Code World Model 2.0 keeps the world state in an upstream engine. Visual proxies fix the camera path, scene layout, and object motion, and a video model generates the appearance.

This repository hosts the **causal streaming DiT weights of Invoker-Render**. The model takes a structural proxy, one appearance reference image, and text. The companion [CodeWorldModel](https://github.com/inclusionAI/CodeWorldModel) inference code runs causal four-step streaming generation and is built on MiniMax-H3, SGLang, and SGLang-Omni.

## Highlights

- **Long-horizon streaming**: a fixed appearance anchor and a bounded history window let a session run for as long as proxy frames arrive.
- **Multi-granularity control**: accepts semantic maps, sparse 3D boxes, subject masks, shaded geometry, and boxes with skeletons.
- **Interactive deployment**: the companion code provides a WebSocket session service, a file client, and a browser client.

## Weights

- **Repository root: main causal streaming DiT weights.** 33.12B parameters stored in FP32, 29 safetensors shards with 638 tensors, about 132.5 GB, not quantized, and loadable as is.
- `config.json` keeps the `MiniMaxH3Transformer3DModel` architecture identifier; the shard index is `diffusion_pytorch_model.safetensors.index.json`.
- **`bidirectional_lora/teacher-live.safetensors`: LoRA weights of the bidirectional teacher** (about 2.3 GB), with MiniMax-H3 as the base model. It is a different model from the causal weights in the repository root; do not apply it on top of them.
- This repository does not include the VAE, Qwen, the causal decoder, silence tensors, or a prepared inference bundle. Prepare matching assets separately.

## Inference

Use the companion [CodeWorldModel](https://github.com/inclusionAI/CodeWorldModel) repository. Follow its `README.md` and `docs/INFERENCE.md` to set up the environment and prepare a bundle, then start the service or run file inference with `invoker_render.py`. The default `production` profile uses eight NVIDIA GPUs on one node.

The inputs are a **1344×768 RGB first image, a 24 FPS proxy video, and a text prompt**. File inference requires `17*N+5` proxy frames, at least 39. 24 FPS is the frame rate of the video timeline, not inference throughput.

## License

This repository is subject to [Apache-2.0](https://www.apache.org/licenses/LICENSE-2.0) and [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/) (non-commercial) terms.

