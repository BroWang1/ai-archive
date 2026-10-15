# Step-5 minimal inference

> 中文版本：[README.zh.md](README.zh.md)

This directory contains the standalone Step-5 inference path. Full-model text
and image-text generation have been validated with FP8 on **one 8 x H200 node**
at **TP=EP=8**, and BF16 on **two 8 x H200 nodes** at **TP=EP=16**.
The vision encoder uses PyTorch and BF16 weights. All commands below run from
this directory; the inference files can be used independently.

The default sliding-attention path is PyTorch SDPA. QKNorm/RoPE, DSA sparse
attention, block-scaled FP8 expert GEMM, and the critical MoE primitives use
Triton/CUDA; model orchestration and NCCL collectives remain PyTorch.

The same ranks provide tensor parallelism for the dense backbone and expert
parallelism for the 352 routed experts. TP=EP=8 places 44 experts on each rank;
TP=EP=16 places 22. TP and EP share a process group; there is no independent
`TP × EP` process grid.

## Contents

| File | What it is |
|------|------------|
| `convert.py` | Converts an original Step-5 checkpoint into per-rank TP shards: `tpN/model-r{rank}.safetensors` + matching `config-r{rank}.json`, plus a shared `tokenizer_files/`. |
| `generate.py` | Greedy text or image-text inference. Loads one shard per `torchrun` rank; accepts a text `--prompt`, or exact prompt IDs with optional prepared `--image-inputs`. |
| `model.py` | Text/VL configuration, decoder layers, TP/EP execution, and image-feature injection into packed prefill. Imports compute kernels from `kernel.py`. |
| `vision_encoder.py` | PyTorch perception encoder with 2D RoPE, absolute positions and convolutional downsamplers. |
| `kernel.py` | The Triton/CUDA compute kernels: the sparse-attention (DSA) indexer + decode/prefill, block-scaled FP8 expert GEMM, the MoE primitives, and fused QKNorm/RoPE. |
| `test_vision.py` | Configuration, checkpoint-loading and multimodal inference regressions. |
| `requirements.txt` | Compatible runtime ranges: torch `>=2.10,<2.14`, transformers `>=4.57.6,<6`, safetensors `>=0.7,<1`, and triton `>=3.6,<3.8`. |

Typical flow: `convert.py` (once, to shard a checkpoint) → `generate.py` (to run it).
`generate.py` loads the model implemented by `model.py`, `kernel.py` and `vision_encoder.py`.

Expert storage follows the source configuration: absent or empty
`quantization_config` selects BF16; `quant_method="fp8"` selects FP8 with BF16
exclusions from `modules_to_not_convert`. Conversion preserves weight dtypes.

## Install

Use a CUDA-enabled PyTorch build matching the host driver. FP8 checkpoint inference
at TP=8 requires eight visible GPUs with FP8 E4M3 support. The validated vision runtime
uses PyTorch 2.13.0+cu129, Triton 3.7.1, Transformers 5.15.0, and Safetensors 0.8.0.
The compatible version ranges are listed in `requirements.txt`.

Create a virtual environment and install the dependencies:

```bash
python3 -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If the host does not already provide a compatible CUDA-enabled PyTorch, install
it from the CUDA wheel index matching the driver before installing the remaining
requirements:

```bash
python -m pip install \
  --index-url "<matching-pytorch-cuda-wheel-index>" \
  "torch>=2.10,<2.14"
