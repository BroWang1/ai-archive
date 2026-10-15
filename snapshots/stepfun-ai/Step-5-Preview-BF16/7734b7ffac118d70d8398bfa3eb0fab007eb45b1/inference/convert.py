"""Convert the original Step-5 checkpoint into validated TP shards.

The converter writes ``OUT/tpN/model-r{rank}.safetensors`` and matching
``config-r{rank}.json`` files, plus one shared ``OUT/tokenizer_files`` directory.
The only supported production layout is ``gqa-provider-shared-tp-v2``.

Example::

    python3 convert.py --checkpoint /path/to/Step-5 \
        --out-dir /path/to/Step-5-TP --tp-size 8 --ep-size 8
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from typing import Any, Callable, TYPE_CHECKING

import torch
from safetensors import safe_open
from safetensors.torch import save_file

if TYPE_CHECKING:
    from model import Step5Config


STEP5_TP_LAYOUT_VERSION = "gqa-provider-shared-tp-v2"


# Each rule callable maps (full_tensor, layer_idx_or_None, tp_size, rank, config) to the
# per-rank tensor. Rules are matched by attempting them in order; the first hit wins.
Rule = Callable[[torch.Tensor, int | None, int, int, Any], torch.Tensor]


def _slice_dim(dim: int) -> Rule:
    """Column or Row: slice tensor along ``dim`` by rank's window, then clone."""

    def apply(t, _layer, tp, rank, _config):
        size = t.shape[dim]
        assert size % tp == 0, f"{size} not divisible by tp={tp}"
        per = size // tp
        return t.narrow(dim, rank * per, per).clone()

    return apply


def _group_window(num_groups: int, tp: int, rank: int) -> tuple[int, int]:
    """Return ``(first_group, count)`` consumed by rank's contiguous Q-head slice.

    For TP below the group count, groups partition across ranks. For TP above it, one group
    is duplicated across ``tp / num_groups`` adjacent ranks. The latter is the production
    TP=8 case: ``_group_window(4, 8, r) == (r // 2, 1)``.
    """
    if not 0 <= rank < tp:
        raise ValueError(f"rank {rank} outside tp_size={tp}")
    if num_groups % tp == 0:
        count = num_groups // tp
        return rank * count, count
    if tp % num_groups == 0:
        replicas = tp // num_groups
        return rank // replicas, 1
    raise ValueError(
        f"tp_size={tp} and group count {num_groups} are incompatible: "
        "one must divide the other"
    )


def _slice_grouped_dim(dim: int, config_attr: str) -> Rule:
    """Slice whole GQA/provider groups, duplicating a group when TP exceeds group count."""

    def apply(t, _layer, tp, rank, config):
        owner = config
        for component in config_attr.split("."):
            owner = getattr(owner, component)
        num_groups = int(owner)
        size = t.shape[dim]
        if size % num_groups:
            raise ValueError(
                f"tensor dim {dim} size {size} is not divisible by {num_groups} groups"
            )
        group_width = size // num_groups
        first, count = _group_window(num_groups, tp, rank)
        return t.narrow(dim, first * group_width, count * group_width).clone()

    return apply


def _replicate(t, _layer, _tp, _rank, _config):
    return t.clone()


