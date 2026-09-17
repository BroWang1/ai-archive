# Kimi-K2-Thinking Deployment Guide

> [!Note]
> This guide only provides some examples of deployment commands for Kimi-K2-Thinking, which may not be the optimal configuration. Since inference engines are still being updated frequenty,  please continue to follow the guidance from their homepage if you want to achieve better inference performance.

> kimi_k2 reasoning parser and other related features have been merged into vLLM/sglang and will be available in the next release. For now, please use the nightly build Docker image.


## vLLM Deployment

The smallest deployment unit for Kimi-K2-Thinking INT4 weights with 256k seqlen on mainstream H200 platform is a cluster with 8 GPUs with Tensor Parallel (TP).  
Running parameters for this environment are provided below. For other parallelism strategies, please refer to updates of official documents. 


### Tensor Parallelism

Here is a sample launch command with TP=8:

``` bash

vllm serve $MODEL_PATH \
  --served-model-name kimi-k2-thinking \
  --trust-remote-code \
  --tensor-parallel-size 8 \
  --enable-auto-tool-choice \
  --max-num-batched-tokens 32768 \
  --tool-call-parser kimi_k2 \
  --reasoning-parser kimi_k2
```

**Key parameter notes:**
- `--enable-auto-tool-choice`: Required when enabling tool usage.
- `--tool-call-parser kimi_k2`: Required when enabling tool usage.
- `--reasoning-parser kimi_k2`: Required for correctly processing reasoning content. 
- `--max-num-batched-tokens 32768`: Using chunk prefill to reduce peak memory usage.


## SGLang Deployment

Similarly, here are the examples using TP in SGLang for Deployment. 

### Tensor Parallelism

Here is the simple example code to run TP8 on H200 in a sigle node:

``` bash
python -m sglang.launch_server --model-path $MODEL_PATH --tp 8 --trust-remote-code  --tool-call-parser kimi_k2 --reasoning-parser kimi_k2
```

**Key parameter notes:**
- `--tool-call-parser kimi_k2`: Required when enabling tool usage.
- `--reasoning-parser kimi_k2`: Required for correctly processing reasoning content. 


## KTransformers Deployment

### KTransformers+SGLang Inference Deployment

Launch with KTransformers + SGLang for CPU+GPU heterogeneous inference:

``` bash
python -m sglang.launch_server \
  --model path/to/Kimi-K2-Thinking/ \
  --kt-amx-weight-path path/to/Kimi-K2-Instruct-CPU-weight/ \
  --kt-cpuinfer 56 \
  --kt-threadpool-count 2 \
  --kt-num-gpu-experts 200 \
  --kt-amx-method AMXINT4 \
  --trust-remote-code \
  --mem-fraction-static 0.98 \
  --chunked-prefill-size 4096 \
  --max-running-requests 37 \
  --max-total-tokens 37000 \
  --enable-mixed-chunk \
  --tensor-parallel-size 8 \
  --enable-p2p-check \
  --disable-shared-experts-fusion
```

Achieves 577.74 tokens/s Prefill and 45.91 tokens/s Decode (37-way concurrency) on 8× NVIDIA L20 + 2× Intel 6454S.  

More details: https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/Kimi-K2-Thinking.md


### KTransformers+LLaMA-Factory Fine-tuning Deployment

You can use below command to run LoRA SFT with KT+llamafactory. 

``` bash 
# For LoRA SFT
USE_KT=1 llamafactory-cli train examples/train_lora/kimik2_lora_sft_kt.yaml
# For Chat with model after LoRA SFT
llamafactory-cli chat examples/inference/kimik2_lora_sft_kt.yaml
# For API with model after LoRA SFT
llamafactory-cli api examples/inference/kimik2_lora_sft_kt.yaml
```

This achieves end-to-end LoRA SFT Throughput: 46.55 token/s on 2× NVIDIA 4090 + Intel 8488C with 1.97T RAM and 200G swap memory.  

More details refer to https://github.com/kvcache-ai/ktransformers/blob/main/doc/en/SFT_Installation_Guide_KimiK2.md.

## Others

Kimi-K2-Thinking reuses the `DeepSeekV3CausalLM` architecture and convert it's weight into proper shape to save redevelopment effort. To let inference engines distinguish it from DeepSeek-V3 and apply the best optimizations, we set `"model_type": "kimi_k2"` in `config.json`.

If you are using a framework that is not on the recommended list, you can still run the model by manually changing `model_type` to "deepseek_v3" in `config.json` as a temporary workaround. You may need to manually parse tool calls in case no tool call parser is available in your framework.
