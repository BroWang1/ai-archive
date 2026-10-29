---
tags:
  - safety
  - guardrail
  - hallucination-detection
  - streaming
  - qwen3.8
license: other
license_name: qwen-community-1.0
license_link: https://huggingface.co/Qwen/Qwen3.8-Flash-Next/blob/main/LICENSE
base_model: Qwen/Qwen3.8-Flash-Next
---

# Qwen3.8-Flash-Next-singprobe

## Model Description

SingProbe is an **intrinsic streaming guardrail** built on `Qwen/Qwen3.8-Flash-Next`. Rather than running a separate safety model, this lightweight probe reuses the base model's hidden states during generation to score, at every token, **query intent**, **response unsafety**, and **hallucination risk**. It adds less than 0.5% decode-time overhead.

| Base model | Probe parameters | Tapped layers | Outputs |
| --- | ---: | --- | --- |
| `inclusionAI/Qwen3.8-Flash-Next-singprobe` | 5.18M | `[15, 31, 47]` | 8 intents + unsafe + hallucination |

See the [technical report](https://arxiv.org/abs/2608.30703) for methodology and complete results. Training codes are available at [inclusionAI/SingProbe](https://github.com/inclusionAI/SingProbe).

## Evaluation

Higher is better for every metric. Results are averages over the benchmark suites specified below.

| Task | Metric | Qwen3.8-Flash-Next-singprobe | Reference baseline |
| --- | --- | ---: | ---: |
| Query intent classification (6 benchmarks) | F1 | **0.8728** | YuFeng-XGuard-Reason-8B: 0.8714 |
| Response safety classification (8 benchmarks) | F1 | **0.8714** | Qwen3Guard-Gen-8B-strict: 0.8604 |
| Streaming safety (3 benchmarks) | R-AUC / T-AUC | **0.9882 / 0.9320** | Qwen3Guard-Stream-8B-strict: 0.9640 / 0.8893 |
| Hallucination detection (6 benchmarks) | AUC | **0.8063** | DRIFT: 0.8000 |

| Deployment characteristic | Result |
| --- | --- |
| Benign-response false-positive rate | 0.03% average across 5 datasets |
| Decode overhead | < 0.5% |

## Quick Start

SingProbe is supported through the [SGLang integration branch](https://github.com/jinzhen-lin/sglang/tree/token-probe-ling3-flash-main) or [vLLM integration branch](https://github.com/jinzhen-lin/vllm/tree/bailing-v3-token-probe). Load the probe by its Hugging Face ID at server launch:

```bash
python -m sglang.launch_server \
  --model-path Qwen/Qwen3.8-Flash-Next \
  --probe-ckpt inclusionAI/Qwen3.8-Flash-Next-singprobe \
  --port 30000
```

The integrations return one score dictionary per generated token (`label_0`–`label_9`). Use the exact base-model/probe pair: `Qwen/Qwen3.8-Flash-Next` with this checkpoint.

## Citation

```bibtex
@article{singteam2026singprobe,
  title = {SingProbe Technical Report},
  author = {Sing Team},
  journal = {arXiv preprint arXiv:2608.30703},
  year = {2026},
}
```
