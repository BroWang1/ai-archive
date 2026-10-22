---
library_name: transformers
license: other
license_name: youtu-llm
license_link: https://huggingface.co/tencent/Youtu-LLM-A7B-Base/blob/main/LICENSE.txt
pipeline_tag: image-text-to-text
---

# Youtu-LLM-A7B-Base

Youtu-LLM-A7B-Base is a pre-trained checkpoint of a vision-language Mixture-of-Experts model with about 120B total parameters and ~7B activated parameters per token. 
- This is a **base** model. We recommend to use raw text continuation, although `chat_template.jinja` is provided for further purpose. Custom modeling code is shipped in this repository and must be loaded with `trust_remote_code=True`.
- It combines a hybrid attention stack, KDA interleaved with GatedMLA, with a fine-grained MoE feed-forward network. The model accepts text and image inputs and is trained with a 262,144-token context window over 11.5T multimodal tokens.

## Model Summary

| Item | Value |
| --- | --- |
| Architecture | `YoutuVLMoEForConditionalGeneration` |
| Total / activated parameters | ~120B / ~7B per token |
| Layers | 48 |
| Hidden size | 3,072 |
| Attention | 3 Hybrid KDA linear attention + 1 MLA |
| MoE | 256 routed experts, top-8, 1 shared expert |
| Router | Quantile-balancing, w/ modality-aware expert bias |
| Vision encoder | Qwen3-VL-MoE style ViT |
| Context length | 262,144 |
| Vocabulary | 129,280 |
| dtype | bfloat16 |

## Evaluation Results

### Text

| Benchmark | Shots | Metric | DeepSeek-V4-Pro-Base | Youtu-LLM-A7B-Base |
| :--- | :---: | :---: | :---: | :---: |
| # Activated Params | - | - | 49B | 7B |
| # Total Params | - | - | 1.6T | 120B |
| **World Knowledge** | | | | |
| MMLU-Redux | 5-shot | EM | 93.21 | **96.00** |
| MMLU-Pro | 5-shot | EM | 67.11 | **78.61** |
| MMMLU | 5-shot | acc_norm | **86.48** | 84.02 |
| AGIEval | 0-shot | acc | **72.46** | 69.01 |
| SuperGPQA | 5-shot | acc_norm | **54.20** | 42.28 |
| GPQA (main) | 5-shot | acc_norm | 55.36 | **68.53** |
| INCLUDE | 5-shot | acc | **85.52** | 77.25 |
| **Math & Code** | | | | |
| BBH (CoT) | 3-shot | EM | **88.36** | 85.85 |
| GSM8K | 8-shot | EM | **91.96** | 88.86 |
| MGSM (zh) | 8-shot | EM | 79.90 | **82.60** |
| HumanEval+ | 0-shot | pass@1 | 76.80 | **78.05** |
| MBPP+ | 3-shot | pass@1 | 84.13 | **89.15** |
| LiveCodeBench v6 | 3-shot | pass@1 | 12.00 | **15.43** |
| RepoBench | 3-shot | EM | 32.72 | **33.57** |
| **Long Context** | | | | |
| RULER 4K-256K | 0-shot | score | **93.11** | 92.38 |
| LongBench v2 | 0-shot | EM | 46.30 | **48.53** |
| MRCR v2 (<256K) | 0-shot | score | 32.50 | **37.93** |

### Vision-Language

