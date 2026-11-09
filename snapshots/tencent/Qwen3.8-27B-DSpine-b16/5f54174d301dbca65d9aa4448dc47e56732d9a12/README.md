---
license: apache-2.0
base_model:
  - Qwen/Qwen3.8-27B
pipeline_tag: text-generation
inference: false
tags:
  - dspine
  - speculative-decoding
  - draft-model
  - sglang
---

<h1 align="center">DSpine for Qwen3.8-27B</h1>

<p align="center">
  <a href="https://arxiv.org/abs/2609.36173"><img src="https://img.shields.io/badge/arXiv-2609.36173-b31b1b.svg" alt="arXiv"></a>
  <a href="https://dspine-project.github.io"><img src="https://img.shields.io/badge/Project-Page-blue" alt="Project Page"></a>
  <a href="https://github.com/Tencent/DSpine"><img src="https://img.shields.io/badge/GitHub-DSpine-black" alt="GitHub"></a>
</p>

DSpine generates draft tokens in parallel. Each layer passes predicted predecessor features to adjacent positions, carrying causal dependencies through network depth.

This checkpoint is a five-layer draft model for [Qwen3.8-27B](https://huggingface.co/Qwen/Qwen3.8-27B), with block size 16 and an 8,192-token sliding window.

<p align="center">
  <img src="https://dspine-project.github.io/assets/overview.jpg" alt="DSpine architecture" width="90%">
</p>

## Evaluation

- **Runtime:** SGLang 0.5.22, BF16, FlashAttention 3, concurrency 8.
- **Draft blocks:** DSpine 16; official [DFlash2](https://huggingface.co/z-lab/Qwen3.8-27B-DFlash2) 8.
- **DSpine inference:** dynamic verification referencing [DSpark](https://github.com/deepseek-ai/DeepSpec), with [ReplaySSM](https://github.com/Johnny-Liou/ReplaySSM) enabled.
- **General benchmarks:** `xhigh` reasoning, greedy and temperature sampling, at most 4,096 new tokens.
- **Agent benchmarks:** We evaluate [WorkBuddy Bench](https://github.com/Tencent/workbuddy-bench) (Code/Web/Office) using CodeBuddy sandbox trajectories: `low`/`xhigh` reasoning, temperature sampling, 20 conversations per subset, all tool-call prefixes replayed in order, prefix caching, and up to 32,768 new tokens per request.
- **Temperature sampling:** `temperature=1.0`, `top_p=0.95`, `top_k=20`.

## Results

### General Benchmark Acceptance Length

| Task | DFlash2(T=0) | DSpine(T=0) | DFlash2(T=1) | DSpine(T=1) |
| --- | ---: | ---: | ---: | ---: |
| GSM8K | 5.69 | **7.20** | 5.45 | **6.31** |
| MATH-500 | 5.49 | **6.49** | 5.27 | **5.66** |
| HumanEval | 4.87 | **5.71** | 4.34 | **4.71** |
| MBPP | 5.04 | **6.14** | 4.79 | **5.41** |
| MT-Bench | 4.11 | **4.48** | 3.89 | **4.03** |

### Agent Acceptance Length

<div style="overflow-x: auto;">
<table style="display: table; width: auto;">
  <thead>
    <tr><th rowspan="2" style="text-align: left; vertical-align: middle;">Benchmark</th><th colspan="2" align="center" style="text-align: center;">low</th><th colspan="2" align="center" style="text-align: center;">xhigh</th></tr>
    <tr><th align="center" style="text-align: center;">DFlash2</th><th align="center" style="text-align: center;">DSpine</th><th align="center" style="text-align: center;">DFlash2</th><th align="center" style="text-align: center;">DSpine</th></tr>
  </thead>
  <tbody>
    <tr><td style="text-align: left; white-space: nowrap;">WorkBuddy Code</td><td align="center" style="text-align: center; white-space: nowrap;">4.19</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>5.08</strong></td><td align="center" style="text-align: center; white-space: nowrap;">4.06</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>4.92</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">WorkBuddy Web</td><td align="center" style="text-align: center; white-space: nowrap;">3.95</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>4.91</strong></td><td align="center" style="text-align: center; white-space: nowrap;">3.95</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>5.01</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">WorkBuddy Office</td><td align="center" style="text-align: center; white-space: nowrap;">4.24</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>5.63</strong></td><td align="center" style="text-align: center; white-space: nowrap;">4.20</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>5.49</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">SWE-bench Pro</td><td align="center" style="text-align: center; white-space: nowrap;">4.19</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>4.99</strong></td><td align="center" style="text-align: center; white-space: nowrap;">4.00</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>4.77</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">τ²-bench</td><td align="center" style="text-align: center; white-space: nowrap;">4.70</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>5.53</strong></td><td align="center" style="text-align: center; white-space: nowrap;">4.29</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>4.95</strong></td></tr>
  </tbody>
</table>
</div>

### Agent End-to-End Throughput

Throughput is total output tokens divided by end-to-end concurrent replay wall time (tokens/s). Parentheses show speedup over autoregressive decoding (AR).

<div style="overflow-x: auto;">
<table style="display: table; width: auto;">
  <thead>
    <tr><th rowspan="2" style="text-align: left; vertical-align: middle;">Benchmark</th><th colspan="3" align="center" style="text-align: center;">low</th><th colspan="3" align="center" style="text-align: center;">xhigh</th></tr>
    <tr><th align="center" style="text-align: center;">AR</th><th align="center" style="text-align: center;">DFlash2 </th><th align="center" style="text-align: center;">DSpine</th><th align="center" style="text-align: center;">AR</th><th align="center" style="text-align: center;">DFlash2</th><th align="center" style="text-align: center;">DSpine</th></tr>
  </thead>
  <tbody>
    <tr><td style="text-align: left; white-space: nowrap;">WorkBuddy Code</td><td align="center" style="text-align: center; white-space: nowrap;">253.35</td><td align="center" style="text-align: center; white-space: nowrap;">590.27 (2.33×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>686.23 (2.71×)</strong></td><td align="center" style="text-align: center; white-space: nowrap;">193.00</td><td align="center" style="text-align: center; white-space: nowrap;">550.40 (2.85×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>613.55 (3.18×)</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">WorkBuddy Web</td><td align="center" style="text-align: center; white-space: nowrap;">247.40</td><td align="center" style="text-align: center; white-space: nowrap;">639.74 (2.59×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>773.19 (3.13×)</strong></td><td align="center" style="text-align: center; white-space: nowrap;">252.26</td><td align="center" style="text-align: center; white-space: nowrap;">734.04 (2.91×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>840.14 (3.33×)</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">WorkBuddy Office</td><td align="center" style="text-align: center; white-space: nowrap;">210.03</td><td align="center" style="text-align: center; white-space: nowrap;">664.77 (3.17×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>805.53 (3.84×)</strong></td><td align="center" style="text-align: center; white-space: nowrap;">215.05</td><td align="center" style="text-align: center; white-space: nowrap;">662.34 (3.08×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>763.83 (3.55×)</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">SWE-bench Pro</td><td align="center" style="text-align: center; white-space: nowrap;">241.86</td><td align="center" style="text-align: center; white-space: nowrap;">657.71 (2.72×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>713.41 (2.95×)</strong></td><td align="center" style="text-align: center; white-space: nowrap;">248.17</td><td align="center" style="text-align: center; white-space: nowrap;">711.60 (2.87×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>791.30 (3.19×)</strong></td></tr>
    <tr><td style="text-align: left; white-space: nowrap;">τ²-bench</td><td align="center" style="text-align: center; white-space: nowrap;">301.39</td><td align="center" style="text-align: center; white-space: nowrap;">891.37 (2.96×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>964.30 (3.20×)</strong></td><td align="center" style="text-align: center; white-space: nowrap;">340.39</td><td align="center" style="text-align: center; white-space: nowrap;">871.98 (2.56×)</td><td align="center" style="text-align: center; white-space: nowrap;"><strong>978.39 (2.87×)</strong></td></tr>
  </tbody>
</table>
</div>

## Installation

```bash
git clone https://github.com/Tencent/DSpine.git
cd DSpine
pip install -e .
```

## Usage

```bash
sglang serve \
  --model-path Qwen/Qwen3.8-27B \
  --speculative-algorithm DSPINE \
  --speculative-draft-model-path /path/to/Qwen3.8-27B-DSpine-b16 \
  --speculative-num-draft-tokens 16 \
  --dtype bfloat16 \
  --attention-backend fa3 \
  --speculative-draft-attention-backend fa3 \
  --linear-attn-backend triton \
  --enable-linear-replayssm-spec \
  --mamba-ssm-dtype float32 \
  --mamba-radix-cache-strategy extra_buffer \
  --max-mamba-cache-size 64 \
  --mem-fraction-static 0.80 \
  --context-length 131072 \
  --max-running-requests 8 \
  --cuda-graph-max-bs-decode 8 \
  --min-free-slots-delay 1 \
  --sampling-backend flashinfer \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --trust-remote-code
```

## Acknowledgements

We thank [DFlash](https://github.com/z-lab/dflash), [SpecForge](https://github.com/sgl-project/SpecForge), [SGLang](https://github.com/sgl-project/sglang) and [FlashInfer](https://github.com/flashinfer-ai/flashinfer). Dynamic verification references [DSpark](https://arxiv.org/abs/2607.05147).

## Citation

```bibtex
@article{zhang2026dspine,
  title   = {Draft in Parallel, Condition Through Depth: Adjacent Causal Injection for Speculative Decoding},
  author  = {Zhang, Haohui and Chen, Keyu and Sun, Haocheng and Gu, Weibo and Qiao, Ruizhi and Sun, Xing and Jiang, Bo},
  journal = {arXiv preprint arXiv:2609.36173},
  year    = {2026}
}
```

## License

[Apache 2.0](LICENSE)