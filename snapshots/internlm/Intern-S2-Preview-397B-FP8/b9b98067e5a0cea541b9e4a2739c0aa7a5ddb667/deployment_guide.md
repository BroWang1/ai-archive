# Intern-S2-Preview-397B Deployment Guide

We recommend deploying the Intern-S2-Preview-397B model on H100 (x8) or H200 (x8) nodes. The next section provides deployment examples for the configurations listed below:

- Basic serving without MTP
- MTP speculative decoding
- Long-context inference with YaRN RoPE configuration


## LMDeploy (>=0.14.0)

- Basic Serving Without MTP

```bash
# proxy server
lmdeploy serve proxy --server-name ${proxy_server_ip} --server-port ${proxy_server_port} 

# api_server
lmdeploy serve api_server \
    internlm/Intern-S2-Preview-397B \
    --trust-remote-code \
    --backend pytorch \
    --dp 4 \
    --ep 8 \
    --enable-prefix-caching \
    --proxy-url http://${proxy_server_ip}:${proxy_server_port} \
    --reasoning-parser default \
    --tool-call-parser interns2-preview
```

- Serving With MTP

```bash
lmdeploy serve api_server \
    internlm/Intern-S2-Preview-397B \
    --trust-remote-code \
    --backend pytorch \
    --dp 4 \
    --ep 8 \
    --enable-prefix-caching \
    --proxy-url http://${proxy_server_ip}:${proxy_server_port} \
    --reasoning-parser default \
    --tool-call-parser interns2-preview \
    --speculative-algorithm qwen3_5_mtp \
    --speculative-num-draft-tokens 4 \
    --max-batch-size 256
```

- Long-Context Serving

For long-context inference, configure both `--session-len` and YaRN RoPE parameters. The following example uses a 512k context length:

```bash
lmdeploy serve api_server \
    internlm/Intern-S2-Preview-397B \
    --trust-remote-code \
    --backend pytorch \
    --dp 4 \
    --ep 8 \
    --enable-prefix-caching \
    --reasoning-parser default \
    --tool-call-parser interns2-preview \
    --session-len 512000 \
    --max-batch-size 64 \
    --hf-overrides '{"text_config": {"rope_parameters": {"mrope_interleaved": true, "mrope_section": [11, 11, 10], "rope_type": "yarn", "rope_theta": 10000000, "partial_rotary_factor": 0.25, "factor": 4.0, "original_max_position_embeddings": 262144}}}'
```

## vLLM (>=v0.22.1)

- Basic Serving Without MTP

```bash
export VLLM_DEEP_GEMM_WARMUP=skip
export VLLM_USE_DEEP_GEMM=0
export VLLM_FLASHINFER_MOE_BACKEND=latency

vllm serve internlm/Intern-S2-Preview-397B \
  --trust-remote-code \
  --tensor-parallel-size 8 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --reasoning-parser qwen3 \
  --mm-encoder-tp-mode data
```

- Serving With MTP

```bash
export VLLM_DEEP_GEMM_WARMUP=skip
export VLLM_USE_DEEP_GEMM=0
export VLLM_FLASHINFER_MOE_BACKEND=latency

vllm serve internlm/Intern-S2-Preview-397B \
  --trust-remote-code \
  --tensor-parallel-size 8 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  --mm-encoder-tp-mode data \
  --reasoning-parser qwen3 \
  --speculative-config '{"method":"mtp","num_speculative_tokens":3}'
```

- Long-Context Serving

```bash
VLLM_ALLOW_LONG_MAX_MODEL_LEN=1 vllm serve internlm/Intern-S2-Preview-397B \
  --tensor-parallel-size 8 \
  --max-model-len 1010000 \
  --reasoning-parser qwen3 \
  --hf-overrides '{"text_config": {"rope_parameters": {"mrope_interleaved": true, "mrope_section": [11, 11, 10], "rope_type": "yarn", "rope_theta": 10000000, "partial_rotary_factor": 0.25, "factor": 4.0, "original_max_position_embeddings": 262144}}}'
```

## SGLang (>=v0.5.13)

- Basic Serving Without MTP

```bash
python3 -m sglang.launch_server \
    --model-path internlm/Intern-S2-Preview-397B \
    --trust-remote-code \
    --tp-size 8 \
    --mem-fraction-static 0.8 \
    --enable-flashinfer-allreduce-fusion \
    --reasoning-parser qwen3 \
    --tool-call-parser qwen3_coder
```

- Serving With MTP

```bash
SGLANG_ENABLE_SPEC_V2=1 \
python3 -m sglang.launch_server \
  --model-path internLM/Intern-S2-Preview-397B \
  --trust-remote-code \
  --tp-size 8 \
  --reasoning-parser qwen3 \
  --tool-call-parser qwen3_coder \
  --mem-fraction-static 0.8 \
  --mamba-scheduler-strategy extra_buffer \
  --enable-flashinfer-allreduce-fusion \
  --speculative-algo 'NEXTN' \
  --speculative-eagle-topk 1 \
  --speculative-num-steps 3 \
  --speculative-num-draft-tokens 4
```