# First matching key substring selects the rule. Attention and dense/shared
# experts use TP dimension slices; routed experts use EP slices of the expert
# axis. Routers, normalization parameters and vision weights are replicated.
_SHARD_TABLE: list[tuple[str, Rule]] = [
    # Attention: q_proj/g_proj ColumnParallel (slice head dim, dim 0); o_proj RowParallel
    # (slice head dim on dim 1 of [hidden, num_heads*head_dim] = the in dim). K/V follow
    # the GQA group consumed by the local Q slice. At TP=8 each rank gets one 192-d head,
    # duplicated across adjacent rank pairs rather than replicating all four heads.
    (".self_attn.q_proj.weight", _slice_dim(0)),
    (".self_attn.g_proj.weight", _slice_dim(0)),
    (".self_attn.o_proj.weight", _slice_dim(1)),
    (
        ".self_attn.k_proj.weight",
        _slice_grouped_dim(0, "num_attention_groups"),
    ),
    (
        ".self_attn.v_proj.weight",
        _slice_grouped_dim(0, "num_attention_groups"),
    ),
    # Dense MLP: gate/up ColumnParallel (slice intermediate, dim 0); down RowParallel
    # (slice intermediate on dim 1 of [hidden, intermediate] = the in dim).
    (".mlp.gate_proj.weight", _slice_dim(0)),
    (".mlp.up_proj.weight", _slice_dim(0)),
    (".mlp.down_proj.weight", _slice_dim(1)),
    # MoE routed experts -- EP, not TP-of-inner-dim. Each rank owns n_experts // tp_size
    # contiguous experts (full inner dim per expert). Slicing the experts dim on dim 0. Block
    # scales follow their weight onto the experts dim. ``moe.gate_proj.weight`` matches
    # ``model.layers.N.moe.gate_proj.weight``; the leading ``.`` excludes ``share_expert`` keys.
    (".moe.gate_proj.weight", _slice_dim(0)),
    (".moe.up_proj.weight", _slice_dim(0)),
    (".moe.down_proj.weight", _slice_dim(0)),
    (".moe.gate_proj.weight_scale_inv", _slice_dim(0)),
    (".moe.up_proj.weight_scale_inv", _slice_dim(0)),
    (".moe.down_proj.weight_scale_inv", _slice_dim(0)),
    # ``moe.gate.weight`` (the router) and ``moe.router_bias`` are replicated so every rank
    # selects over all experts and sees the same router scores.
    (".moe.gate.weight", _replicate),
    (".moe.router_bias", _replicate),
    # Shared expert is ordinary TP, not a replicate: gate/up slice their output dim and
    # down slices its input dim. The runtime deliberately leaves the down result local,
    # combines it with the local EP-routed result in FP32, then all-reduces once.
    (".share_expert.gate_proj.weight", _slice_dim(0)),
    (".share_expert.up_proj.weight", _slice_dim(0)),
    (".share_expert.down_proj.weight", _slice_dim(1)),
    # The indexer's Q/W heads are grouped by DSA provider group. Provider groups align with
    # GQA KV groups, so TP=8 gives every rank one group (four Q/W heads), duplicated across
    # the same adjacent rank pair. K/Z are single-head MQA projections and remain replicated.
    # These exact matches must precede the generic sparse-indexer replicate rule.
    (
        ".sparse_indexer_q.weight",
        _slice_grouped_dim(0, "sparse_config.num_provider_groups"),
    ),
    (
        ".sparse_indexer_w.weight",
        _slice_grouped_dim(0, "sparse_config.num_provider_groups"),
    ),
    (".sparse_indexer_", _replicate),
    (".ssmax_s", _replicate),
    # Attention + indexer RMSNorms: each is a small per-head scale on the routed tensor
    # (the residual stream is full, so the norm acts on the full vector). Replicated.
    (".q_norm.weight", _replicate),
    (".k_norm.weight", _replicate),
    (".k_norm.bias", _replicate),
    # Per-layer input/post-attention RMSNorms and the model's final RMSNorm: replicated.
    (".input_layernorm.weight", _replicate),
    (".post_attention_layernorm.weight", _replicate),
    # Embedding, lm_head: replicated (vocab is split at runtime by VocabParallelLinear).
    ("model.embed_tokens.weight", _replicate),
    ("model.norm.weight", _replicate),
    ("lm_head.weight", _replicate),
]


def _shard_for(key: str) -> Rule:
    if key.startswith(("vision_model.", "vit_large_projector.")):
        return _replicate
    for substr, rule in _SHARD_TABLE:
        if substr in key:
            return rule
    raise KeyError(f"no sharding rule for {key}")


def _layer_idx_of(key: str) -> int | None:
    """``model.layers.N.`` -- extract N if present and in-range, else None."""
    marker = "model.layers."
    if key.startswith(marker):
        rest = key[len(marker):]
        layer_str = rest.split(".", 1)[0]
        try:
            return int(layer_str)
        except ValueError:
            return None
    return None


def _order_for_inspection(state: dict[str, torch.Tensor]) -> dict[str, torch.Tensor]:
    """Put embed / lm_head / norm first, then layers, then any stragglers."""
    ordered: dict[str, torch.Tensor] = {}
    for key in ("model.embed_tokens.weight", "model.norm.weight", "lm_head.weight"):
        if key in state:
            ordered[key] = state[key]
    for key in sorted(state.keys()):
        if key.startswith("model.layers."):
            ordered[key] = state[key]
    for key in sorted(state.keys()):
        if key not in ordered:
            ordered[key] = state[key]
    return ordered


