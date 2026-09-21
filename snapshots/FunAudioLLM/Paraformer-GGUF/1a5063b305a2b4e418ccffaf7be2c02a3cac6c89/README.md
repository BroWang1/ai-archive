---
license: apache-2.0
language:
- zh
- en
library_name: gguf
tags:
- automatic-speech-recognition
- asr
- paraformer
- funasr
- llama.cpp
- ggml
- cpu
- chinese
pipeline_tag: automatic-speech-recognition
---

# Paraformer-zh · GGUF (FunASR llama.cpp runtime)

GGUF build of FunASR's **Paraformer-zh** (SAN-M encoder + CIF predictor + SAN-M decoder, non-autoregressive) for the zero-Python, CPU/edge **[FunASR llama.cpp runtime](https://github.com/modelscope/FunASR/tree/main/runtime/llama.cpp)** — fast Mandarin ASR, **~21× real-time on CPU**.

## Get it running (no Python, no build)

These are GGUF weights for the **[FunASR llama.cpp runtime](https://github.com/modelscope/FunASR/tree/main/runtime/llama.cpp)** — a whisper.cpp-style, single self-contained binary for CPU / edge. Grab a prebuilt binary, then fetch this model and run:

- **Prebuilt binaries (Linux / macOS / Windows) → [GitHub Releases](https://github.com/modelscope/FunASR/releases)** (tag `runtime-llamacpp-v*`)
- **Deployment guide & qualified benchmarks → [funasr.com/deploy/llama-cpp](https://www.funasr.com/deploy/llama-cpp.html)**

```bash
bash download-funasr-model.sh paraformer ./gguf
llama-funasr-paraformer -m ./gguf/paraformer-q8.gguf --vad ./gguf/fsmn-vad.gguf -a audio.wav
```

## Files
| file | size | notes |
|---|---|---|
| `paraformer-f16.gguf` | 435 MB | **recommended** (f16 matmul weights) |
| `paraformer-q8.gguf` | ~217 MB | **recommended** — half of f16, same accuracy |
| `paraformer.gguf` | 863 MB | f32 reference |

## Usage
The binary prints **transcription text** directly (no Python detok). `--ids` for raw ids.
```bash
llama-funasr-paraformer -m paraformer-f16.gguf -a audio.wav --vad fsmn-vad.gguf
```
On CPU (8 threads): **9.85 % CER** on the 184-clip Mandarin benchmark (vs whisper.cpp 22–31 %).

## Links
- 🧩 Runtime & build: **[FunASR · runtime/llama.cpp](https://github.com/modelscope/FunASR/tree/main/runtime/llama.cpp)** — ⭐ **Star [FunASR](https://github.com/modelscope/FunASR)!**
- Source model: [funasr/paraformer-zh](https://huggingface.co/funasr/paraformer-zh)
