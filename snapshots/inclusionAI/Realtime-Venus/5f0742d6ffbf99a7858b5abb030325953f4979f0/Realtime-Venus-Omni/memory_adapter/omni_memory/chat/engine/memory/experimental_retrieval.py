# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Rank-preserving and static-parallel selectors for long-video retrieval."""

from __future__ import annotations
from typing import Literal
import torch
from .online_manager import PackedMemorySnapshot, PackedVisualFrame
from .retrieval import _pooled_frame_descriptors, select_retrieval_k
from .scoring import (
    ScoreMode,
    TokenWeighting,
    score_dense_visual_bank,
    score_packed_frames,
)
from .types import RetrievalResult

ParallelNoveltyMode = Literal[
    "prior_max",
    "prior_relevance_weighted",
    "prior_rank_window",
    "prior_temporal_decay",
    "global_max",
]
ParallelRelevanceNormalization = Literal["global", "pool"]


def _candidate_frames(
    snapshot: PackedMemorySnapshot, query_tokens: torch.Tensor
) -> tuple[dict[int, PackedVisualFrame], tuple[int, ...]]:
    if query_tokens.ndim != 2 or query_tokens.shape[0] <= 0:
        raise ValueError("query_tokens must have non-empty shape [Q,D]")
    by_frame = {frame.frame_index: frame for frame in snapshot.frames}
    if not by_frame:
        raise ValueError("packed memory snapshot contains no visual embeddings")
    hidden_sizes = {int(frame.embeddings.shape[1]) for frame in snapshot.frames}
    if len(hidden_sizes) != 1 or query_tokens.shape[1] != next(iter(hidden_sizes)):
        raise ValueError("query_tokens hidden size must match visual embeddings")
    for frame_index in snapshot.short_frame_ids:
        frame = by_frame.get(frame_index)
        if frame is None or frame.token_indices != tuple(range(64)):
            raise ValueError("short-term frames must remain complete")
    candidate_ids = tuple(
        (
            frame_index
            for frame_index in sorted(
                (*snapshot.mid_frame_ids, *snapshot.long_frame_ids)
            )
            if frame_index in by_frame
        )
    )
    return (by_frame, candidate_ids)


def _finish_result(
    *,
    snapshot: PackedMemorySnapshot,
    by_frame: dict[int, PackedVisualFrame],
    question_id: str,
    candidate_ids: tuple[int, ...],
    selected_order: list[int],
    frame_scores: dict[int, float],
    coefficient: float,
    effective_k: int,
    fixed_k: int,
    base_k: int,
    k_mode: Literal["adaptive", "fixed"],
    normalized_scores: dict[int, float],
    selection_scores: dict[int, float],
    redundancy_scores: dict[int, float],
    relevance_weight: float | None,
) -> RetrievalResult:
    selected_set = set(selected_order)
    remaining_ranked = sorted(
        (
            frame_index
            for frame_index in candidate_ids
            if frame_index not in selected_set
        ),
        key=lambda frame_index: (-frame_scores[frame_index], frame_index),
    )
    complete_ranking = (*selected_order, *remaining_ranked)
    selected_history = tuple(
        (frame_index for frame_index in candidate_ids if frame_index in selected_set)
    )
    included_short = tuple(snapshot.short_frame_ids)
    selected_frames = tuple(
        sorted(
            (*selected_history, *included_short),
            key=lambda frame_index: (
                by_frame[frame_index].timestamp_seconds,
                frame_index,
            ),
        )
    )
    indices = [
        (frame_index, token_index)
        for frame_index in selected_frames
        for token_index in by_frame[frame_index].token_indices
    ]
    device = snapshot.frames[0].embeddings.device
    index_tensor = torch.tensor(indices, dtype=torch.long, device=device)
    if index_tensor.numel() == 0:
        index_tensor = index_tensor.reshape(0, 2)
    return RetrievalResult(
        question_id=question_id,
        candidate_frame_ids=candidate_ids,
        selected_history_frame_ids=selected_history,
        included_short_frame_ids=included_short,
        selected_frame_ids=selected_frames,
        frame_scores=frame_scores,
        score_cv=coefficient,
        k_mode=k_mode,
        requested_k=fixed_k if k_mode == "fixed" else base_k,
        effective_k=effective_k,
        ranked_history_frame_ids=tuple(complete_ranking),
        selected_token_indices=index_tensor,
        normalized_frame_scores=normalized_scores,
        diversity_selection_scores=selection_scores,
        diversity_redundancy_scores=redundancy_scores,
        diversity_relevance_weight=relevance_weight,
        score_direction="query_to_frame",
    )


