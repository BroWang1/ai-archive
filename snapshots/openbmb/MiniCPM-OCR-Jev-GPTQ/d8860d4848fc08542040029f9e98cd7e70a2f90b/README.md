---
license: apache-2.0
language:
  - en
  - zh
pipeline_tag: image-text-to-text
tags:
  - minicpm-ocr
  - ocr
  - quality-assessment
  - multimodal
  - 4-bit
  - quantized
  - compressed-tensors
base_model: openbmb/MiniCPM-OCR-Jev
base_model_relation: quantized
---

<div align="center">

[GitHub](https://github.com/OpenBMB/MiniCPM-OCR) · [Usage](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/minicpm_ocr_jev_tutorial_en.md)

</div>

> **This repository hosts the GPTQ W4A16 quantized version of
> [MiniCPM-OCR Jev](https://huggingface.co/openbmb/MiniCPM-OCR-Jev).** For the original BF16 weights and the base model
> card, see [openbmb/MiniCPM-OCR-Jev](https://huggingface.co/openbmb/MiniCPM-OCR-Jev). Everything below describes the model
> itself; see [Quantization](#quantization) for what changed.
**MiniCPM-OCR Jev** (2B) is an OCR **quality-assessment** model for text, formula, and table
regions. Given a region image and a candidate OCR result, it returns a **score from 0 to 1** —
higher means the candidate is more likely correct.

## MiniCPM-OCR Jev

**MiniCPM-OCR Jev** is a **2B OCR quality-assessment model** for text, formula, and table
regions. Given a region image and a candidate OCR result, it returns a **score from 0 to 1** —
higher means the candidate is more likely correct. Use it to auto-accept reliable regions,
route the rest to human review, or pick the best result among several OCR models.

- 🛡️ **A small model that beats larger ones**: at only 2B parameters, decision AUROC (×100) on
  [JevOCRBench](https://huggingface.co/datasets/openbmb/JevOCRBench) is **93.6**, above
  JEV-35B-A3B (90.1) and close to Qwen3.5-397B-A17B (93.8).
- 🧩 **Stable generalization**: on parses from MiniCPM-OCR 1.0, GLM-OCR, PaddleOCR-VL-1.6, and
  Xiaomi-OCR-0, AUROC (×100) stays in **91.9–93.4**.

### Architecture

Trained from **Qwen3.5-2B**. The vision encoder and language backbone are retained, and the
language-model output head `lm_head` is replaced with a **binary classification head** that
learns whether a candidate is correct.

| Item | Description |
| :--- | :--- |
| Assessment unit | One text / formula / table region plus its candidate OCR result |
| Original region image | The crop from the document |
| Candidate content | OCR text and an image rendered from that text |
| Output | Score in 0–1; higher = more likely correct |

When calling the cloud API, the Docker image, or the SDK service with a built-in renderer,
supply the original region image, the candidate text, and the region `category`
(`text` / `formula` / `table`) — the service renders internally. A service without a renderer
requires you to supply the rendered image as well.

### Evaluation Results

The table below reports overall and per-category AUROC (×100) on JevOCRBench. Higher values
indicate better discrimination between correct and incorrect parsing results.

<p align="center"><img src="https://raw.githubusercontent.com/OpenBMB/MiniCPM-OCR/main/assets/minicpm-ocr/jev-benchmark-score-table.png" alt="Overall, text, formula, and table AUROC on JevOCRBench, highlighting MiniCPM-OCR Jev." width="100%"></p>

### Discrimination across OCR models

| OCR model | MiniCPM-OCR 1.0 | GLM-OCR | PaddleOCR-VL-1.6 | Xiaomi-OCR-0 |
| :--- | ---: | ---: | ---: | ---: |
| AUROC (×100) | 92.7 | 91.9 | 93.4 | 93.1 |

Same 200 samples drawn at random from JevOCRBench; four models parse them independently, every
candidate is hand-labelled, then scored by MiniCPM-OCR Jev. Maximum gap **1.5 points**.

### Automatic screening to reduce human review

Score the parsed result for each region and choose a threshold using samples from your
application. Results above the threshold proceed automatically; the rest go to human review.
A higher threshold typically reduces the number of results that pass automatically, so monitor
both the accuracy of automatically accepted results and the volume of human review.

<p align="center"><img src="https://raw.githubusercontent.com/OpenBMB/MiniCPM-OCR/main/assets/minicpm-ocr/review-free-en.png" alt="Accuracy versus review-free rate for legal documents, financial receipts, and complex documents." width="100%"></p>

### Selecting across models to improve parsing quality

Use the same layout segmentation to have several OCR models parse each region. MiniCPM-OCR Jev
scores the candidates for the same region, selects the highest-scoring candidate, and combines
the selected results in reading order. If all candidates fall below the application threshold,
the region can still be sent for human review.

<p align="center"><img src="https://raw.githubusercontent.com/OpenBMB/MiniCPM-OCR/main/assets/minicpm-ocr/multi-models-improvements-en.png" alt="Parsing-quality gains from MiniCPM-OCR Jev scoring for MiniCPM-OCR 1.0, Xiaomi OCR, and PaddleOCR-VL 1.6." width="100%"></p>

Candidates for the same region must share the crop and content boundaries. Jev selects among
existing candidates, so quality is bounded by their coverage and correctness.

### Examples

The figure below compares the original image with candidates 1 and 2, showing how MiniCPM-OCR
Jev scores text, formula, and table candidates.

<p align="center"><img src="https://raw.githubusercontent.com/OpenBMB/MiniCPM-OCR/main/assets/minicpm-ocr/jev-case-en.png" alt="Three examples for text, formulas, and tables: original, candidate 1 and candidate 2, with MiniCPM-OCR Jev scores." width="100%"></p>

## Quick start

| Deployment | Guide |
| :--- | :--- |
| Cloud API | [Single-candidate scoring, best-of-N, batched best-of-N](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/minicpm_ocr_jev_api_en.md) (stub — being written) |
| Docker / local SDK | [Environment, rendering options, service startup](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/minicpm_ocr_jev_tutorial_en.md) |
| vLLM backend | [Service configuration with and without a renderer](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/vllm_deploy_jev_en.md) |
| SGLang | [Deployment guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/sglang_deploy_jev_en.md) |
| llama.cpp | [GGUF deployment guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/llamacpp_deploy_jev_en.md) |
| Ollama | [Deployment guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/ollama_deploy_jev_en.md) |
| FlagOS (multi-chip) | [Deployment guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/flagos_deploy_en.md) |

When a service has a built-in renderer (cloud API, Docker, SDK), check `verdict` before using
the score — only `scored` means model scoring actually ran. Fixed values returned for precheck,
rendering, or forward-pass failures must not be read as low model scores.

### Pipeline integration

1. Keep page/region ids, original region images, region categories, and candidate text while
   parsing.
2. Submit image + category + candidate text (renderer service), or image + rendered image
   (renderer-less service).
3. Check status, associate scores with candidates, apply your threshold, and compare candidates
   within each region when several models are in play.
4. Emit selected results in the original reading order and keep pending regions for reviewers.

Use `score` for one candidate, `score_best` for best-of-N within a block, and `score_best_batch`
across blocks — see the [API documentation](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/minicpm_ocr_jev_api_en.md) (stub for now;
until it lands use the [vLLM deploy guide for Jev](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/vllm_deploy_jev_en.md)).

### Fine-tuning

[ms-swift guide](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/finetune_jev_en.md): data format, binary classification head
configuration, training commands, and JevOCRBench evaluation.

## Quantization

| Field | Value |
| :--- | :--- |
| Format | `compressed-tensors`, `pack-quantized` |
| Weight bits | 4 |
| Group size | 128 |
| Activations | BF16 (W4A16) |
| Tool | [llm-compressor](https://github.com/vllm-project/llm-compressor) |
| Recipe | `recipe.yaml` (kept in this repository) |

Weight footprint drops from about 4.43 GB (BF16) to about 2.41 GB.

| File | Notes |
| :--- | :--- |
| `model.safetensors` | 4-bit quantized weights |
| `config.json` | base config + `quantization_config` |
| `recipe.yaml` | quantization recipe (AWQ/GPTQ modifiers, layer mappings) |
| tokenizer / chat template / processor configs | tokenizer and processor configs |

The service name and request format are the same as the base model:

```bash
vllm serve openbmb/MiniCPM-OCR-Jev-GPTQ \
  --served-model-name MiniCPM-OCR-Jev \
  --trust-remote-code
```

## Related checkpoints

| Format | Hugging Face | ModelScope |
| :--- | :--- | :--- |
| BF16 (original) **(this repo)** | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-Jev) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-Jev) |
| GGUF (llama.cpp) | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-Jev-gguf) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-Jev-gguf) |
| AWQ W4A16 | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-Jev-AWQ) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-Jev-AWQ) |
| GPTQ W4A16 | [🤗](https://huggingface.co/openbmb/MiniCPM-OCR-Jev-GPTQ) | [ModelScope](https://modelscope.cn/models/OpenBMB/MiniCPM-OCR-Jev-GPTQ) |

Jev works on candidates from any parser. The companion parser is
[MiniCPM-OCR 1.0](https://huggingface.co/openbmb/MiniCPM-OCR-1.0).

## FAQ

Installation, model downloads, GPU memory, input formats, and unexpected outputs:
[FAQ](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/docs/faq_en.md).

## License

Model weights, code, and documentation are released under the
[Apache License 2.0](https://github.com/OpenBMB/MiniCPM-OCR/blob/main/LICENSE).
