---
tags:
  - safety
  - guardrail
  - hallucination-detection
  - streaming
  - glm-5.3-flash
license: other
license_name: glm-5.3-flash
license_link: https://huggingface.co/zai-org/GLM-5.3-Flash/blob/main/LICENSE
base_model: zai-org/GLM-5.3-Flash
---

# GLM-5.3-Flash-singprobe

## Model Description

SingProbe is an **intrinsic streaming guardrail** built on `zai-org/GLM-5.3-Flash`. Rather than running a separate safety model, this lightweight probe reuses the base model's hidden states during generation to score, at every token, **query intent**, **response unsafety**, and **hallucination risk**. It adds less than 0.5% decode-time overhead.

| Base model | Probe parameters | Tapped layers | Outputs |
| --- | ---: | --- | --- |
| `inclusionAI/GLM-5.3-Flash-singprobe` | 8.13M | `[14, 29, 43]` | 8 intents + unsafe + hallucination |

See the [technical report](https://arxiv.org/abs/2608.30703) for methodology and complete results. Training codes are available at [inclusionAI/SingProbe](https://github.com/inclusionAI/SingProbe).

## Evaluation

Higher is better for every metric. Results are averages over the benchmark suites specified below.

| Task | Metric | GLM-5.3-Flash-singprobe | Reference baseline |
| --- | --- | ---: | ---: |
| Query intent classification (6 benchmarks) | F1 | **0.8683** | YuFeng-XGuard-Reason-8B: 0.8714 |
| Response safety classification (8 benchmarks) | F1 | **0.8706** | Qwen3Guard-Gen-8B-strict: 0.8604 |
| Streaming safety (3 benchmarks) | R-AUC / T-AUC | **0.9786 / 0.9232** | Qwen3Guard-Stream-8B-strict: 0.9640 / 0.8893 |
| Hallucination detection (6 benchmarks) | AUC | **0.8143** | DRIFT: 0.8000 |

| Deployment characteristic | Result |
| --- | --- |
| Benign-response false-positive rate | 0.02% average across 5 datasets |
| Decode overhead | < 0.5% |

## Quick Start

SingProbe is supported through the [SGLang integration branch](https://github.com/jinzhen-lin/sglang/tree/token-probe-ling3-flash-main) or [vLLM integration branch](https://github.com/jinzhen-lin/vllm/tree/bailing-v3-token-probe). Load the probe by its Hugging Face ID at server launch:

```bash
python -m sglang.launch_server \
  --model-path zai-org/GLM-5.3-Flash \
  --probe-ckpt inclusionAI/GLM-5.3-Flash-singprobe \
  --port 30000
```

The integrations return one score dictionary per generated token (`label_0`–`label_9`). Use the exact base-model/probe pair: `zai-org/GLM-5.3-Flash` with this checkpoint.

## Citation

```bibtex
@article{singteam2026singprobe,
  title = {SingProbe Technical Report},
  author = {Sing Team},
  journal = {arXiv preprint arXiv:2608.30703},
  year = {2026},
}
```
