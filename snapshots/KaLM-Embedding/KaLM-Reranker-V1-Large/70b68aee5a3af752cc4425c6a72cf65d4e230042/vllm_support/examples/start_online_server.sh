#!/usr/bin/env bash
set -euo pipefail

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"
export VLLM_PLUGINS="${VLLM_PLUGINS:-kalm_t5gemma2}"
if [[ -d /lib/x86_64-linux-gnu && -d /usr/lib/x86_64-linux-gnu ]]; then
  export LD_LIBRARY_PATH="/lib/x86_64-linux-gnu:/usr/lib/x86_64-linux-gnu${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
fi

exec kalm-vllm-serve \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  --model "${MODEL:-KaLM-Embedding/KaLM-Reranker-V1-Nano}" \
  --query-max-length "${QUERY_MAX_LENGTH:-512}" \
  --document-max-length "${DOCUMENT_MAX_LENGTH:-1024}" \
  --encoder-chunk-size "${ENCODER_CHUNK_SIZE:-4}" \
  --max-model-len "${MAX_MODEL_LEN:-2048}" \
  --batch-size "${BATCH_SIZE:-32}" \
  --dtype "${DTYPE:-bfloat16}" \
  --gpu-memory-utilization "${GPU_MEMORY_UTILIZATION:-0.85}"