| Benchmark | Shots | Metric | MiMo-V2.5-Base | Youtu-LLM-A7B-Base |
| :--- | :---: | :---: | :---: | :---: |
| # Activated Params | - | - | 15B | 7B |
| # Total Params | - | - | 310B | 120B |
| **STEM** | | | | |
| AI2D (test) | 3-shot | EM | 85.23 | **89.83** |
| LogicVista | 3-shot | EM | 47.20 | **50.11** |
| WeMath | 3-shot | Score (Strict) | 45.14 | **56.19** |
| MMMU (dev+val) | 3-shot | EM | 65.56 | **67.11** |
| MMMU-Pro (10c) | 3-shot | EM | 50.12 | **53.87** |
| MathVista (mini) | 3-shot | acc (judge) | 70.00 | **73.20** |
| **VQA** | | | | |
| MMBench (EN v1.1) | 3-shot | EM | 85.14 | **88.08** |
| MMBench (CN v1.1) | 3-shot | EM | **86.15** | 85.14 |
| SimpleVQA | 3-shot | acc (judge) | 49.38 | **49.48** |
| ChineseSimpleVQA | 3-shot | acc (judge) | 47.27 | **53.00** |
| WorldVQA | 3-shot | acc (judge) | **13.53** | 13.40 |
| BabyVision | 3-shot | acc (judge) | **18.56** | 14.18 |
| PerceptionBench | 3-shot | acc (judge) | 32.57 | **34.03** |
| RealWorldQA | 3-shot | EM | 78.56 | **80.26** |
| MMStar | 3-shot | EM | 68.07 | **70.47** |
| **OCR** | | | | |
| ChartQA (test) | 3-shot | relaxed acc | 87.80 | **88.60** |
| CharXiv (descriptive) | 3-shot | acc (judge) | 84.40 | **86.95** |
| CharXiv (reasoning) | 3-shot | acc (judge) | **65.40** | 61.50 |
| OCRBench v2 (EN) | 3-shot | Overall Score | 52.00 | **52.19** |
| OCRBench v2 (ZH) | 3-shot | Overall Score | 59.84 | **60.96** |
| **Hallucination** | | | | |
| CRPE (exist) | 3-shot | EM | 94.14 | **96.79** |
| CRPE (relation) | 3-shot | EM | 64.84 | **73.86** |
| HallusionBench | 3-shot | avg a/f/qAcc | 57.65 | **60.87** |
| **Grounding** | | | | |
| EmbSpatialBench | 3-shot | EM | 80.00 | **81.48** |
| CountBenchQA | 3-shot | acc | **94.48** | 94.46 |
| RefCOCO | 3-shot | Precision@1 | 72.71 | **91.84** |

> For VL evaluation, MCQ-style benches report option-letter **EM** after extraction. Open-ended benches use MiniMax-M2.7 for MLLM-as-a-**judge**. Other columns are the official suite metrics (not generic accuracy).

## Transformers

Install `transformers==5.12.1`, plus `torch`, `accelerate` and `pillow` for images.

```bash
pip install transformers==5.12.1 torch accelerate pillow
```

```python
import torch
from transformers import AutoModelForCausalLM, AutoProcessor

model_path = "tencent/Youtu-LLM-A7B-Base"

processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)
model = AutoModelForCausalLM.from_pretrained(
    model_path,
    trust_remote_code=True,
    torch_dtype=torch.bfloat16,
    device_map="auto",
)

prompt = "The answer of Q1 is (A). The answer of Q2 is (B). The answer of Q3 is ("
inputs = processor(text=[prompt], return_tensors="pt")
inputs = {k: v.to(model.device) if hasattr(v, "to") else v for k, v in inputs.items()}

outputs = model.generate(**inputs, max_new_tokens=64, do_sample=False)
print(processor.tokenizer.decode(outputs[0], skip_special_tokens=False))
```

For an image, pass `images=[pil_image]` to the processor together with a prompt that contains `<|vision_start|><|image_pad|><|vision_end|>`.

## SGLang

Install `sglang==0.5.17` and start the server with the adapter shipped in this repository (`sglang_adapt/launch.py`), **not** `python -m sglang.launch_server`.

```bash
cd sglang_adapt
MODEL_PATH=tencent/Youtu-LLM-A7B-Base \
  TP_SIZE=4 DP_SIZE=2 EP_SIZE=4 PORT=8000 \
  bash serve_youtu_vl_moe_sglang.sh
```

```bash
curl http://127.0.0.1:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"text":"The answer of Q1 is (A). The answer of Q2 is (B). The answer of Q3 is (","sampling_params":{"temperature":0,"max_new_tokens":16}}'
```

> **Note**
> - Use a Python environment that already has SGLang on `PATH`, or set `SGLANG_ENV`.
> - Weights are BF16; the serve script sets `--dtype bfloat16`.
> - On 8 GPUs, the recommended layout is `TP_SIZE=4`, `DP_SIZE=2`, `EP_SIZE=4`.
> - This is a **base** model: it is recommended to send raw prompts to `POST /generate`, although `chat_template.jinja` is provided for further purpose.

### Overlap scheduler

`DISABLE_OVERLAP_SCHEDULE` defaults to `1` (off). For **text-only** serving you can enable it for higher decode throughput:

```bash
DISABLE_OVERLAP_SCHEDULE=0 MODEL_PATH=tencent/Youtu-LLM-A7B-Base \
  TP_SIZE=4 DP_SIZE=2 EP_SIZE=4 bash serve_youtu_vl_moe_sglang.sh
```

Do not enable it for high-concurrency **image** traffic — vision prefill can hang in `event_loop_overlap`.

## License

See [LICENSE.txt](./LICENSE.txt).