def _load_config_for(checkpoint: str, tp_size: int) -> Step5Config:
    from model import config_from_dict

    with open(os.path.join(checkpoint, "config.json")) as handle:
        raw = json.load(handle)
    raw["tp_size"] = tp_size
    raw["expert_parallel_size"] = tp_size
    raw["tp_layout_version"] = STEP5_TP_LAYOUT_VERSION
    return config_from_dict(raw)


def _write_config(
    existing_config_path: str,
    out_path: str,
    tp_size: int,
    expert_parallel_size: int,
) -> None:
    with open(existing_config_path) as handle:
        cfg = json.load(handle)
    cfg["tp_size"] = tp_size
    cfg["expert_parallel_size"] = expert_parallel_size
    cfg["tp_layout_version"] = STEP5_TP_LAYOUT_VERSION
    cfg.pop("use_triton_sliding_attention", None)
    from model import Step5VLConfig, config_from_dict
    config = config_from_dict(cfg)
    cfg = config.to_dict()
    if isinstance(config, Step5VLConfig):
        cfg["architectures"] = ["Step5ForConditionalGeneration"]
        cfg["auto_map"] = {
            "AutoConfig": "model.Step5VLConfig",
            "AutoModelForCausalLM": "model.Step5ForConditionalGeneration",
            "AutoModelForImageTextToText": "model.Step5ForConditionalGeneration",
        }
    else:
        cfg["architectures"] = ["Step5ForCausalLM"]
        cfg["auto_map"] = {
            "AutoConfig": "model.Step5Config",
            "AutoModelForCausalLM": "model.Step5ForCausalLM",
        }
    # ``num_attention_heads`` stays at the full value -- the model derives the per-rank view via
    # ``num_attention_heads // tp_size``. ``tp_layout_version`` deliberately makes shards
    # produced by either the old replicated-KV/provider rule or the v1 replicated-shared
    # rule fail closed instead of loading with plausible but wrong shapes/semantics.
    with open(out_path, "w") as handle:
        json.dump(cfg, handle, indent=2)
        handle.write("\n")


def _write_readme(
    out_path: str,
    tp_size: int,
    expert_parallel_size: int,
    checkpoint: str,
    config: Step5Config,
) -> None:
    local_kv = config.num_kv_groups_per_rank
    local_index_heads = config.sparse_indexer_num_heads_per_rank
    text = f"""# step5 TP-{tp_size} shards

This directory holds one `model-r{{0..{tp_size-1}}}.safetensors` and one
`config-r{{0..{tp_size-1}}}.json` file per rank. The sharding matches the tensor-parallel convention in
`model.py`. Layout marker: `{STEP5_TP_LAYOUT_VERSION}`. Shards without this
marker use an obsolete replicated-KV/provider or replicated-shared layout and must not be
resumed or loaded.

The same {tp_size} ranks form the dense tensor-parallel group and the routed-expert
placement group (`expert_parallel_size={expert_parallel_size}`). Independent TP and EP
process-group axes are not implemented.

| Tensor | Rule | Per-rank shape (tp={tp_size}) |
|--------|------|-------------------------------|
| `self_attn.q_proj.weight` | ColumnParallel, slice dim 0 by `num_heads / tp_size` | `[{64 // tp_size} * 192, 4096]` |
| `self_attn.g_proj.weight` | ColumnParallel, slice dim 0 by `num_heads / tp_size` | `[{64 // tp_size}, 4096]` |
| `self_attn.k_proj.weight` | GQA group slice; duplicate only for ranks consuming the same group | `[{local_kv} * 192, 4096]` |
| `self_attn.v_proj.weight` | GQA group slice; duplicate only for ranks consuming the same group | `[{local_kv} * 192, 4096]` |
| `self_attn.o_proj.weight` | RowParallel, slice dim 1 by `num_heads * head_dim / tp_size` | `[4096, {64 // tp_size} * 192]` |
| `mlp.gate_proj.weight` | ColumnParallel, slice dim 0 by `intermediate / tp_size` | `[{13824 // tp_size}, 4096]` |
| `mlp.up_proj.weight` | ColumnParallel, slice dim 0 by `intermediate / tp_size` | `[{13824 // tp_size}, 4096]` |
| `mlp.down_proj.weight` | RowParallel, slice dim 1 by `intermediate / tp_size` | `[4096, {13824 // tp_size}]` |
| `moe.gate.weight` | replicated (router, every rank selects over all experts) | `[352, 4096]` |
| `moe.gate_proj.weight` | EP, slice dim 0 (experts) by `n_experts / tp_size` | `[{352 // tp_size}, 1536, 4096]` |
| `moe.up_proj.weight` | EP, slice dim 0 (experts) by `n_experts / tp_size` | `[{352 // tp_size}, 1536, 4096]` |
| `moe.down_proj.weight` | EP, slice dim 0 (experts) by `n_experts / tp_size` | `[{352 // tp_size}, 4096, 1536]` |
| `moe.*.weight_scale_inv` | slice the experts dim (dim 0), inner block grid unchanged | `[{352 // tp_size}, ceil(out/128), ceil(in/128)]` |
| `moe.router_bias` | replicated | `[352]` |
| `share_expert.gate/up_proj.weight` | ColumnParallel, slice dim 0 by `share_expert_dim / tp_size` | `[{1536 // tp_size}, 4096]` |
| `share_expert.down_proj.weight` | RowParallel, slice dim 1; reduce deferred until shared+routed FP32 combine | `[4096, {1536 // tp_size}]` |
| `sparse_indexer_q.weight` | provider-group slice (4 heads/group) | `[{local_index_heads} * 256, 4096]` |
| `sparse_indexer_w.weight` | provider-group slice (4 heads/group) | `[{local_index_heads}, 4096]` |
| `sparse_indexer_k/z`, `ssmax_s`, `*_norm.weight`, `k_norm.bias` | replicated | full |
| `model.embed_tokens.weight` | replicated | `[128896, 4096]` |
| `lm_head.weight` | slices the vocab dim at runtime (VocabParallelLinear) | `[128896, 4096]` full per rank |
| `model.norm.weight` | replicated | `[4096]` |

Reference geometry: `num_attention_heads={64}`, `num_attention_groups={4}`, `head_dim={192}`,
`hidden={4096}`, `intermediate={13824}`, `moe_intermediate={1536}`, `vocab={128896}`,
`moe_num_experts={352}`, `topk={8}`. Produced from `{checkpoint}` by
`inference/convert.py`.
"""
    with open(out_path, "w") as handle:
        handle.write(text)