python -m pip install -r requirements.txt
```

The release loads the fast tokenizer serialized in local `tokenizer.json` directly.
Automatic tokenizer class selection in Transformers 5.15 is incompatible with these
Step-5 assets and can collapse long prompts. Direct loading preserves the
byte-level BPE input IDs and output decoding validated with Transformers 4.57.6.

## Long-output stability

Generation uses the following long-output execution contract:

- TP partial results are added in rank order with FP32 accumulation.
- Sliding-window token-by-token decode uses PyTorch's default SDPA backend
  selection. This keeps the production path on the backend supported by the
  installed PyTorch/CUDA runtime instead of forcing the slower math backend.
- A request that emits EOS is removed from later decode steps and its cache row
  is compacted.

The checks cover row-position stability inside one active batch. They do not
promise bitwise-identical output across different batch sizes, schedulers, GPU
models, or software versions.

## Checkpoints and launch modes

Run all commands from this directory. Choose the FP8 or BF16 section for your
source checkpoint and use a separate output directory for each format.
Conversion partitions weights and preserves their dtype; it does not quantize
a BF16 checkpoint into FP8.

The source model directory supplies the authoritative `config.json`.
`convert.py` writes `tpN/model-r{rank}.safetensors` and matching
`config-r{rank}.json` files, with `gqa-provider-shared-tp-v2` and
`expert_parallel_size=N`, plus shared tokenizer assets in `tokenizer_files/`.
`generate.py` reads these configs from `--tp-dir` and discovers the copied
tokenizer automatically. The inference directory does not supply a model config.
Use the weights and configs from the same conversion. If a config omits
`expert_parallel_size`, the runtime uses `tp_size`.

<a id="fp8"></a>

## FP8: one node with 8 GPUs

The FP8 path has been validated on **8 x H200**, with **TP=EP=8** and 44 routed
experts per rank. The source config must declare `quant_method="fp8"`;
excluded expert layers and the vision tower retain their BF16 weights.

Set the source and output directories:

```bash
export STEP5_FP8_CHECKPOINT="<fp8-checkpoint-directory>"
export STEP5_FP8_OUT="<fp8-shard-output-directory>"
```

Check checkpoint keys and shard shapes, then convert once to a fresh output
directory. `--check-only` reads headers without loading weights or writing shards:

```bash
python3 convert.py \
  --checkpoint "$STEP5_FP8_CHECKPOINT" \
  --tp-size 8 --ep-size 8 --check-only

python3 convert.py \
  --checkpoint "$STEP5_FP8_CHECKPOINT" \
  --out-dir "$STEP5_FP8_OUT" \
  --tp-size 8 --ep-size 8
```

Launch text generation on the node with eight visible GPUs:

```bash
torchrun --standalone --nproc-per-node=8 generate.py \
  --tp-dir "$STEP5_FP8_OUT/tp8" --ep-size 8 \
  --prompt "请介绍一下张量并行。" \
  --max-new-tokens 128
```

For image-text generation, prepare the matching checkpoint's prompt IDs and
image tensors according to [Vision inputs](#vision-inputs), then run:

```bash
torchrun --standalone --nproc-per-node=8 generate.py \
  --tp-dir "$STEP5_FP8_OUT/tp8" --ep-size 8 \
  --prompt-json prompt-ids.json --image-inputs image-inputs.safetensors \
  --max-new-tokens 128
```

<a id="bf16"></a>

## BF16: 16 GPUs across two nodes

The full 92-layer BF16 VL model needs approximately **144.41 GiB per rank** at
TP/EP=8 for parameters alone, exceeding the validated H200 node's 140.40 GiB per
GPU. At **TP=EP=16**, loaded parameters occupy **74.93 GiB per rank**, with 22 routed
experts per rank. These figures include replicated vision weights and a sharded
output head, exclude MTP, and leave KV caches, RoPE, activations and communication
as additional memory requirements.

The complete BF16 decoder, vision encoder and projector passed two-node text
and single-image greedy generation on **16 H200 GPUs**. All ranks produced
identical tokens and reached EOS, with finite logits throughout. The measured
peak PyTorch allocation was **76.37 GiB per GPU** for batch size 1 and a
943-token image prompt, including 898 visual tokens. This excludes allocations
outside PyTorch, such as NCCL and the CUDA context. Communication used **NCCL TCP
Socket**; RDMA, long-context workloads and throughput have not been validated.

The full-model run streamed and sliced the original weights using the converter's
TP rules and executed the released model forward path. The complete BF16
`convert.py` → `generate.py --tp-dir` file-based workflow below has not been
separately run end to end; checkpoint key/shape checks and small-model BF16
conversion/loading/generation tests have passed.

Use two nodes with eight visible H200 GPUs each. Both nodes need the same code
and compatible runtime, NCCL connectivity, and access to the same converted
weights and tokenizer files at the configured paths. Image inputs must also be
available with identical contents on both nodes.

Set these paths on both nodes. The source checkpoint must use BF16 weights and
have no quantization config, or an empty one:

```bash
export STEP5_BF16_CHECKPOINT="<bf16-checkpoint-directory>"
export STEP5_BF16_OUT="<bf16-shard-output-directory>"
```

On **one node only**, check the source and convert once into 16 complete shards.
Make the resulting `tp16/` and `tokenizer_files/` directories accessible to both
nodes before launching:

```bash
python3 convert.py \
  --checkpoint "$STEP5_BF16_CHECKPOINT" \
  --tp-size 16 --ep-size 16 --check-only

