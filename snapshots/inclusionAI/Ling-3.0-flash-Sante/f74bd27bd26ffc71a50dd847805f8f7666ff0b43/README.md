---
license: mit
pipeline_tag: text-generation
---
<p align="center">
    <img src="https://mdn.alipayobjects.com/huamei_qa8qxu/afts/img/A*4QxcQrBlTiAAAAAAQXAAAAgAemJ7AQ/original" width="100"/>
</p>
<p align="center">🤗 <a href="https://huggingface.co/inclusionAI">Hugging Face</a>&nbsp;&nbsp; | &nbsp;&nbsp;🤖 <a href="https://www.modelscope.cn/models/inclusionAI/Ling-3.0-flash-Sante">ModelScope </a>&nbsp;&nbsp; | &nbsp;&nbsp;🐙 <a href="https://vercel.com/ai-gateway/models/ling-3.0-flash-sante">Vercel </a>&nbsp;&nbsp;</p>

## Introduction
**Ling-3.0-flash-Sante** is our healthcare-specialized model built on [Ling-3.0-flash](https://huggingface.co/inclusionAI/Ling-3.0-flash). Its name comes from the French word _santé_, meaning “health.”

With **124B total parameters** and **5.1B active parameters per token**, Sante is designed for **medical reasoning, healthcare research, deep research, and tool-assisted workflows** while retaining the general capabilities of Ling-3.0-flash. Model weights are available on [Hugging Face](https://huggingface.co/inclusionAI/Ling-3.0-flash-Sante) and [ModelScope](https://www.modelscope.cn/models/inclusionAI/Ling-3.0-flash-Sante).

> **Important:** Ling-3.0-flash-Sante is a research model, not a medical device. Its outputs may be incomplete or incorrect and must not be used as a substitute for professional medical advice, diagnosis, or treatment. High-stakes use requires qualified human review, independent verification, and compliance with applicable privacy, security, and healthcare regulations.
>

## Highlights
+ **Strong healthcare capabilities:** Sante performs well across professional healthcare tasks, complex medical reasoning, medical knowledge, and healthcare safety benchmarks.
+ **Efficient at scale:** Its hybrid-linear MoE architecture combines Kimi Delta Attention (KDA), gated MLA, and sparse MoE layers, activating 5.1B of 124B parameters per token.
+ **Built for long contexts:** Training extends to 256K tokens, supporting long-document analysis, evidence synthesis, and multi-step research.
+ **Beyond medical QA:** Sante is designed for deep research, tool-assisted workflows, and multi-agent collaboration as well as question answering.
+ **Native reasoning and tool use:** Thinking mode is enabled by default, with tool calling supported through compatible serving frameworks.

<img src="https://intranetproxy.alipay.com/skylark/lark/0/2026/png/929/1792589593619-e6d45bb1-34b1-4cbd-aabd-27dc061a3a63.png?x-oss-process=image%2Fcrop%2Cx_71%2Cy_85%2Cw_2718%2Ch_2829" width="2718" title="" crop="0.0201,0.023,0.7936,0.7904" id="iQJhV" class="ne-image">

## Evaluation
We evaluate Ling-3.0-flash-Sante across **professional healthcare tasks, medical knowledge and safety, complex reasoning, deep research, multi-agent collaboration, and tool-assisted agent** benchmarks. The table below summarizes the results shown in the evaluation figure.



<img src="https://intranetproxy.alipay.com/skylark/lark/0/2026/png/139056389/1792679263821-6277a66f-9b7e-4f4c-bdc7-432904587034.png" width="1414" title="" crop="0,0,1,1" id="u9e29e38a" class="ne-image">

**Evaluation settings**

+ Unless otherwise specified, Ling-3.0-flash-Sante is evaluated with `temperature=1.0` and `top_p=0.95` across all benchmarks.
+ The reasoning effort is set to the highest tier for all models in the comparison.
+ AFUMED-Drug emphasizes medication safety and evaluates accuracy on medication contraindications.
+ AFUSAFE-MedSCE measures the overall safety standard of healthcare responses.
+ MedMCQA uses the standard validation set.
+ BrowseComp uses a 256K context window, `temperature=1.0`, `top_p=0.95`, and up to 1,000 turns. The single-agent setting uses a discard-all context-management strategy triggered at 40% context usage. The multi-agent setting uses an in-house harness capable of dispatching up to 64 sub-agents per task.
+ HLE with tools and DeepSearchQA use a 256K context window with `temperature=1.0` and `top_p=0.95`, without a context-management strategy.
+ Tau3-Banking uses the official Tau evaluation set with access restricted to the `terminal_use` tool.

## Quickstart
The official model identifier is `inclusionAI/Ling-3.0-flash-Sante`.

### SGLang
Use the Ling-3.0-compatible SGLang image:

```bash
docker pull lmsysorg/sglang:dev-Ling-3.0-flash
```

The following example launches an OpenAI-compatible server with a 256K context window on four 141GB-class GPUs or a compatible four-GPU Blackwell node:

```bash
docker run --rm --gpus all --ipc=host --shm-size 32g \
  -p 30000:30000 \
  -e HF_TOKEN=<your-hf-token> \
  lmsysorg/sglang:dev-Ling-3.0-flash \
  env SGLANG_ALLOW_OVERWRITE_LONGER_CONTEXT_LEN=1 \
  python3 -m sglang.launch_server \
    --model-path inclusionAI/Ling-3.0-flash-Sante \
    --tp 4 \
    --context-length 262144 \
    --speculative-algorithm NEXTN \
    --mem-fraction-static 0.8 \
    --host 0.0.0.0 \
    --port 30000
```

On 80GB GPUs such as H100 or H800, use `--tp 8` with the same core settings.

Send a request with the OpenAI-compatible API:

```bash
curl -s http://localhost:30000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "inclusionAI/Ling-3.0-flash-Sante",
    "messages": [
      {
        "role": "user",
        "content": "Summarize the evidence in this clinical abstract and identify its primary endpoint."
      }
    ],
    "stream": true,
    "temperature": 0.6,
    "top_k": 20,
    "top_p": 0.95
  }'
```

Thinking is enabled by default through the chat template. To disable it for an individual request, set:

```json
{"chat_template_kwargs": {"enable_thinking": false}}
```

### vLLM
Install a current vLLM build with Ling-3.0 support:

```bash
pip install uv
uv venv ~/my_ling_env
source ~/my_ling_env/bin/activate

git clone https://github.com/vllm-project/vllm.git
cd vllm
VLLM_USE_PRECOMPILED=1 uv pip install --editable . --torch-backend=auto
```

Launch the model server. MTP is recommended for lower latency:

```bash
vllm serve inclusionAI/Ling-3.0-flash-Sante \
  --port "$PORT" \
  --trust-remote-code \
  --served-model-name ling-3.0-flash-sante \
  --tensor-parallel-size 4 \
  --gpu-memory-utilization 0.85 \
  --enable-prefix-caching \
  --mamba-cache-mode align \
  --enable-auto-tool-choice \
  --tool-call-parser ling3 \
  --reasoning-parser ling3 \
  --speculative-config '{"method":"mtp","num_speculative_tokens":3}'
```

Example client request:

```bash
curl -s http://${MASTER_IP}:${PORT}/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "ling-3.0-flash-sante",
    "messages": [
      {
        "role": "user",
        "content": "Compare the inclusion criteria across these two study protocols."
      }
    ],
    "chat_template_kwargs": {"enable_thinking": true},
    "stream": true,
    "temperature": 0.6,
    "top_k": 20,
    "top_p": 0.95
  }'
```

## Intended Use
Ling-3.0-flash-Sante is intended for research and development scenarios such as:

+ Medical and healthcare question answering with human review.
+ Literature search, evidence synthesis, and scientific deep research.
+ Long-document analysis and structured information extraction.
+ Healthcare knowledge-base and retrieval-augmented generation applications.
+ Tool-assisted research and multi-agent healthcare workflows.
+ Evaluation and development of domain-specific AI agents.

## Limitations and Responsible Use
+ The model can produce hallucinated, outdated, incomplete, or unsafe medical information.
+ It must not independently diagnose, prescribe, triage, or make treatment decisions.
+ Outputs for clinical or other high-stakes use require review by qualified professionals and verification against authoritative sources.
+ Users are responsible for protecting personal health information and complying with applicable privacy, data-governance, security, and medical-device requirements.
+ Performance can vary across languages, specialties, populations, institutions, and deployment configurations. Benchmark results do not guarantee real-world clinical performance.
+ Tool access and multi-agent execution introduce additional risks. Use least-privilege credentials, auditable actions, and human approval for consequential operations.

## 