_TOKENIZER_FILES = (
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "chat_template.jinja",
    "vocab.json",
    "merges.txt",
    "added_tokens.json",
    "preprocessor_config.json",
    "processor_config.json",
)


def _build_rank_state(
    checkpoint: str,
    keys: list[str],
    weight_map: dict[str, str],
    tp_size: int,
    rank: int,
    config: Step5Config,
) -> dict[str, torch.Tensor]:
    state: dict[str, torch.Tensor] = {}
    chunks_by_shard: dict[str, list[str]] = {}
    for key in keys:
        chunks_by_shard.setdefault(weight_map[key], []).append(key)
    for shard in sorted(chunks_by_shard):
        print(f"  rank {rank}: shard {shard}", flush=True)
        with safe_open(os.path.join(checkpoint, shard), framework="pt", device="cpu") as handle:
            for key in chunks_by_shard[shard]:
                full = handle.get_tensor(key)
                rule = _shard_for(key)
                state[key] = rule(full, _layer_idx_of(key), tp_size, rank, config)
    return state


def validate_rank_shard(path, config, rank, *, expected=None) -> None:
    """Reject incompatible or incomplete shards before HF can initialize missing weights.

    Inspect headers only. In particular, text-only v2 shards must not load under
    a VL config just because their parallel-layout metadata is still current.
    """
    from model import model_class_for_config

    if expected is None:
        with torch.device("meta"):
            expected = model_class_for_config(config)(config).state_dict()
    text_config = config.get_text_config()
    required_metadata = {
        "tp_size": str(text_config.tp_size),
        "expert_parallel_size": str(getattr(text_config, "expert_parallel_size", text_config.tp_size)),
        "rank": str(rank),
    }
    with safe_open(str(path), framework="pt", device="cpu") as handle:
        metadata = handle.metadata() or {}
        # Tensor layout is unchanged; accept either serialized spelling, but
        # reject conflicting markers rather than silently choosing one.
        layout_fields = [name for name in ("step5_tp_layout", "step4_tp_layout") if name in metadata]
        if not layout_fields:
            raise ValueError(f"{path}: missing step5_tp_layout metadata")
        for field in layout_fields:
            if metadata[field] != STEP5_TP_LAYOUT_VERSION:
                raise ValueError(
                    f"{path}: {field} metadata is {metadata[field]!r}, "
                    f"expected {STEP5_TP_LAYOUT_VERSION!r}"
                )
        for field, value in required_metadata.items():
            if metadata.get(field) != value:
                raise ValueError(f"{path}: {field} metadata is {metadata.get(field)!r}, expected {value!r}")
        keys = set(handle.keys())
        missing, unexpected = set(expected) - keys, keys - set(expected)
        if missing or unexpected:
            raise ValueError(
                f"{path}: shard key mismatch: missing={sorted(missing)[:8]}, "
                f"unexpected={sorted(unexpected)[:8]}; regenerate complete TP shards"
            )
        for key, tensor in expected.items():
            shape = tuple(handle.get_slice(key).get_shape())
            if shape != tuple(tensor.shape):
                raise ValueError(f"{path}: {key} shape {shape} != model {tuple(tensor.shape)}")