def _normalize_scores(
    candidate_ids: tuple[int, ...], frame_scores: dict[int, float], device: torch.device
) -> tuple[torch.Tensor, dict[int, float]]:
    raw = torch.tensor(
        [frame_scores[frame_index] for frame_index in candidate_ids],
        dtype=torch.float32,
        device=device,
    )
    minimum = raw.min()
    span = raw.max() - minimum
    normalized = (
        torch.ones_like(raw) if float(span.item()) <= 1e-12 else (raw - minimum) / span
    )
    return (
        normalized,
        {
            frame_index: float(normalized[position].item())
            for (position, frame_index) in enumerate(candidate_ids)
        },
    )


def _normalize_tensor(values: torch.Tensor) -> torch.Tensor:
    """Min-max normalize one finite vector with a deterministic flat fallback."""
    if values.ndim != 1 or values.numel() == 0:
        raise ValueError("values must be a non-empty one-dimensional tensor")
    minimum = values.min()
    span = values.max() - minimum
    return (
        torch.ones_like(values)
        if float(span.item()) <= 1e-12
        else (values - minimum) / span
    )


def _parallel_redundancy(
    pairwise_similarity: torch.Tensor,
    pool_relevance: torch.Tensor,
    pool_timestamps: torch.Tensor,
    *,
    mode: ParallelNoveltyMode,
    rank_window: int,
    temporal_decay_scale_seconds: float,
) -> tuple[torch.Tensor, str]:
    """Compute all static redundancy scores with one matrix reduction."""
    if (
        pairwise_similarity.ndim != 2
        or pairwise_similarity.shape[0] != pairwise_similarity.shape[1]
    ):
        raise ValueError("pairwise_similarity must be square")
    pool_size = int(pairwise_similarity.shape[0])
    if pool_relevance.shape != (pool_size,):
        raise ValueError("pool_relevance must match the similarity matrix")
    if pool_timestamps.shape != (pool_size,):
        raise ValueError("pool_timestamps must match the similarity matrix")
    prior_mask = torch.tril(
        torch.ones(
            (pool_size, pool_size), dtype=torch.bool, device=pairwise_similarity.device
        ),
        diagonal=-1,
    )
    weighted_similarity = pairwise_similarity
    definition = "max_similarity_to_earlier_relevance_rank"
    if mode == "prior_relevance_weighted":
        weighted_similarity = pairwise_similarity * pool_relevance.unsqueeze(0)
        definition = "max_similarity_times_prior_relevance"
    elif mode == "prior_rank_window":
        rows = torch.arange(pool_size, device=pairwise_similarity.device).unsqueeze(1)
        columns = torch.arange(pool_size, device=pairwise_similarity.device).unsqueeze(
            0
        )
        prior_mask = prior_mask & (rows - columns <= int(rank_window))
        definition = f"max_similarity_to_previous_{int(rank_window)}_ranks"
    elif mode == "prior_temporal_decay":
        temporal_distance = (
            pool_timestamps.unsqueeze(1) - pool_timestamps.unsqueeze(0)
        ).abs()
        decay = torch.exp(
            -temporal_distance / max(float(temporal_decay_scale_seconds), 1e-12)
        )
        weighted_similarity = pairwise_similarity * decay
        definition = "max_similarity_times_exponential_temporal_decay"
    elif mode == "global_max":
        global_mask = ~torch.eye(
            pool_size, dtype=torch.bool, device=pairwise_similarity.device
        )
        if pool_size == 1:
            return (
                torch.zeros(1, device=pairwise_similarity.device),
                "max_similarity_to_any_other_pool_frame",
            )
        redundancy = (
            pairwise_similarity.masked_fill(~global_mask, float("-inf"))
            .max(dim=1)
            .values
        )
        return (redundancy, "max_similarity_to_any_other_pool_frame")
    elif mode != "prior_max":
        raise ValueError(f"unknown parallel novelty mode: {mode}")
    redundancy = (
        weighted_similarity.masked_fill(~prior_mask, float("-inf")).max(dim=1).values
    )
    redundancy = torch.where(
        torch.isfinite(redundancy), redundancy, torch.zeros_like(redundancy)
    )
    return (redundancy, definition)