python3 convert.py \
  --checkpoint "$STEP5_BF16_CHECKPOINT" \
  --out-dir "$STEP5_BF16_OUT" \
  --tp-size 16 --ep-size 16
```

On **both nodes**, set the same reachable node-0 address and free rendezvous port:

```bash
export MASTER_ADDR="<node-0-reachable-IP-or-hostname>"
export MASTER_PORT=29500
```

On **node 0**:

```bash
export NODE_RANK=0
```

On **node 1**:

```bash
export NODE_RANK=1
```

Run the following command on **both nodes**, with their respective `NODE_RANK`,
for the same launch. It starts eight workers per node and 16 workers in total:

```bash
torchrun --nnodes=2 --nproc-per-node=8 \
  --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" --master-port="$MASTER_PORT" \
  generate.py \
  --tp-dir "$STEP5_BF16_OUT/tp16" --ep-size 16 \
  --prompt "请介绍一下张量并行。" \
  --max-new-tokens 128
```

Alternatively, for image-text generation, prepare the inputs according to
[Vision inputs](#vision-inputs) and run this command on **both nodes**:

```bash
torchrun --nnodes=2 --nproc-per-node=8 \
  --node-rank="$NODE_RANK" \
  --master-addr="$MASTER_ADDR" --master-port="$MASTER_PORT" \
  generate.py \
  --tp-dir "$STEP5_BF16_OUT/tp16" --ep-size 16 \
  --prompt-json prompt-ids.json --image-inputs image-inputs.safetensors \
  --max-new-tokens 128
```

The launcher sets `WORLD_SIZE=2 x 8=16`; shard configs and `--ep-size` must both
use 16. `--standalone` is only used by the single-node FP8 example.

For exact text token IDs in either launch mode, replace `--prompt` and its value
with `--prompt-json <prompt-json-file>`. The file accepts a JSON list or
`{"prompt_ids": [...]}`. `--prompt-json-batch` accepts a batch of requests.

## Limitations

- Full-model generation has been validated with FP8 on one 8 x H200 node and
  BF16 on two 8 x H200 nodes using streamed weights. The full BF16 file-based
  conversion/loading workflow remains unvalidated end to end.
- `--ep-size` defaults to 8 and currently must equal TP/world size; independent
  TP and EP process groups such as `TP=4, EP=2` are not implemented.
  `generate.py` reads TP from the shard config (and checks it against
  `WORLD_SIZE`); it intentionally has no separate `--tp-size` switch.
- Sliding attention uses PyTorch SDPA.
- Generation is greedy. Continuous dynamic batching, paged KV cache, prefix
  caching and CUDA graphs are not provided. BF16 cross-node validation covers
  short text and single-image requests over NCCL TCP Socket.
- MTP layers are not loaded, so speculative decoding is unavailable.
- The checkpoint's factory FP8/BF16 expert layout is consumed directly; the
  converter and generated TP shards are checkpoint-layout specific.

## Vision checkpoints (`step5_vl`)

`Step5ForConditionalGeneration` uses `Step5VLConfig` with top-level
`model_type=step5_vl`, `text_config.model_type=step5`, and
`vision_config.model_type=perception_encoder`. Text-only checkpoints use
`Step5Config` and `Step5ForCausalLM`.

The Step-5 perception encoder uses PyTorch operations, non-causal SDPA,
2D RoPE, absolute position embeddings, LayerScale and two convolutional
downsamplers. Projected image features enter the packed text decoder during
prefill; text decoding uses the DSA cache and co-located TP/EP execution.

The validated VL checkpoint has the following geometry:

| Component | Configuration |
| --- | --- |
| Text decoder | 92 layers, hidden size 4096; 3 MTP layers excluded from ordinary generation |
| Vision Transformer | 47 layers, width 1536, 16 attention heads, MLP size 8960 |
| Patch embedding | RGB, 14×14 kernel and stride 14 |
| Activation and normalization | QuickGELU, pre-LN, no post-LN, LayerScale 0.1 |
| Position encoding | Absolute positions and 2D RoPE; no CLS token |
| Downsamplers | Two 3×3 convolutions, stride 2, padding 1; 1536→3072→6144 |
| Projector | 6144→4096, no bias |
| Image placeholder | Token ID 128001 |
| Vision weights | 667 BF16 tensors; approximately 3.96 GB per TP rank |

Checkpoint keys are `model.*`, `lm_head.*`, `vision_model.*` and
`vit_large_projector.*`. Vision and projector tensors are replicated on each
TP rank. The checkpoint index determines the files and dtypes to load.
The converter excludes MTP tensors at indices `>= text_config.num_hidden_layers`.

Use the [FP8](#fp8) or [BF16](#bf16) checkpoint-check and conversion
commands above for VL checkpoints as well. Complete shards include the nested
config, `Step5ForConditionalGeneration` identity, text, vision and projector weights.

Both resumed conversion and generation verify each shard's complete key set,
shapes and TP/EP/rank metadata before reading weight data. Generation also rejects
any missing or unexpected keys reported by the Hugging Face loader; incomplete
vision weights cannot fall back to random initialization.

<a id="vision-inputs"></a>

### Vision inputs

The model API accepts preprocessed tensors:

| Argument | Meaning |
| --- | --- |
| `pixel_values` | Overview images, `[images, 3, H, W]`; additional leading batch dimensions are flattened. |
| `patch_pixel_values` | Optional crops in image order, with the same layout. |
| `num_patches` | One nonnegative crop count per overview image. Defaults to zero crops. |
| `image_embeds` | Alternative already projected features, `[..., text_hidden_size]`; excludes all pixel/crop arguments. |

The released geometry produces 169 tokens for each 728×728 overview and 81
for each 504×504 crop. Each image contributes **its crops first, then its
overview**. Concatenate images in prompt order across packed requests. The
number of `image_token_id` placeholders must equal the total feature-token
count; `<im_start>` / `<im_end>` remain ordinary text embeddings. Image
encoding runs only during prefill. Decode uses the existing cache.

Image resizing, normalization, crop selection and prompt construction must come
from the matching checkpoint processor. This standalone path consumes those
prepared results; it does not define a new PIL/JPEG processing policy. Save a
prepared batch with `safetensors.torch.save_file`, for example:

```python
import torch
from safetensors.torch import save_file

