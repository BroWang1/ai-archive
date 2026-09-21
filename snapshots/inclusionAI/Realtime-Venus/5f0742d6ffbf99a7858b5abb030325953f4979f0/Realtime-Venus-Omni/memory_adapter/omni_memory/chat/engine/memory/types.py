# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Tensor contracts shared by compression, retrieval, and model adapters."""

from __future__ import annotations
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal
import torch


@dataclass(frozen=True)
class FrameTokenStore:
    """Immutable references to Resampler outputs and their source timeline."""

    embeddings: torch.Tensor
    timestamps: torch.Tensor
    source_frame_indices: torch.Tensor

    def __post_init__(self) -> None:
        if self.embeddings.ndim != 3:
            raise ValueError("embeddings must have shape [F,64,D]")
        (frame_count, token_count, hidden_size) = self.embeddings.shape
        if frame_count <= 0:
            raise ValueError("embeddings frame dimension F must be positive")
        if token_count != 64:
            raise ValueError(
                f"expected 64 Resampler tokens per frame, got {token_count}"
            )
        if hidden_size <= 0:
            raise ValueError("embedding hidden size must be positive")
        if self.timestamps.ndim != 1 or self.timestamps.shape[0] != frame_count:
            raise ValueError("timestamps must have shape [F]")
        if (
            self.source_frame_indices.ndim != 1
            or self.source_frame_indices.shape[0] != frame_count
        ):
            raise ValueError("source_frame_indices must have shape [F]")
        if not torch.is_floating_point(self.embeddings):
            raise ValueError("embeddings must be floating point")
        if not torch.is_floating_point(self.timestamps):
            raise ValueError("timestamps must be floating point")
        if self.source_frame_indices.dtype == torch.bool or torch.is_floating_point(
            self.source_frame_indices
        ):
            raise ValueError("source_frame_indices must use an integer dtype")
        if not torch.isfinite(self.embeddings).all():
            raise ValueError("embeddings must be finite")
        if not torch.isfinite(self.timestamps).all():
            raise ValueError("timestamps must be finite")
        if frame_count > 1 and torch.any(torch.diff(self.timestamps) < 0):
            raise ValueError("timestamps must be nondecreasing")
        if frame_count > 1 and torch.any(torch.diff(self.source_frame_indices) <= 0):
            raise ValueError("source_frame_indices must be strictly increasing")

    @property
    def frame_count(self) -> int:
        return self.embeddings.shape[0]

    @property
    def tokens_per_frame(self) -> int:
        return self.embeddings.shape[1]

    @property
    def hidden_size(self) -> int:
        return self.embeddings.shape[2]


MemoryTier = Literal["short", "mid", "long", "dropped", "unseen"]


@dataclass(frozen=True)
class RetrievalResult:
    """Question-time frame selection without embedding copies."""

    question_id: str
    candidate_frame_ids: tuple[int, ...]
    selected_history_frame_ids: tuple[int, ...]
    included_short_frame_ids: tuple[int, ...]
    selected_frame_ids: tuple[int, ...]
    frame_scores: Mapping[int, float]
    score_cv: float
    k_mode: Literal["adaptive", "fixed"]
    requested_k: int
    effective_k: int
    ranked_history_frame_ids: tuple[int, ...]
    selected_token_indices: torch.LongTensor
    normalized_frame_scores: Mapping[int, float] = field(default_factory=dict)
    diversity_selection_scores: Mapping[int, float] = field(default_factory=dict)
    diversity_redundancy_scores: Mapping[int, float] = field(default_factory=dict)
    diversity_relevance_weight: float | None = None
    score_direction: Literal["visual_to_query", "query_to_frame"] = "visual_to_query"
