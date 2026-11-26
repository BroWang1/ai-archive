"""Checkpoint loading: Qwen3.5 backbone shards plus the WePM task weights."""

from __future__ import annotations

import json
from pathlib import Path

import mlx.core as mx
import mlx.nn as nn
from mlx.utils import tree_flatten

from mlx_vlm.models.qwen3_5 import Model as Qwen35Model

from .config import build_model_config, read_json

INDEX_NAME = "model.safetensors.index.json"
AUX_NAME = "unimodel_aux.safetensors"
MANIFEST_NAME = "wepm_mlx.json"

# RMSNorm gains of the Qwen3.5 family are stored as (weight - 1); MLX applies the
# gain directly, so the stored delta needs +1. Only the language-side norms use
# this convention, and ``linear_attn.norm`` (Qwen3_5RMSNormGated) does not.
NORM_WEIGHT_SUFFIXES = (
    ".input_layernorm.weight",
    ".post_attention_layernorm.weight",
    "model.norm.weight",
    ".q_norm.weight",
    ".k_norm.weight",
)

TASK_HEAD_KEYS = {
    "unimodel.embedding_head.weight",
    "unimodel.decision_head.output.weight",
    "unimodel.slot_pooler.embedding_slot",
    "unimodel.slot_pooler.decision_slot",
}


def resolve_model_dir(model: str | Path, *, revision: str | None = None) -> Path:
    """Accept a local export directory or a Hugging Face repository id."""
    path = Path(model).expanduser()
    if path.is_dir():
        return path.resolve()
    from huggingface_hub import snapshot_download

    return Path(
        snapshot_download(
            repo_id=str(model),
            revision=revision,
            allow_patterns=["*.json", "*.safetensors", "*.jinja", "*.txt"],
            ignore_patterns=["assets/*", "*.png", "*.jpg", "*.webp", "*.mov", "*.mp4"],
        )
    )


def checkpoint_files(model_dir: Path) -> tuple[dict[str, str], list[str]]:
    """Return ``(backbone_weight_map, shard_names)``."""
    index_path = model_dir / INDEX_NAME
    if not index_path.is_file():
        raise ValueError(
            f"missing {INDEX_NAME} in {model_dir}; download the complete model repository"
        )
    weight_map = read_json(index_path).get("weight_map")
    if not isinstance(weight_map, dict) or not weight_map:
        raise ValueError(f"invalid weight index: {index_path}")
    backbone = {
        key: name for key, name in weight_map.items() if not key.startswith("unimodel.")
    }
    if not backbone:
        raise ValueError(f"weight index lists no backbone tensors: {index_path}")
    return backbone, sorted(set(backbone.values()))


def _safetensors_shapes(path: Path) -> dict[str, tuple[int, ...]]:
    with path.open("rb") as stream:
        header_size = int.from_bytes(stream.read(8), "little")
        header = json.loads(stream.read(header_size))
    return {
        key: tuple(value["shape"]) for key, value in header.items() if key != "__metadata__"
    }


def uses_delta_norm(model_dir: Path, shards: list[str]) -> bool:
    """Detect the ``weight - 1`` RMSNorm convention from the conv1d layout.

    PyTorch checkpoints store depthwise conv1d as ``[out, 1, kernel]``; converted
    MLX checkpoints store ``[out, kernel, 1]``. Every Qwen3.5 export keeps one
    convention across the whole file, so the layout identifies the norm form.
    """
    for name in shards:
        for key, shape in _safetensors_shapes(model_dir / name).items():
            if key.endswith("linear_attn.conv1d.weight"):
                return len(shape) == 3 and shape[-1] != 1
    raise ValueError("checkpoint has no gated-delta conv1d weights")


def map_backbone_key(key: str) -> str:
    if key.startswith("model.language_model.visual"):
        return key.replace("model.language_model.visual", "vision_tower", 1)
    if key.startswith("model.language_model"):
        return key.replace("model.language_model", "language_model.model", 1)
    if key.startswith("model.visual"):
        return key.replace("model.visual", "vision_tower", 1)
    if key.startswith("lm_head"):
        return key.replace("lm_head", "language_model.lm_head", 1)
    return key


def sanitize_backbone(
    weights: dict[str, mx.array],
    *,
    in_channels: int,
    delta_norm: bool,
    tie_word_embeddings: bool,
) -> dict[str, mx.array]:
    """Rename and reshape raw release tensors into the MLX module layout."""
    if tie_word_embeddings:
        weights.pop("lm_head.weight", None)
    sanitized: dict[str, mx.array] = {}
    for original_key, value in weights.items():
        if "mtp." in original_key:
            continue
        key = map_backbone_key(original_key)
        if "conv1d.weight" in key and value.shape[-1] != 1:
            value = value.moveaxis(2, 1)
        # PyTorch Conv3d is NCDHW; MLX convolutions expect NDHWC.
        if key.endswith("patch_embed.proj.weight") and value.ndim == 5:
            if value.shape[-1] != in_channels and value.shape[1] == in_channels:
                value = value.transpose(0, 2, 3, 4, 1)
        if delta_norm and value.ndim == 1 and any(
            key.endswith(suffix) for suffix in NORM_WEIGHT_SUFFIXES
        ):
            value = value + mx.array(1.0, dtype=value.dtype)
        sanitized[key] = value
    return sanitized


