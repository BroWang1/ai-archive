---
license: mit
pipeline_tag: text-generation
---
<p align="center">
    <img src="https://mdn.alipayobjects.com/huamei_qa8qxu/afts/img/A*4QxcQrBlTiAAAAAAQXAAAAgAemJ7AQ/original" width="100"/>
</p>
<p align="center">🤗 <a href="https://huggingface.co/inclusionAI">Hugging Face</a>&nbsp;&nbsp; | &nbsp;&nbsp;🤖 <a href="https://modelscope.cn/organization/inclusionAI">ModelScope </a>&nbsp;&nbsp; | &nbsp;&nbsp;🐙 <a href="https://openrouter.ai/inclusionai/ling-3.0-flash:free">OpenRouter </a>&nbsp;&nbsp;</p>

## Introduction
We're introducing Ling-3.0-flash, our next-generation native hybrid reasoning model. Operating with **124B** total and **5.1B** active parameters (~12.4% and ~8.1% of our previous 1T-class flagship Ring-2.6-1T), Ling-3.0-flash matches or outperforms its predecessor across key benchmarks.

Key highlights of the model are summarized below:

+ **Native Hybrid-Linear Architecture:** Ling-3.0 adopts a native hybrid linear attention architecture from the very start of pretraining (5:1 alternating stacking of Kimi Delta Attention (KDA) and MLA), upgraded with KDA fine-grained diagonal gating and 1/64 sparse MoE. With 124B total parameters and 5.1B activated parameters, it achieves a synergistic leap in long-context efficiency and computational cost.
+ **Remarkable Efficiency & Performance:** Engineered for speed, compute efficiency, and production deployment, Ling-3.0-flash delivers class-defying performance against both larger SOTA competitors and previous-generation flagships. Activating only 5.1B parameters per token, it provides impressive reasoning, instruction following, and long-context capabilities to empower complex agentic workflows in production environments.
+ **Comprehensive Agentic Evolution:** Tailored for real-world productivity workflows, the model incorporates 10,000+ interactive training environments to achieve end-to-end closed-loop execution across Coding, General, and Deep Research Agent tasks. It natively integrates the SGLang HiCache + Mooncake hierarchical caching architecture (featuring physical dual-pools and a cluster-shared L3 cache), eliminating redundant recomputation during long-horizon interactions and reducing Time to First Token (TTFT) by 60% to over 80% in long-input scenarios.

