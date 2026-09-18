# KaLM-Reranker-V1-Large vLLM Support

This directory contains the experimental vLLM 0.19.1 adapter for
`KaLM-Embedding/KaLM-Reranker-V1-Large`. It supports offline Python and CLI
reranking plus an optional FastAPI service.

The adapter does not modify or retrain the checkpoint. It reads the original
decoder logits for the single-token answers `yes` and `no` and returns:

```text
margin = yes_logit - no_logit
score = sigmoid(margin) = P(yes)
```

## Tested environment

- Linux and NVIDIA CUDA
- Python 3.12
- vLLM 0.19.1
- Transformers 5.6.2
- PyTorch 2.10.0
- BF16, one GPU

The package intentionally rejects other vLLM versions and
`tensor_parallel_size != 1`. These combinations have not been validated.

## Installation

Create an environment and download the model repository:

```bash
conda create -n kalm-vllm python=3.12 -y
conda activate kalm-vllm

pip install "vllm==0.19.1" "transformers==5.6.2"
pip install "fastapi>=0.136,<0.137" "uvicorn>=0.46,<0.47"

hf download KaLM-Embedding/KaLM-Reranker-V1-Large \
  --local-dir ./KaLM-Reranker-V1-Large
pip install ./KaLM-Reranker-V1-Large/vllm_support --no-deps
export VLLM_PLUGINS=kalm_t5gemma2
```

The model can also be loaded directly by its Hugging Face ID. In that case,
only download the `vllm_support` directory before installing the plugin:

```bash
hf download KaLM-Embedding/KaLM-Reranker-V1-Large \
  --include "vllm_support/**" \
  --local-dir ./KaLM-Reranker-V1-Large
pip install ./KaLM-Reranker-V1-Large/vllm_support --no-deps
```

## Offline Python API

```python
from kalm_t5gemma2_vllm_plugin import KaLMVLLMReranker

query = "What is the capital of China?"
documents = [
    "The capital of China is Beijing.",
    "Gravity attracts bodies toward one another.",
]

pairs = [(query, document) for document in documents]
with KaLMVLLMReranker(
    "KaLM-Embedding/KaLM-Reranker-V1-Large",
    query_max_length=512,
    document_max_length=1024,
    encoder_chunk_size=4,
    max_model_len=2048,
    batch_size=32,
) as reranker:
    print(reranker.predict(pairs))
    print(reranker.predict(pairs, return_margin=True))
    print(reranker.rank(query, documents))
```

Expected BF16 scores are approximately:

```text
[0.99980897, 0.00000493699]
```

`predict()` preserves input order. `rank()` returns score-descending results
with the original document index in `corpus_id`.

## Offline CLI

Run the built-in example:

```bash
kalm-vllm-rerank --return-margin
```

Score JSONL input:

```bash
kalm-vllm-rerank \
  --input-jsonl ./KaLM-Reranker-V1-Large/vllm_support/examples/sample_pairs.jsonl \
  --output-jsonl ./scores.jsonl \
  --return-margin
```

Each input line must contain `query` and `document`. Optional fields are `id`
and `instruction`. `--top-k N` groups rows by exact query text, sorts each
group by score, and keeps its first `N` documents.

## Online service

Start one model instance:

```bash
kalm-vllm-serve \
  --host 0.0.0.0 \
  --port 8000 \
  --model KaLM-Embedding/KaLM-Reranker-V1-Large \
  --encoder-chunk-size 4
```

The portable startup script exposes the same settings through environment
variables:

```bash
CUDA_VISIBLE_DEVICES=0 PORT=8000 \
  ./KaLM-Reranker-V1-Large/vllm_support/examples/start_online_server.sh
```

In a second terminal, check health and send built-in demo requests:

```bash
kalm-vllm-client --health
kalm-vllm-client --endpoint rerank --return-margin
kalm-vllm-client --endpoint score --return-margin
```