def _expected_backbone_keys(model: Qwen35Model) -> set[str]:
    return {key for key, _ in tree_flatten(model.parameters())}


def mlx_manifest(model_dir: Path) -> dict | None:
    """Return the conversion manifest of a published MLX repository, if any."""
    path = model_dir / MANIFEST_NAME
    return read_json(path) if path.is_file() else None


def load_backbone(
    model_dir: Path,
    config: dict,
    *,
    dtype: mx.Dtype = mx.bfloat16,
) -> Qwen35Model:
    """Load the Qwen3.5 vision tower and hybrid language model shard by shard."""
    model = Qwen35Model(build_model_config(config))
    manifest = mlx_manifest(model_dir)
    _, shards = checkpoint_files(model_dir)
    expected = _expected_backbone_keys(model)
    loaded: set[str] = set()

    if manifest is not None:
        # Published MLX repositories already store the MLX module layout: names
        # remapped, conv1d transposed and norm gains applied.
        if manifest.get("norm_weights") != "baked":
            raise ValueError(f"unsupported MLX weight format: {manifest}")
        transform = None
    else:
        delta_norm = uses_delta_norm(model_dir, shards)
        tie = bool(
            config.get(
                "tie_word_embeddings",
                config["text_config"].get("tie_word_embeddings", False),
            )
        )
        in_channels = int(config["vision_config"]["in_channels"])

        def transform(raw: dict[str, mx.array]) -> dict[str, mx.array]:
            return sanitize_backbone(
                raw,
                in_channels=in_channels,
                delta_norm=delta_norm,
                tie_word_embeddings=tie,
            )

    for name in shards:
        raw = dict(mx.load(str(model_dir / name)))
        sanitized = transform(raw) if transform is not None else raw
        if sanitized is not raw:
            del raw
        casted = []
        for key, value in sanitized.items():
            if key not in expected:
                raise ValueError(f"unexpected checkpoint tensor: {key}")
            casted.append((key, value if value.dtype == dtype else value.astype(dtype)))
        model.load_weights(casted, strict=False)
        loaded.update(key for key, _ in casted)
        del sanitized, casted
        mx.clear_cache()

    missing = sorted(expected - loaded)
    if missing:
        raise ValueError(
            f"incomplete backbone load; missing {len(missing)} tensors: {missing[:8]}"
        )
    model.eval()
    return model


def quantize_backbone(
    model: Qwen35Model, *, bits: int, group_size: int = 64
) -> Qwen35Model:
    """Quantize 2-D linear weights in place; embeddings and norms stay in place."""

    def predicate(_path: str, module: nn.Module) -> bool:
        weight = getattr(module, "weight", None)
        if weight is None or weight.ndim != 2:
            return False
        if isinstance(module, nn.Embedding):
            return False
        return weight.shape[-1] % group_size == 0

    nn.quantize(model, group_size=group_size, bits=bits, class_predicate=predicate)
    return model


def task_weight_file(model_dir: Path) -> tuple[Path, str]:
    """Locate the auxiliary weights and report the expected file name."""
    manifest = mlx_manifest(model_dir)
    name = (manifest or {}).get("task_modules") or AUX_NAME
    return model_dir / name, name


def load_task_weights(model_dir: Path, *, dtype: mx.Dtype = mx.bfloat16) -> dict[str, mx.array]:
    """Load the E/J slots, the task heads and the MGVB parameters."""
    path, name = task_weight_file(model_dir)
    if not path.is_file():
        raise ValueError(
            f"missing {name} in {model_dir}; download the complete model repository"
        )
    raw = dict(mx.load(str(path)))
    weights = {key: (value if value.dtype == dtype else value.astype(dtype)) for key, value in raw.items()}
    del raw
    return weights


def split_task_weights(
    weights: dict[str, mx.array],
) -> tuple[dict[str, mx.array], dict[str, mx.array], dict[str, mx.array]]:
    """Split task weights into slots, heads and MGVB parameter dicts."""
    prefix = "unimodel.mgvb."
    unknown = {
        key
        for key in weights
        if not key.startswith(prefix) and key not in TASK_HEAD_KEYS
    }
    if unknown:
        raise ValueError(f"unknown task weights: {sorted(unknown)}")
    slots = {
        role: weights[f"unimodel.slot_pooler.{role}_slot"]
        for role in ("embedding", "decision")
    }
    heads = {
        "embedding": weights["unimodel.embedding_head.weight"],
        "decision": weights["unimodel.decision_head.output.weight"],
    }
    mgvb = {
        key.removeprefix(prefix): value
        for key, value in weights.items()
        if key.startswith(prefix)
    }
    return slots, heads, mgvb


def weight_file_bytes(model_dir: Path) -> int:
    _, shards = checkpoint_files(model_dir)
    total = sum((model_dir / name).stat().st_size for name in shards)
    aux, _ = task_weight_file(model_dir)
    if aux.is_file():
        total += aux.stat().st_size
    return total
