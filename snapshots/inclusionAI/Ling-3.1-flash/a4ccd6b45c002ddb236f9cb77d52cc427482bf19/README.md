---
license: mit
pipeline_tag: text-generation
---
<p align="center">
    <img src="https://mdn.alipayobjects.com/huamei_qa8qxu/afts/img/A*4QxcQrBlTiAAAAAAQXAAAAgAemJ7AQ/original" width="100"/>
</p>
<p align="center">🤗 <a href="https://huggingface.co/inclusionAI">Hugging Face</a>&nbsp;&nbsp; | &nbsp;&nbsp;🤖 <a href="https://modelscope.cn/organization/inclusionAI">ModelScope</a>&nbsp;&nbsp; | &nbsp;&nbsp;🐙 <a href="https://openrouter.ai/inclusionai/ling-3.1-flash">OpenRouter</a>&nbsp;&nbsp;</p>

## Introduction
We're introducing **Ling-3.1-flash**, an upgraded native hybrid reasoning model designed for complex, real-world tasks. With **560B** total parameters, **25B** active parameters per token, and a **1M-token context window**, Ling-3.1-flash builds upon Ling-3.0-flash with improvements in architecture and performance on real-world tasks.

With stronger real-world capabilities, Ling-3.1-flash shows improvements across a range of real-world tasks, including general-purpose agents, search, office productivity, and software engineering. It demonstrates strong performance on benchmarks such as **GDPVal-AA V2.1, HealthBench Professional, FrontierSWE, and Terminal-Bench 4.0**, covering office tasks, healthcare, software engineering, and terminal-based tool use. The model also shows improvements in specialized domains such as finance and materials science.

<img src="https://intranetproxy.alipay.com/skylark/lark/0/2026/png/23157180/1791987400376-c61f96e8-41a7-4377-80c2-173a01132dc5.png" alt="Ling-3.1-flash performance overview">

## Model Overview
The table and diagram below summarize the model’s specifications and architecture.

| Architecture | Hybrid-linear MoE |
| --- | --- |
| Parameter Scale | Total 560B, Activated 25B |
| Transformer Layers | 63 KDA + 9 Gated MLA (7:1) |
| Number of Dense Layers | 4 |
| Number of Routed Experts | 512 |
| Number of Shared Experts | 1 |
| Number of Activated Experts | 8 |
| Attention Heads | 64 |
| Hidden Size | 4096 |
| Expert Intermediate Size | 1280 |
| Dense Intermediate Size | 10240 |
| Vocabulary Size | 157184 |

<img src="https://intranetproxy.alipay.com/skylark/lark/0/2026/png/23157180/1791966963600-8408d222-3dc1-43c6-87af-f4f905a681db.png" width="600" alt="Ling-3.1-flash model architecture">

## Evaluation
We have conducted a comprehensive evaluation of Ling-3.1-flash across multiple authoritative benchmarks. **Ling-3.1-flash** performs strongly on representative coding/agentic benchmarks including **Terminal-Bench 4.0**, **SWE-bench Pro**, **FrontierSWE**, **GDPVal-AA V2.1**, **Automationbench**, **MCP-Atlas**, and **SkillsBench**, among others. In practice, Ling-3.1-flash delivers a strong user experience across **Claude Code**, **Kilo Code**, **Qwen Code**, **Hermes Agent**, **OpenClaw**, and other frameworks. Beyond agentic tasks, Ling-3.1-flash performs strongly on real-world tasks across **STEM**, **healthcare**, and **finance**. 

We also introduce **LingCode**, a harness built on the open-source coding agent Pi and enhanced to support complex, long-horizon coding tasks that run for hours, involve hundreds of rounds of tool calls, and require repeated context compaction. LingCode delivers significant performance gains on some coding agent tasks, and we are considering open-sourcing it in the future.

<img src="https://intranetproxy.alipay.com/skylark/lark/0/2026/png/202156655/1791988674787-5f49370c-0853-4940-96ea-9f1e4ff20d57.png" alt="Ling-3.1-flash evaluation results">

## Quickstart
### SGLang (Recommended)

The day-0 SGLang image includes Ling-3.1-flash support, MTP (NEXTN) speculative decoding, and Hopper decode optimizations:

```bash
docker pull lmsysorg/sglang:dev-ling-3.1-flash
```

#### Run Inference

**Server** (8 × H200, TP8 + EP8):

```bash
docker run --gpus all --network host --ipc=host --rm \
  lmsysorg/sglang:dev-ling-3.1-flash \
  python3 -m sglang.launch_server \
    --model-path inclusionAI/Ling-3.1-flash \
    --tp 8 --ep 8 \
    --speculative-algorithm NEXTN \
    --host 0.0.0.0 --port 30000
```

On 4 × GB300, use `--tp 4 --ep 4` instead. Hopper decode optimizations (optional, ~10% faster batch-1 decode) can be enabled with `SGLANG_ENABLE_FP8_BLOCK_GEMV=1` and `SGLANG_ENABLE_FUSED_KDA_OUTPUT_QUANT=1`.

**Client**

```bash
curl -s http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "Ling-3.1-flash",
       "messages": [{"role": "user", "content": "What is the capital of France?"}],
       "chat_template_kwargs": {"enable_thinking": true},
       "stream": true,
       "temperature": 1.0,
       "top_k": 20,
       "top_p": 0.95}'
```

Verified recipes for H200, GB300, H800, H100, and B200, plus HiCache (Mooncake L3), reasoning on/off, tool calling, and measured accuracy/speed numbers, are in the [SGLang Ling-3.1-flash cookbook](https://docs.sglang.io/cookbook/autoregressive/InclusionAI/Ling-3.1-flash).

### vLLM
#### Environment Preparation
```bash
pip install uv

uv venv ~/my_ling_env

source ~/my_ling_env/bin/activate

git clone -b vllm https://github.com/vllm-project/vllm.git

cd vllm

VLLM_USE_PRECOMPILED=1 uv pip install --editable . --torch-backend=auto
```

#### Run Inference
**Server**

```bash
vllm serve "$MODEL_PATH" \
    --port "$PORT" \
    --trust-remote-code \
    --served-model-name auto \
    --tensor-parallel-size 8 \
    --gpu-memory-utilization 0.85 \
    --enable-prefix-caching \
    --enable-expert-parallel \
    --mamba-cache-mode align \
    --enable-auto-tool-choice \
    --tool-call-parser ling3 \
    --reasoning-parser ling3 \
    --speculative-config '{"method":"mtp","num_speculative_tokens":3}'
```

**Client**  
It is recommended to use the sampling parameters (`temperature=1.0`, `top_p=0.95`, `top_k=20`) and set `enable_thinking` to `true` for better performance.

```bash
curl -s http://${MASTER_IP}:${PORT}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto", 
       "messages": [{"role": "user", "content": "What is the capital of France?"}],
       "chat_template_kwargs": {"enable_thinking": true},
       "stream": true,
       "temperature": 1.0, 
       "top_k": 20,
       "top_p": 0.95}'
```

<!-- TDS-LINKS:START -->
## Training Content Summary

The public training-content summary identifying **Ling-3.1-flash** is available below. Please refer to the document for its covered model versions, training-content scope, summary version, and update date.

- [Training-content summary (PDF)](https://huggingface.co/inclusionAI/AI-Transparency/resolve/main/Ling-3.1_TDS-Summary.pdf)
- [Training-content documentation index](https://huggingface.co/inclusionAI/AI-Transparency)

This summary concerns training-content disclosure; it does not replace the model’s technical documentation, usage terms, or license.
<!-- TDS-LINKS:END -->