For custom input, pass one JSON object with `--json-file`. Use `/rerank` for
one query against multiple documents:

```bash
kalm-vllm-client \
  --endpoint rerank \
  --json-file ./KaLM-Reranker-V1-Large/vllm_support/examples/rerank_request.json \
  --return-margin \
  --top-k 10
```

Use `/score` for a batch of independent query-document pairs:

```bash
kalm-vllm-client \
  --endpoint score \
  --json-file ./KaLM-Reranker-V1-Large/vllm_support/examples/score_request.json \
  --return-margin
```

When `--json-file` is used, `--return-margin` sets
`"return_margin": true` in the outgoing request, and `--top-k` overrides the
JSON value for `/rerank`.

### `POST /rerank`

```json
{
  "query": "What is the capital of China?",
  "documents": [
    "The capital of China is Beijing.",
    "Gravity attracts bodies toward one another."
  ],
  "instruction": "Given a query, retrieve documents that answer the query.",
  "top_k": null,
  "return_margin": true
}
```

Results are returned in descending score order:

```json
{
  "object": "rerank",
  "results": [
    {"index": 0, "score": 0.9998089, "margin": 8.5625},
    {"index": 1, "score": 0.00000493699, "margin": -12.21875}
  ]
}
```

### `POST /score`

```json
{
  "pairs": [
    {
      "id": "doc-1",
      "query": "What is the capital of China?",
      "document": "The capital of China is Beijing."
    }
  ],
  "instruction": null,
  "return_margin": false
}
```

`/score` accepts multiple entries in `pairs`, preserves their input order and
includes an input `id` when provided.

### `GET /health`

Returns service status and the effective model, length, chunking, dtype and
memory settings.

## Configuration

| Setting | Default | Meaning |
| --- | ---: | --- |
| `query_max_length` | `512` | Maximum raw query tokens before prompt insertion |
| `document_max_length` | `1024` | Maximum encoder tokens for `<Document>: ...` |
| `encoder_chunk_size` | `4` | Mean-pooling factor; one of `1,2,4,8,16,32` |
| `max_model_len` | `2048` | vLLM engine context budget |
| `batch_size` | `32` | Pairs passed to each `LLM.classify()` call |
| `dtype` | `bfloat16` | Model compute dtype |
| `gpu_memory_utilization` | `0.85` | vLLM GPU memory fraction |
| `tensor_parallel_size` | `1` | Only supported value in this release |

The query and document limits belong to separate decoder and encoder streams;
they are not a combined cross-encoder token limit. Larger values are
configurable but have not been validated up to the model card's full 128K
limit.

## Limitations

- This is a custom `LLM.classify()` plugin, not vLLM's native HTTP `/score`
  implementation.
- The shim uses vLLM scheduling and pooling interfaces but executes the
  T5Gemma2 semantic forward through Transformers. It is not a complete
  vLLM-native kernel implementation and should not be used to claim native
  vLLM throughput.
- Online serving is a single-process FastAPI wrapper around one model instance.
- `encoder_chunk_size=None`, `null`, or an empty string falls back to `4`; it
  does not disable pooling in this release.

## Troubleshooting

**The plugin is not discovered**

Reinstall the package and ensure the environment variable includes its entry
point name:

```bash
pip install ./KaLM-Reranker-V1-Large/vllm_support --no-deps --force-reinstall
export VLLM_PLUGINS=kalm_t5gemma2
```

**The adapter reports an unsupported vLLM version**

Install exactly `vllm==0.19.1`. Internal model and processor APIs are version
sensitive.

**The tokenizer check fails**

Confirm that the tokenizer belongs to this Large checkpoint. The adapter
requires `yes -> 4443` and `no -> 1904`.

**CUDA runs out of memory**

Reduce `batch_size`, `document_max_length`, `query_max_length`,
`max_model_len`, or `gpu_memory_utilization`.

