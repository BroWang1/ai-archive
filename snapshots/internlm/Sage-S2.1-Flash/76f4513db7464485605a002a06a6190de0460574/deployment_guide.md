# Sage-S2.1-Flash Deployment Guide

The Sage-S2.1-Flash release is a 320B-A18B multimodal MoE model stored in bfloat16 weight format (about 645 GB). The vLLM and SGLang examples below use 8× H200 GPUs. This guide provides basic serving examples for LMDeploy, vLLM and SGLang.

Sage-S2.1-Flash uses the GLM-5.3-Flash architecture, so install and tune vLLM and SGLang following the official GLM-5.3-Flash recipes linked in their sections, replacing `zai-org/GLM-5.3-Flash` with `internlm/Sage-S2.1-Flash`. On top of the official commands, Sage-S2.1-Flash needs the two additions in the next section.

> NOTE: The commands below are reference configurations. Inference frameworks are under active development, so use the latest framework documentation and your local validation results when tuning production deployments.

## Required for Sage-S2.1-Flash

1. **Pass `--trust-remote-code` to every engine.** Code, logs and tool outputs in agentic and machine-learning engineering tasks often contain strings such as `<|user|>`, `<tool_call>` or `</think>`. With the flag, the repository's tokenizer encodes these strings in message content as ordinary text. Without it, the engines silently load the stock tokenizer, which encodes them as control tokens: the model can stop early, and tool calls and reasoning can break. Nothing warns you when the flag is missing.
2. **vLLM: apply the patch in [`vllm_patch/`](./vllm_patch/README.md)** before starting the server (see [vLLM](#vllm)).

On Hopper GPUs (H100, H200), keep the default BF16 KV cache: FP8 KV cache is not supported for this model there.

## LMDeploy

Use [LMDeploy](https://github.com/InternLM/lmdeploy) built from the main branch with `transformers>=5.17,<5.19`, and install [FlashMLA](https://github.com/deepseek-ai/FlashMLA). transformers 5.19 and later rename the layer type `deepseek_sparse_attention` to `indexed_attention`, which LMDeploy does not accept yet.

**Keep `--trust-remote-code`:** the repository ships a custom tokenization strategy (`tokenization_glm5.py`, `processing_glm5.py`) that LMDeploy loads only with this flag. See [Required for Sage-S2.1-Flash](#required-for-sage-s21-flash).

```bash
pip install "transformers>=5.17,<5.19"
lmdeploy serve api_server \
    internlm/Sage-S2.1-Flash \
    --trust-remote-code \
    --backend pytorch \
    --tp 8 \
    --reasoning-parser default \
    --tool-call-parser glm47
```

## vLLM

Install vLLM 0.33.0 following the official [GLM-5.3-Flash vLLM recipe](https://recipes.vllm.ai/zai-org/GLM-5.3-Flash), then apply the patch in [`vllm_patch/`](./vllm_patch/README.md) and pass `--trust-remote-code`.

**Why the patch:** when the model calls several tools and their results come back in a different order than the calls (common with parallel tool calls), the chat template renders the results in call order, but vLLM collects their images in message order. Each image is then silently attached to the wrong result, and the model answers about the wrong image. The patch replaces one file, `vllm/renderers/hf.py`, to put such results in call order before vLLM collects the images. The upstream fix is in progress in [vllm-project/vllm#67108](https://github.com/vllm-project/vllm/pull/67108).

`vllm serve` does not download the patch folder, so fetch it first (this downloads only the patch, not the weights):

```bash
hf download internlm/Sage-S2.1-Flash --include "vllm_patch/*" --local-dir /path/to/Sage-S2.1-Flash
```

Apply the patch to your vLLM installation as described in `/path/to/Sage-S2.1-Flash/vllm_patch/README.md`, then start the server. With `--trust-remote-code`, `vllm serve` downloads the weights and the repository's tokenizer and processor code:

```bash
vllm serve internlm/Sage-S2.1-Flash \
    --trust-remote-code \
    --tensor-parallel-size 8 \
    --enable-auto-tool-choice \
    --tool-call-parser glm47 \
    --reasoning-parser glm47
```

These commands use vLLM's default Python frontend. The official recipe defaults to the Rust frontend (`VLLM_USE_RUST_FRONTEND=1 --tokenizer-mode glm5_next`), which does not accept image or video input yet.

Known issue: in non-streaming responses, a `</think>` or `<tool_call>` that the model writes as ordinary text can end the reasoning early or hide a tool call ([vllm-project/vllm#64326](https://github.com/vllm-project/vllm/issues/64326)). Streaming responses are not affected.

## SGLang

Install SGLang 0.5.20 or later following the official [GLM-5.3-Flash SGLang cookbook](https://cookbook.sglang.io/autoregressive/GLM/GLM-5.3-Flash), then pass `--trust-remote-code` and the repository's chat template explicitly: by default SGLang installs its built-in template for this architecture, which does not go through the repository's tokenizer. `--chat-template` takes a local file:

```bash
hf download internlm/Sage-S2.1-Flash chat_template.jinja --local-dir /path/to/Sage-S2.1-Flash
```

Then pass the downloaded file to `--chat-template`. The server downloads the weights itself.

**Keep `--trust-remote-code`:** the repository ships a custom tokenization strategy (`tokenization_glm5.py`, `processing_glm5.py`) that SGLang loads only with this flag. See [Required for Sage-S2.1-Flash](#required-for-sage-s21-flash).

```bash
python3 -m sglang.launch_server \
    --model-path internlm/Sage-S2.1-Flash \
    --trust-remote-code \
    --chat-template /path/to/Sage-S2.1-Flash/chat_template.jinja \
    --tp-size 8 \
    --reasoning-parser glm45 \
    --tool-call-parser glm47
```