<!-- Benchmark comparison chart across models -->
![](https://intranetproxy.alipay.com/skylark/lark/0/2026/png/23157180/1785831264180-d6ca4404-acef-4424-84db-fbc5a4c6db5f.png)

## Model Overview
The model summary information and architecture diagram are as follows:

| Architecture | Hybrid-linear MoE |
| --- | --- |
| Parameter Scale | Total 124B, Activated 5.1B |
| Transformer Layers | 35 KDA + 7 Gated MLA (5:1) |
| Number of Dense Layers | 2 |
| Number of Routed Experts | 512 |
| Number of Shared Experts | 1 |
| Number of Activated Experts | 8 |
| Attention Heads | 32 |
| Hidden Size | 2560 |
| Expert Intermediate Size | 768 |
| Dense Intermediate Size | 6144 |
| Vocabulary Size | 157184 |
| Context Training Schedule | 8K -> 32K -> 256K |

<!-- Ling-3.0-flash architecture diagram -->
![](https://cdn-uploads.huggingface.co/production/uploads/675fc648a63fff7b5be452f6/Psj43kxXZ5KyYFy9iZV5V.png)

## Evaluation
We have conducted a comprehensive evaluation of Ling-3.0-flash across multiple authoritative benchmarks. **Ling-3.0-flash** performs strongly on representative code/agent benchmarks such as **SWE-Bench Pro, SWE-Bench Multilingual, Tau3-banking-AA**, **MCP-Atlas** and **SkillsBench, etc**. In practice, Ling-3.0-flash delivers a strong user experience across frameworks including **Claude Code**,**Kilo Code**,**Qwen Code**,**Hermes Agent**,and **OpenClaw**, etc. Beyond agentic tasks, Ling-3.0-flash also delivers strong performance across **general knowledge**,**mathematical reasoning**,**instruction following**,and **long-context understanding**.

<!-- Benchmark evaluation results comparison chart -->
![](https://intranetproxy.alipay.com/skylark/lark/0/2026/png/23157180/1785843565924-387dbbd7-90f8-4241-a58d-664cc5e6b486.png)

> + Thinking mode is enabled by default. Unless otherwise specified, the default parameters for Ling-3.0-flash are as follows: `temperature=0.6, top_p=0.95, top_k=20`.
> + SWE-Bench Series: Evaluated using OpenHands as the agent harness with tailored prompts. Decoding uses `temperature=0.6, top_p=0.95, max_new_tokens=32K`, with a 256K context window.
> + Terminal-Bench 2.1: Evaluated under the Artificial Analysis (AA) protocol using the default Terminus 2 harness, a unified 2-hour timeout, the provided JSON parser in preserve-thinking mode, and 3 runs per task (mean). Decoding uses `temperature=0.6, top_p=1.0, max_new_tokens=32K`, with a 256K context window.
> + MiniAppBench: A 500-task coding benchmark evaluating whether models can turn a single user request into complete, usable interactive HTML apps in real-world application-generation scenarios. Evaluated with `temperature=1.0, top_p=1.0, max_tokens=128K`.
> + AntSWEBench: AntSWEBench is an internally used software engineering benchmark that covers mainstream programming languages such as Java, JavaScript, and Python, including various development scenarios like new feature, bug fix, and code refactoring.
> + Tau3-banking-AA: Aligned with the AA leaderboard, utilizing GPT-5.4-mini (medium reasoning) for both the user simulator and the natural-language assertion judge.
> + MCP-Atlas: Evaluated on the 500-task public set using the official v1 harness with a 20-turn limit and Gemini-2.5-Pro as the claim-coverage judger.
> + SkillsBench: Evaluated via kilo-code on 87 tasks (excluding external API-dependent tasks), averaged over 3 runs.
> + GDPval v2-AA: Evaluated on the public 220-task benchmark using the official Stirrup harness, with a 250-turn limit and a 5-hour timeout.
> + Search-agent: For all search‑agent tasks, evaluations are performed using an internal harness. The basic ReAct paradigm is adopted for single-agent evaluation, while a multi-agent setup is employed for BrowseComp. The reported metric is the average pass@1.
>     - WideSearch: Evaluated using the official prompt and the official judge model GPT-4.1 on the corrected version of the dataset.
>     - Draco: Scored based on official rubrics per question, with the final score calculated as the average across all questions using Claude Opus 4.6 as the scoring model.
>     - BrowseComp (Single-Agent): Evaluated using a resume strategy for context management: once the context reaches a 64K-token threshold, the trajectory is summarized, the original history is discarded, and execution is resumed from the summary.
>     - BrowseComp (Multi-Agent): Evaluated using an internal multi-agent search harness based on SearchSwarm/Tongyi DeepResearch, configured with `temperature=0.85, top_p=0.95, max_tokens=8K`, and main/sub-agent context windows of 128K and 64K, respectively.
>


## Quantized Models
We evaluate the quantized models using several datasets. The FP8 quantized model is applied via the blockwise quantization, and INT4 and FP4 models are applied via groupwise quantization with routed experts weights.

|dataset	| BF16	| **FP8**	| INT4	| FP4 |
| -- | -- | -- | -- | -- |
|GPQA-diamond	| 84.97	| 84.00	| 83.65	| 83.68 |
|IFBench |	74.49	| 73.40	| 72.20	| 73.87 |
|SciCode |	41.24	| 40.37	| 39.35	| 38.43 |
|ArcPrize |	68.75	| 67.18	| 67.56	| 68.06 |



## Quickstart
#### Install our SGLang
```bash
pip install uv

uv venv ~/my_ling_env

source ~/my_ling_env/bin/activate

git clone -b ling_v3_support_mxfp4 https://github.com/inclusionAI/sglang.git

cd sglang

pip install --upgrade pip

pip install -e "python"

pip install flashinfer-cubin==0.6.16.post1 --index-url https://flashinfer.ai/whl

pip install flashinfer-python==0.6.16.post1
```

#### Run Inference
Here is an example to run Ling-3.0-flash with 2 Blackwell GPUs, where the master node IP is `${MASTER_IP}` and server port is `${PORT}`:

**Server**

Since the model is trained with MTP, we recommend enabling MTP during inference (i.e., --speculative-algorithm NEXTN) for lower latency.

```bash
export SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1
export SGLANG_JIT_DEEPGEMM_PRECOMPILE=1
export SGLANG_ENABLE_SPEC_V2=1
export FLASHINFER_DISABLE_VERSION_CHECK=1
python -m sglang.launch_server \
    --model-path "$MODEL_PATH" \
    --trust-remote-code \
    --nnodes 1 \
    --dist-init-addr "$MASTER_IP:2345" \
    --port "$PORT" \
    --tp-size 2 \
    --ep-size 1 \
    --max-running-requests 64 \
    --max-mamba-cache-size 320 \
    --chunked-prefill-size 8192 \
    --allow-auto-truncate \
    --context-length 262144 \
    --random-seed 308534008 \
    --attention-backend trtllm_mla \
    --disable-flashinfer-autotune \
    --mem-fraction-static 0.85 \
    --fp8-gemm-backend cutlass \
    --tool-call-parser ling3 \
    --reasoning-parser ling3 \
    --moe-runner-backend flashinfer_mxfp4 \
    --flashinfer-mxfp4-moe-precision default \
    --enable-fp32-lm-head \
    --disable-shared-experts-fusion \
    --speculative-algorithm NEXTN
```

**Client**

We recommend using the sampling parameters `temperature=0.6`, `top_p=0.95`, and `top_k=20`, and enabling `enable_thinking` for better performance.

```bash
curl -s http://${MASTER_IP}:${PORT}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "auto",
       "messages": [{"role": "user", "content": "hello!"}],
       "chat_template_kwargs": {"enable_thinking": true},
       "stream": true,
       "temperature": 0.6, 
       "top_k": 20,
       "top_p": 0.95
     }'
```

You can also refer to the [deployment guide in our cookbook](https://github.com/inclusionAI/ling-cookbook/blob/main/guide/local-deploy/ling-3.0-flash/dgx-spark-llamacpp-ling-3-flash-q4-gguf.ipynb). If you hit any snags while deploying, start a thread in [GitHub Discussions](https://github.com/inclusionAI/ling-cookbook/discussions)—we’d be happy to debug it with you.