def retrieve_parallel_dominance_novelty_packed(
    snapshot: PackedMemorySnapshot,
    question_id: str,
    query_tokens: torch.Tensor,
    *,
    k_mode: Literal["adaptive", "fixed"] = "fixed",
    fixed_k: int = 64,
    base_k: int = 10,
    low_cv: float = 0.05,
    high_cv: float = 0.3,
    minimum_fraction: float = 0.9,
    score_mode: ScoreMode = "late_interaction",
    token_weighting: TokenWeighting = "uniform",
    match_top_r: int = 1,
    candidate_pool_size: int = 256,
    relevance_weight: float = 0.5,
    relevance_normalization: ParallelRelevanceNormalization = "global",
    novelty_mode: ParallelNoveltyMode = "prior_max",
    rank_window: int = 64,
    temporal_decay_fraction: float = 0.05,
    dense_visual_embeddings: torch.Tensor | None = None,
    dense_inverse_token_norms: torch.Tensor | None = None,
    dense_frame_chunk_size: int = 256,
) -> RetrievalResult:
    """Select fixed-K frames with a batched, static relevance-novelty score.

    Candidates are first ordered once by query-to-frame relevance. The default
    mode defines novelty against earlier frames in that deterministic order;
    Registered modes only change the matrix mask or element-wise weights.
    This is intentionally *not* greedy MMR: all pairwise similarities and all
    final selection scores are computed in batched tensor operations, with no
    K-step dependency on previously selected frames.
    """
    if not isinstance(question_id, str) or not question_id:
        raise ValueError("question_id must be a non-empty string")
    if (
        isinstance(candidate_pool_size, bool)
        or not isinstance(candidate_pool_size, int)
        or candidate_pool_size <= 0
    ):
        raise ValueError("candidate_pool_size must be a positive integer")
    if (
        isinstance(relevance_weight, bool)
        or not isinstance(relevance_weight, (int, float))
        or (not torch.isfinite(torch.tensor(float(relevance_weight))))
        or (not 0.0 <= float(relevance_weight) <= 1.0)
    ):
        raise ValueError("relevance_weight must be finite and in [0,1]")
    if relevance_normalization not in {"global", "pool"}:
        raise ValueError("relevance_normalization must be global or pool")
    if novelty_mode not in {
        "prior_max",
        "prior_relevance_weighted",
        "prior_rank_window",
        "prior_temporal_decay",
        "global_max",
    }:
        raise ValueError("unknown parallel novelty mode")
    if (
        isinstance(rank_window, bool)
        or not isinstance(rank_window, int)
        or rank_window <= 0
    ):
        raise ValueError("rank_window must be a positive integer")
    if (
        isinstance(temporal_decay_fraction, bool)
        or not isinstance(temporal_decay_fraction, (int, float))
        or (not torch.isfinite(torch.tensor(float(temporal_decay_fraction))))
        or (float(temporal_decay_fraction) <= 0.0)
    ):
        raise ValueError("temporal_decay_fraction must be finite and positive")
    if (dense_visual_embeddings is None) != (dense_inverse_token_norms is None):
        raise ValueError(
            "dense_visual_embeddings and dense_inverse_token_norms must be provided together"
        )
    (by_frame, candidate_ids) = _candidate_frames(snapshot, query_tokens)
    device = snapshot.frames[0].embeddings.device
    if candidate_ids:
        if dense_visual_embeddings is not None:
            assert dense_inverse_token_norms is not None
            if score_mode != "late_interaction":
                raise ValueError("dense visual scorer requires late_interaction")
            if candidate_ids != tuple(range(len(candidate_ids))):
                raise ValueError(
                    "dense visual scorer requires history candidates to be a contiguous prefix"
                )
            if dense_visual_embeddings.ndim != 3 or dense_visual_embeddings.shape[
                0
            ] < len(candidate_ids):
                raise ValueError(
                    "dense_visual_embeddings must contain every history candidate"
                )
            if dense_inverse_token_norms.shape != dense_visual_embeddings.shape[:2]:
                raise ValueError(
                    "dense_inverse_token_norms must align with dense_visual_embeddings"
                )
            dense_result = score_dense_visual_bank(
                dense_visual_embeddings[: len(candidate_ids)],
                dense_inverse_token_norms[: len(candidate_ids)],
                query_tokens,
                token_weighting=token_weighting,
                match_top_r=match_top_r,
                frame_chunk_size=dense_frame_chunk_size,
            )
            score_values = dense_result.scores.detach().cpu().tolist()
            frame_scores = {
                frame_index: float(score_values[position])
                for (position, frame_index) in enumerate(candidate_ids)
            }
        else:
            frame_scores = score_packed_frames(
                snapshot,
                candidate_ids,
                query_tokens,
                score_mode=score_mode,
                token_weighting=token_weighting,
                match_top_r=match_top_r,
            )
        (effective_k, coefficient) = select_retrieval_k(
            [frame_scores[index] for index in candidate_ids],
            k_mode=k_mode,
            fixed_k=fixed_k,
            base_k=base_k,
            low_cv=low_cv,
            high_cv=high_cv,
            minimum_fraction=minimum_fraction,
        )
    else:
        frame_scores = {}
        effective_k = 0
        coefficient = 0.0
    selected_order: list[int] = []
    selection_scores: dict[int, float] = {}
    redundancy_scores: dict[int, float] = {}
    normalized_scores: dict[int, float] = {}
    if effective_k:
        if candidate_pool_size < effective_k:
            raise ValueError(
                "candidate_pool_size must be at least the effective retrieval K"
            )
        (normalized, normalized_scores) = _normalize_scores(
            candidate_ids, frame_scores, device
        )
        raw = torch.tensor(
            [frame_scores[index] for index in candidate_ids],
            dtype=torch.float32,
            device=device,
        )
        relevance_positions = torch.argsort(raw, descending=True, stable=True)
        pool_size = min(int(candidate_pool_size), len(candidate_ids))
        pool_positions = relevance_positions[:pool_size]
        pool_ids = tuple(
            (candidate_ids[position] for position in pool_positions.tolist())
        )
        pool_relevance = (
            _normalize_tensor(raw[pool_positions])
            if relevance_normalization == "pool"
            else normalized[pool_positions]
        )
        if relevance_normalization == "pool":
            normalized_scores.update(
                {
                    frame_index: float(pool_relevance[position].item())
                    for (position, frame_index) in enumerate(pool_ids)
                }
            )
        pooled_descriptors = _pooled_frame_descriptors(snapshot, pool_ids)
        pairwise_similarity = pooled_descriptors @ pooled_descriptors.T
        pairwise_similarity = ((pairwise_similarity + 1.0) * 0.5).clamp(0.0, 1.0)
        pool_timestamps = torch.tensor(
            [by_frame[frame_index].timestamp_seconds for frame_index in pool_ids],
            dtype=torch.float32,
            device=device,
        )
        all_timestamps = torch.tensor(
            [frame.timestamp_seconds for frame in snapshot.frames],
            dtype=torch.float32,
            device=device,
        )
        video_span_seconds = float((all_timestamps.max() - all_timestamps.min()).item())
        temporal_decay_scale_seconds = max(
            video_span_seconds * float(temporal_decay_fraction), 1e-12
        )
        (redundancy, novelty_definition) = _parallel_redundancy(
            pairwise_similarity,
            pool_relevance,
            pool_timestamps,
            mode=novelty_mode,
            rank_window=rank_window,
            temporal_decay_scale_seconds=temporal_decay_scale_seconds,
        )
        novelty = 1.0 - redundancy
        combined = (
            float(relevance_weight) * pool_relevance
            + (1.0 - float(relevance_weight)) * novelty
        )
        selected_pool_positions = torch.argsort(combined, descending=True, stable=True)[
            :effective_k
        ]
        selected_order = [
            pool_ids[position] for position in selected_pool_positions.tolist()
        ]
        for position in selected_pool_positions.tolist():
            frame_index = pool_ids[position]
            selection_scores[frame_index] = float(combined[position].item())
            redundancy_scores[frame_index] = float(redundancy[position].item())
    return _finish_result(
        snapshot=snapshot,
        by_frame=by_frame,
        question_id=question_id,
        candidate_ids=candidate_ids,
        selected_order=selected_order,
        frame_scores=frame_scores,
        coefficient=coefficient,
        effective_k=effective_k,
        fixed_k=fixed_k,
        base_k=base_k,
        k_mode=k_mode,
        normalized_scores=normalized_scores,
        selection_scores=selection_scores,
        redundancy_scores=redundancy_scores,
        relevance_weight=float(relevance_weight),
    )
