---
license: apache-2.0
language:
  - en
  - zh
pipeline_tag: image-text-to-text
tags:
  - minicpm-ocr
  - dspark
  - speculative-decoding
  - draft-model
  - gguf
  - llama.cpp
  - ocr
base_model: openbmb/MiniCPM-OCR-1.0
base_model_relation: finetune
---

<div align="center">

Official Demo([CN](https://platform.modelbest.cn/console/playground/document-parse) / [Global](https://platform.modelbest.ai/console/playground/document-parse)) · Basic Demo([CN](http://82.157.64.212:10111/playground/document-parse) / [Global](https://huggingface.co/spaces/openbmb/MiniCPM-OCR))
\
[GitHub](https://github.com/OpenBMB/MiniCPM-OCR) · [Free API](https://platform.modelbest.ai/console/docs/api/document-parse) · [Usage](https://github.com/OpenBMB/MiniCPM-OCR#using-minicpm-ocr) · [DSpark](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-DSpark) · [Skill](https://github.com/OpenBMB/MiniCPM-OCR#skill)

</div>

# MiniCPM-OCR 1.0 DSpark — GGUF

> **GGUF build of the [DSpark draft head](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-DSpark) for
> [MiniCPM-OCR 1.0](https://huggingface.co/openbmb/MiniCPM-OCR-1.0).** A draft model, not a standalone OCR model — pair it
> with the matching main checkpoint.

## Files

| File | Size |
| :--- | ---: |
| `dspark-MiniCPM-OCR-1_0-F16.gguf` | 0.606 GB |
| `dspark-MiniCPM-OCR-1_0-Q8_0.gguf` | 0.327 GB |
| `dspark-MiniCPM-OCR-1_0-Q6_K.gguf` | 0.255 GB |
| `dspark-MiniCPM-OCR-1_0-Q5_K_M.gguf` | 0.233 GB |
| `dspark-MiniCPM-OCR-1_0-Q5_K_S.gguf` | 0.232 GB |
| `dspark-MiniCPM-OCR-1_0-Q5_1.gguf` | 0.243 GB |
| `dspark-MiniCPM-OCR-1_0-Q5_0.gguf` | 0.232 GB |
| `dspark-MiniCPM-OCR-1_0-Q4_K_M.gguf` | 0.211 GB |
| `dspark-MiniCPM-OCR-1_0-Q4_K_S.gguf` | 0.209 GB |
| `dspark-MiniCPM-OCR-1_0-Q4_1.gguf` | 0.220 GB |
| `dspark-MiniCPM-OCR-1_0-Q4_0.gguf` | 0.209 GB |

Use the main model's projector (`mmproj-model-f16-4x.gguf` from
[MiniCPM-OCR-1.0-gguf](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-gguf)); this repository contains only the draft.

## Usage

```bash
llama-cli \
  -m MiniCPM-OCR-1_0-Q8_0.gguf \
  --mmproj mmproj-model-f16-4x.gguf \
  -md dspark-MiniCPM-OCR-1_0-Q8_0.gguf \
  --spec-type draft-dspark \
  --image page.png -p "Text Recognition:" \
  --jinja -ngl 99 -ngld 99 -fa on
```

`-md` is the draft model and `--spec-type draft-dspark` enables the draft; `-ngld` offloads draft
layers to GPU.

> `llama-mtmd-cli` does not accept a draft model. Use `llama-cli` or `llama-server` when enabling
> DSpark with multimodal input.

Each tier carries the **absolute** target token IDs in its `d2t` tensor (the safetensors export
stores them delta-encoded).

## Related checkpoints

| Format | Hugging Face | ModelScope |
| :--- | :--- | :--- |
| BF16 (original) | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-1.0) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-1.0) |
| GGUF (llama.cpp) | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-gguf) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-1.0-gguf) |
| AWQ W4A16 | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-AWQ) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-1.0-AWQ) |
| GPTQ W4A16 | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-GPTQ) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-1.0-GPTQ) |
| DSpark draft (BF16) | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-DSpark) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-1.0-DSpark) |
| DSpark draft (GGUF) **(this repo)** | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-1.0-DSpark-gguf) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-1.0-DSpark-gguf) |

## FAQ

Installation, model downloads, GPU memory, input formats, and unexpected outputs:
[FAQ](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/faq_en.md).

## License

Model weights, code, and documentation are released under the
[Apache License 2.0](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/LICENSE).