save_file({
    "pixel_values": pixel_values.contiguous(),
    "patch_pixel_values": patch_pixel_values.contiguous(),
    "num_patches": torch.tensor(num_patches, dtype=torch.int64),
}, "image-inputs.safetensors")
```

Use the image-text launch command in the [FP8](#fp8) or [BF16](#bf16)
section with `prompt-ids.json` (including image placeholders) and
`image-inputs.safetensors`.

`--prompt-json-batch` supports a mixture of text and image requests. Every rank
reads the same prepared image file. The Python API accepts these arguments in
`Step5ForConditionalGeneration.forward` and `generate_greedy` as well.

Run the multimodal integration regression with the optional test dependency:

```bash
python -m pip install pytest
python -m pytest -q test_vision.py
```

`vision_select_layer=-1` and language-frequency 2D RoPE are supported.
Other layer-selection or frequency modes fail explicitly.

### Validation results

The following results were obtained on H200 with PyTorch 2.13.0+cu129,
Triton 3.7.1 and Transformers 5.15.0:

| Check | Result |
| --- | --- |
| Vision integration, checkpoint identity and BF16 loading tests | 20 passed |
| Configuration, generation, serving, evaluation and cache regressions | 203 passed, 93 subtests passed |
| GPU operator gates | All 10 passed |
| Batch and NCCL TP stability | Passed |
| FP8 checkpoint schema, TP8 | 2653 runtime tensors validated; 51 MTP tensors excluded |
| BF16 checkpoint schema, TP8 and TP16 | 2398 runtime tensors validated; 51 MTP tensors excluded |
| BF16 small-model generation | TP1/TP8 pixel and projected-embedding inputs produced identical output token IDs |
| Full vision numerical validation | Overview and crop outputs matched exactly; maximum absolute error 0 |
| TP8 mixed-precision fixture | Pixel and projected-embedding inputs produced identical output token IDs |
| HF file-shard loading, complete real rank 0 | 85.4 GB shard loaded; real-image features `[898,4096]` matched exactly |
| Full real FP8 checkpoint TP8 image generation, streamed weights | Correctly described a white Samoyed on grass; 27 generated tokens, normal EOS, identical output on all ranks |
| Full real BF16 checkpoint, two-node TP16/EP16, streamed weights | Text and single-image generation passed; finite logits, normal EOS and identical tokens on all 16 ranks; 74.93 GiB parameters/rank, 76.37 GiB peak PyTorch allocation/GPU |

The image case used one 728×728 overview and nine 504×504 crops, totaling
898 visual tokens. Image encoding runs in PyTorch with fused GPU attention.
These results cover functional and numerical correctness for the tested inputs;
they do not constitute a multimodal benchmark or OCR/video quality evaluation.
