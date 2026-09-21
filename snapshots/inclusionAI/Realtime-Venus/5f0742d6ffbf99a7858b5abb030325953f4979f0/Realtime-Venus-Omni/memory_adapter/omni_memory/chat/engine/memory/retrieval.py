# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Pure-question frame retrieval over a question-independent memory snapshot."""

from __future__ import annotations
import math
from collections.abc import Sequence
from typing import Literal
import torch
import torch.nn.functional as functional
from .online_manager import PackedMemorySnapshot


def _pooled_frame_descriptors(
    snapshot: PackedMemorySnapshot, candidate_ids: Sequence[int]
) -> torch.Tensor:
    """Mean-pool Realtime-Venus-Omni visual tokens in bounded chunks without a second model."""
    by_frame = {frame.frame_index: frame for frame in snapshot.frames}
    chunks: list[torch.Tensor] = []
    for start in range(0, len(candidate_ids), 64):
        frame_ids = candidate_ids[start : start + 64]
        embeddings = torch.stack(
            [by_frame[frame_index].embeddings for frame_index in frame_ids]
        )
        chunks.append(
            functional.normalize(
                functional.normalize(embeddings.float(), dim=-1, eps=1e-12).mean(dim=1),
                dim=-1,
                eps=1e-12,
            )
        )
    return torch.cat(chunks, dim=0)


def adaptive_retrieval_k(
    scores: Sequence[float],
    base_k: int = 10,
    low_cv: float = 0.05,
    high_cv: float = 0.3,
    minimum_fraction: float = 0.9,
) -> tuple[int, float]:
    """Reproduce SAVEMem adaptive K, including its 90% retention floor."""
    if not scores:
        raise ValueError("scores must be non-empty")
    if any((not math.isfinite(float(score)) for score in scores)):
        raise ValueError("scores must be finite")
    if isinstance(base_k, bool) or not isinstance(base_k, int) or base_k <= 0:
        raise ValueError("base_k must be a positive integer")
    if not 0.0 <= low_cv < high_cv:
        raise ValueError("CV thresholds must satisfy 0 <= low_cv < high_cv")
    if not 0.0 <= minimum_fraction <= 1.0:
        raise ValueError("minimum_fraction must be in [0,1]")
    score_tensor = torch.tensor(list(scores), dtype=torch.float32)
    standard_deviation = (
        float(score_tensor.std().item()) if score_tensor.numel() > 1 else 0.0
    )
    mean = float(score_tensor.mean().item())
    coefficient = standard_deviation / max(abs(mean), 1e-08)
    candidate_count = len(scores)
    if candidate_count <= base_k:
        return (candidate_count, coefficient)
    if coefficient <= low_cv:
        selected = candidate_count
    elif coefficient >= high_cv:
        selected = base_k
    else:
        ratio = (coefficient - low_cv) / (high_cv - low_cv)
        selected = int(candidate_count - ratio * (candidate_count - base_k))
    minimum_keep = max(base_k, int(minimum_fraction * candidate_count))
    selected = max(selected, min(minimum_keep, candidate_count))
    return (selected, coefficient)


def select_retrieval_k(
    scores: Sequence[float],
    k_mode: Literal["adaptive", "fixed"],
    fixed_k: int,
    base_k: int = 10,
    low_cv: float = 0.05,
    high_cv: float = 0.3,
    minimum_fraction: float = 0.9,
) -> tuple[int, float]:
    """Choose a history-frame count using either adaptive or exact fixed K."""
    if k_mode not in {"adaptive", "fixed"}:
        raise ValueError("k_mode must be adaptive or fixed")
    if isinstance(fixed_k, bool) or not isinstance(fixed_k, int) or fixed_k <= 0:
        raise ValueError("fixed_k must be a positive integer")
    if k_mode == "adaptive":
        return adaptive_retrieval_k(
            scores,
            base_k=base_k,
            low_cv=low_cv,
            high_cv=high_cv,
            minimum_fraction=minimum_fraction,
        )
    if not scores:
        raise ValueError("scores must be non-empty")
    if any((not math.isfinite(float(score)) for score in scores)):
        raise ValueError("scores must be finite")
    score_tensor = torch.tensor(list(scores), dtype=torch.float32)
    deviation = float(score_tensor.std().item()) if len(scores) > 1 else 0.0
    mean = float(score_tensor.mean().item())
    coefficient = deviation / max(abs(mean), 1e-08)
    return (min(fixed_k, len(scores)), coefficient)