def _validate_resume_shards(tp_dir, start_rank, *, config, expected) -> None:
    """Validate retained ranks with the same contract as the runtime loader."""
    for rank in range(start_rank):
        path = os.path.join(tp_dir, f"model-r{rank}.safetensors")
        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"cannot resume at rank {start_rank}: missing completed shard {path}"
            )
        validate_rank_shard(path, config, rank, expected=expected)


def pre_shard(
    checkpoint: str,
    out_dir: str,
    tp_size: int,
    *,
    expert_parallel_size: int | None = None,
    dry_run: bool = False,
    start_rank: int = 0,
    check_only: bool = False,
) -> int:
    """Write ``tp_size`` per-rank safetensors (plus configs and a README) to ``out_dir``.

    ``start_rank`` resumes a partial conversion after checking earlier ranks for
    matching layout, topology and complete parameter keys/shapes.
    """
    expert_parallel_size = (
        tp_size if expert_parallel_size is None else expert_parallel_size
    )
    if tp_size < 1 or expert_parallel_size < 1:
        raise ValueError(
            f"parallel sizes must be positive, got TP={tp_size}, "
            f"EP={expert_parallel_size}"
        )
    if expert_parallel_size != tp_size:
        raise ValueError(
            "independent TP and EP groups are not implemented: "
            f"expert_parallel_size={expert_parallel_size} must equal "
            f"tp_size={tp_size}. The same ranks shard the dense backbone and "
            "the routed experts."
        )
    if not 0 <= start_rank < tp_size:
        raise ValueError(
            f"start_rank must be in [0, {tp_size}), got {start_rank}"
        )
    index_path = os.path.join(checkpoint, "model.safetensors.index.json")
    with open(index_path) as handle:
        weight_map = json.load(handle)["weight_map"]

    config = _load_config_for(checkpoint, tp_size)
    text_config = config.get_text_config()
    keys = sorted(k for k in weight_map if (
        _layer_idx_of(k) is None or _layer_idx_of(k) < text_config.num_hidden_layers
    ))
    from model import model_class_for_config

    with torch.device("meta"):
        expected = model_class_for_config(config)(config).state_dict()
    missing = set(expected) - set(keys)
    unexpected = set(keys) - set(expected)
    if missing or unexpected:
        raise ValueError(
            f"checkpoint key mismatch: missing={sorted(missing)[:8]}, "
            f"unexpected={sorted(unexpected)[:8]}"
        )
    # Check every shape before reading weight data or creating outputs. This also
    # detects vision geometry/configuration drift on the original checkpoint.
    by_shard = {}
    for key in keys:
        by_shard.setdefault(weight_map[key], []).append(key)
    for shard, shard_keys in sorted(by_shard.items()):
        with safe_open(os.path.join(checkpoint, shard), framework="pt", device="cpu") as handle:
            for key in shard_keys:
                shape = handle.get_slice(key).get_shape()
                full = torch.empty(shape, device="meta")
                actual = _shard_for(key)(full, _layer_idx_of(key), tp_size, 0, text_config)
                if actual.shape != expected[key].shape:
                    raise ValueError(f"{key}: shard shape {tuple(actual.shape)} != model {tuple(expected[key].shape)}")
    print(f"validated {len(keys)} tensors; excluded {len(weight_map) - len(keys)} MTP tensors", flush=True)
    if check_only:
        print("PASS (checkpoint keys and TP shapes; no weight data read or files written)")
        return 0

    tp_dir = os.path.join(out_dir, f"tp{tp_size}")
    os.makedirs(tp_dir, exist_ok=True)
    if start_rank:
        _validate_resume_shards(
            tp_dir,
            start_rank,
            config=config,
            expected=expected,
        )
    tokenizer_dst = os.path.join(out_dir, "tokenizer_files")
    if not dry_run and not os.path.isdir(tokenizer_dst):
        os.makedirs(tokenizer_dst, exist_ok=True)
        for name in _TOKENIZER_FILES:
            src = os.path.join(checkpoint, name)
            if os.path.exists(src):
                shutil.copy(src, os.path.join(tokenizer_dst, name))

    sample_keys = [
        "model.embed_tokens.weight",
        "model.norm.weight",
        "lm_head.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.0.self_attn.k_proj.weight",
        "model.layers.0.self_attn.o_proj.weight",
        "model.layers.0.mlp.gate_proj.weight",
        "model.layers.0.mlp.down_proj.weight",
        "model.layers.10.moe.gate_proj.weight",
        "model.layers.10.moe.gate_proj.weight_scale_inv",
        "model.layers.10.moe.down_proj.weight",
        "model.layers.10.moe.down_proj.weight_scale_inv",
        "model.layers.3.self_attn.sparse_indexer_q.weight",
        "model.layers.3.self_attn.sparse_indexer_w.weight",
    ]
    for rank in range(start_rank, tp_size):
        print(f"=== rank {rank} ===", flush=True)
        state = _build_rank_state(checkpoint, keys, weight_map, tp_size, rank, text_config)
        if dry_run:
            print(f"rank {rank}:")
            for key in sample_keys:
                if key in state:
                    print(f"  {key}: {tuple(state[key].shape)} {state[key].dtype}")
        else:
            ordered = _order_for_inspection(state)
            path = os.path.join(tp_dir, f"model-r{rank}.safetensors")
            save_file(
                ordered,
                path,
                metadata={
                    "format": "pt",
                    "format_version": "1",
                    "step5_tp_layout": STEP5_TP_LAYOUT_VERSION,
                    "tp_size": str(tp_size),
                    "expert_parallel_size": str(expert_parallel_size),
                    "rank": str(rank),
                },
            )
            print(f"  wrote {path}  ({os.path.getsize(path) / 1e9:.2f} GB)")

    if dry_run:
        print(f"(dry_run: no files written, would produce tp{tp_size}/ in {out_dir})")
        return 0

    config_path = os.path.join(tp_dir, "config-r0.json")
    if start_rank > 0:
        print(f"resuming from rank {start_rank} (ranks 0..{start_rank - 1} skipped)", flush=True)

    _write_config(
        os.path.join(checkpoint, "config.json"),
        config_path,
        tp_size,
        expert_parallel_size,
    )
    for rank in range(tp_size):
        dst = os.path.join(tp_dir, f"config-r{rank}.json")
        if dst != config_path:
            shutil.copy(config_path, dst)
    _write_readme(
        os.path.join(tp_dir, "README.md"),
        tp_size,
        expert_parallel_size,
        checkpoint,
        text_config,
    )
    print(f"  wrote {len(_TOKENIZER_FILES)} tokenizer files to {tokenizer_dst}")
    print(f"  wrote {tp_size} per-rank configs to {tp_dir}/config-r{{0..{tp_size-1}}}.json")
    print("PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--out-dir", "--out_dir", dest="out_dir", default=None)
    parser.add_argument("--tp-size", "--tp_size", dest="tp_size", type=int, default=8)
    parser.add_argument(
        "--ep-size",
        "--expert-parallel-size",
        dest="ep_size",
        type=int,
        default=8,
        help="Routed-expert sharding degree (default: 8). The current "
        "co-located topology requires EP size to equal TP size.",
    )
    parser.add_argument("--dry-run", "--dry_run", dest="dry_run", action="store_true")
    parser.add_argument(
        "--start-rank",
        "--start_rank",
        dest="start_rank",
        type=int,
        default=0,
        help="Resume from this rank; ranks 0..start_rank-1 are assumed already on disk.",
    )
    parser.add_argument("--check-only", action="store_true", help="Validate all checkpoint keys and TP shapes without reading tensor data or writing shards")
    args = parser.parse_args()
    if not args.check_only and args.out_dir is None:
        parser.error("--out-dir is required unless --check-only is set")
    return pre_shard(
        checkpoint=args.checkpoint,
        out_dir=args.out_dir,
        tp_size=args.tp_size,
        expert_parallel_size=args.ep_size,
        dry_run=args.dry_run,
        start_rank=args.start_rank,
        check_only=args.check_only,
    )


if __name__ == "__main__":
    raise SystemExit(main())
