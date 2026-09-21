# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Query-only relevance scorers for visual frames and audio blocks."""

from __future__ import annotations
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal
import torch
import torch.nn.functional as functional
from .online_manager import PackedMemorySnapshot

ScoreMode = Literal["late_interaction", "pooled_cosine"]
TokenWeighting = Literal["uniform", "mad"]


@dataclass(frozen=True)
class MediaScoreResult:
    """Media relevance scores and query-token weights."""

    scores: tuple[float, ...]
    query_token_weights: tuple[float, ...]
    score_mode: ScoreMode
    token_weighting: TokenWeighting
    match_top_r: int
    weighting_scale: tuple[float, ...]


@dataclass(frozen=True)
class DenseMediaScoreResult:
    """Tensor-resident late-interaction scores for one dense visual bank.

    This representation deliberately keeps all score-side values on the
    visual device.  The caller can therefore rank and select frames before it
    materializes frame-indexed scores on CPU.
    """

    scores: torch.Tensor
    query_token_weights: torch.Tensor
    weighting_scale: torch.Tensor
    match_matrix: torch.Tensor


def _validate_query(query_tokens: torch.Tensor) -> None:
    if not isinstance(query_tokens, torch.Tensor) or query_tokens.ndim != 2:
        raise ValueError("query_tokens must have shape [Q,D]")
    if query_tokens.shape[0] <= 0 or query_tokens.shape[1] <= 0:
        raise ValueError("query_tokens must be non-empty")
    if not torch.isfinite(query_tokens).all():
        raise ValueError("query_tokens must be finite")


def _validate_scoring(
    *, score_mode: ScoreMode, token_weighting: TokenWeighting, match_top_r: int
) -> None:
    if score_mode not in {"late_interaction", "pooled_cosine"}:
        raise ValueError("score_mode must be late_interaction or pooled_cosine")
    if token_weighting not in {"uniform", "mad"}:
        raise ValueError("token_weighting must be uniform or mad")
    if (
        isinstance(match_top_r, bool)
        or not isinstance(match_top_r, int)
        or match_top_r <= 0
    ):
        raise ValueError("match_top_r must be a positive integer")
    if score_mode == "pooled_cosine" and (
        token_weighting != "uniform" or match_top_r != 1
    ):
        raise ValueError(
            "pooled_cosine requires token_weighting=uniform and match_top_r=1"
        )


def _query_weights(
    match_matrix: torch.Tensor, token_weighting: TokenWeighting
) -> tuple[torch.Tensor, torch.Tensor]:
    """Return normalized token weights and their raw robust dispersion."""
    if match_matrix.ndim != 2 or match_matrix.shape[0] <= 0:
        raise ValueError("match_matrix must have non-empty shape [N,Q]")
    query_count = int(match_matrix.shape[1])
    if token_weighting == "uniform":
        raw = torch.ones(query_count, dtype=torch.float32, device=match_matrix.device)
    elif token_weighting == "mad":
        median = match_matrix.median(dim=0).values
        raw = (match_matrix - median).abs().median(dim=0).values
        if float(raw.sum().item()) <= 1e-12:
            raw = (match_matrix - median).abs().mean(dim=0)
        if float(raw.sum().item()) <= 1e-12:
            raw = torch.ones_like(raw)
    else:
        raise ValueError("token_weighting must be uniform or mad")
    weights = raw / raw.sum().clamp_min(1e-12)
    return (weights, raw)


def build_dense_token_inverse_norms(
    embeddings: torch.Tensor, *, frame_chunk_size: int = 256
) -> torch.Tensor:
    """Precompute FP32 inverse token norms for a dense ``[F,64,D]`` bank.

    The original dense scorer normalizes visual tokens in FP32 for every query.
    This helper moves just the denominator computation to video setup time.
    It stores ``[F,64]`` rather than a second normalized visual bank, keeping
    the generation-facing embeddings unchanged and limiting persistent memory.
    """
    if not isinstance(embeddings, torch.Tensor) or embeddings.ndim != 3:
        raise ValueError("embeddings must have shape [F,T,D]")
    if embeddings.shape[0] <= 0 or embeddings.shape[1] <= 0 or embeddings.shape[2] <= 0:
        raise ValueError("embeddings must be non-empty")
    if isinstance(frame_chunk_size, bool) or not isinstance(frame_chunk_size, int):
        raise ValueError("frame_chunk_size must be a positive integer")
    if frame_chunk_size <= 0:
        raise ValueError("frame_chunk_size must be a positive integer")
    chunks: list[torch.Tensor] = []
    for start in range(0, int(embeddings.shape[0]), frame_chunk_size):
        chunk = embeddings[start : start + frame_chunk_size].float()
        chunks.append(
            torch.linalg.vector_norm(chunk, dim=-1).clamp_min(1e-12).reciprocal()
        )
    return torch.cat(chunks, dim=0)


def _dense_query_weights(
    match_matrix: torch.Tensor, token_weighting: TokenWeighting
) -> tuple[torch.Tensor, torch.Tensor]:
    """Compute dense token weights without moving fallback predicates to CPU."""
    if token_weighting == "uniform":
        raw = torch.ones(
            int(match_matrix.shape[1]), dtype=torch.float32, device=match_matrix.device
        )
    elif token_weighting == "mad":
        median = match_matrix.median(dim=0).values
        mad = (match_matrix - median).abs().median(dim=0).values
        mean_absolute_deviation = (match_matrix - median).abs().mean(dim=0)
        raw = torch.where(mad.sum() <= 1e-12, mean_absolute_deviation, mad)
        raw = torch.where(raw.sum() <= 1e-12, torch.ones_like(raw), raw)
    else:
        raise ValueError("token_weighting must be uniform or mad")
    return (raw / raw.sum().clamp_min(1e-12), raw)


@torch.inference_mode()
def score_dense_visual_bank(
    embeddings: torch.Tensor,
    inverse_token_norms: torch.Tensor,
    query_tokens: torch.Tensor,
    *,
    token_weighting: TokenWeighting = "mad",
    match_top_r: int = 1,
    frame_chunk_size: int = 256,
) -> DenseMediaScoreResult:
    """Score a dense visual bank with dense scorer's Top-r late interaction semantics.

    ``embeddings`` remains the original VPM output.  Multiplication by the
    precomputed FP32 inverse norms is algebraically the same cosine
    normalization used by ``_late_interaction_scores`` while avoiding per-query
    frame stacking and visual-norm reductions.
    """
    _validate_query(query_tokens)
    _validate_scoring(
        score_mode="late_interaction",
        token_weighting=token_weighting,
        match_top_r=match_top_r,
    )
    if not isinstance(embeddings, torch.Tensor) or embeddings.ndim != 3:
        raise ValueError("embeddings must have shape [F,T,D]")
    (frame_count, token_count, hidden_size) = (int(value) for value in embeddings.shape)
    if frame_count <= 0 or token_count <= 0 or hidden_size <= 0:
        raise ValueError("embeddings must be non-empty")
    if query_tokens.shape[1] != hidden_size:
        raise ValueError("query_tokens hidden size must match embeddings")
    if inverse_token_norms.shape != (frame_count, token_count):
        raise ValueError("inverse_token_norms must have shape [F,T]")
    if inverse_token_norms.device != embeddings.device:
        raise ValueError("inverse_token_norms must reside with embeddings")
    if inverse_token_norms.dtype != torch.float32:
        raise ValueError("inverse_token_norms must use float32")
    if isinstance(frame_chunk_size, bool) or not isinstance(frame_chunk_size, int):
        raise ValueError("frame_chunk_size must be a positive integer")
    if frame_chunk_size <= 0:
        raise ValueError("frame_chunk_size must be a positive integer")
    query = functional.normalize(query_tokens.float(), dim=-1, eps=1e-12)
    query = query.to(device=embeddings.device)
    matched_chunks: list[torch.Tensor] = []
    top_r = min(match_top_r, token_count)
    for start in range(0, frame_count, frame_chunk_size):
        stop = min(start + frame_chunk_size, frame_count)
        visual = embeddings[start:stop].float()
        similarities = visual @ query.transpose(0, 1)
        similarities.mul_(inverse_token_norms[start:stop].unsqueeze(-1))
        if top_r == 1:
            matched_chunks.append(similarities.amax(dim=1))
        else:
            matched_chunks.append(similarities.topk(top_r, dim=1).values.mean(dim=1))
    match_matrix = torch.cat(matched_chunks, dim=0)
    (weights, raw) = _dense_query_weights(match_matrix, token_weighting)
    return DenseMediaScoreResult(
        scores=match_matrix @ weights,
        query_token_weights=weights,
        weighting_scale=raw,
        match_matrix=match_matrix,
    )


def _late_interaction_scores(
    items: Sequence[torch.Tensor],
    query_tokens: torch.Tensor,
    *,
    token_weighting: TokenWeighting,
    match_top_r: int,
    batch_size: int,
) -> MediaScoreResult:
    if not items:
        raise ValueError("media items cannot be empty")
    if (
        isinstance(batch_size, bool)
        or not isinstance(batch_size, int)
        or batch_size <= 0
    ):
        raise ValueError("batch_size must be a positive integer")
    hidden_size = int(query_tokens.shape[1])
    query = functional.normalize(query_tokens.float(), dim=-1, eps=1e-12)
    matches: list[torch.Tensor] = []
    for start in range(0, len(items), batch_size):
        batch = tuple(items[start : start + batch_size])
        token_counts = {int(item.shape[0]) for item in batch}
        if len(token_counts) != 1:
            for item in batch:
                if item.ndim != 2 or item.shape[0] <= 0 or item.shape[1] != hidden_size:
                    raise ValueError("each media item must have non-empty shape [T,D]")
                if not torch.isfinite(item).all():
                    raise ValueError("media items must be finite")
                visual = functional.normalize(item.float(), dim=-1, eps=1e-12)
                similarity = query.to(visual.device) @ visual.transpose(0, 1)
                top_r = min(match_top_r, int(visual.shape[0]))
                matches.append(
                    similarity.topk(top_r, dim=1).values.mean(dim=1).unsqueeze(0)
                )
            continue
        token_count = next(iter(token_counts))
        top_r = min(match_top_r, token_count)
        for item in batch:
            if item.ndim != 2 or item.shape != (token_count, hidden_size):
                raise ValueError("batched media items must share shape [T,D]")
            if not torch.isfinite(item).all():
                raise ValueError("media items must be finite")
        embeddings = torch.stack(batch)
        normalized = functional.normalize(embeddings.float(), dim=-1, eps=1e-12)
        similarities = normalized @ query.to(normalized.device).transpose(0, 1)
        matches.append(similarities.topk(top_r, dim=1).values.mean(dim=1))
    matrix = torch.cat(matches, dim=0)
    (weights, raw) = _query_weights(matrix, token_weighting)
    scores = matrix @ weights
    return MediaScoreResult(
        scores=tuple((float(value) for value in scores.detach().cpu().tolist())),
        query_token_weights=tuple(
            (float(value) for value in weights.detach().cpu().tolist())
        ),
        score_mode="late_interaction",
        token_weighting=token_weighting,
        match_top_r=match_top_r,
        weighting_scale=tuple((float(value) for value in raw.detach().cpu().tolist())),
    )


def _pooled_scores(
    items: Sequence[torch.Tensor], query_tokens: torch.Tensor
) -> MediaScoreResult:
    if not items:
        raise ValueError("media items cannot be empty")
    hidden_size = int(query_tokens.shape[1])
    query = functional.normalize(
        functional.normalize(query_tokens.float(), dim=-1, eps=1e-12).mean(dim=0),
        dim=0,
        eps=1e-12,
    )
    values: list[float] = []
    for item in items:
        if item.ndim != 2 or item.shape[0] <= 0 or item.shape[1] != hidden_size:
            raise ValueError("each media item must have non-empty shape [T,D]")
        if not torch.isfinite(item).all():
            raise ValueError("media items must be finite")
        descriptor = functional.normalize(
            functional.normalize(item.float(), dim=-1, eps=1e-12).mean(dim=0),
            dim=0,
            eps=1e-12,
        )
        values.append(float(torch.dot(descriptor, query.to(descriptor.device)).item()))
    uniform = 1.0 / int(query_tokens.shape[0])
    return MediaScoreResult(
        scores=tuple(values),
        query_token_weights=tuple((uniform for _ in range(query_tokens.shape[0]))),
        score_mode="pooled_cosine",
        token_weighting="uniform",
        match_top_r=1,
        weighting_scale=tuple((1.0 for _ in range(query_tokens.shape[0]))),
    )


def score_media_items(
    items: Sequence[torch.Tensor],
    query_tokens: torch.Tensor,
    *,
    score_mode: ScoreMode = "late_interaction",
    token_weighting: TokenWeighting = "uniform",
    match_top_r: int = 1,
    batch_size: int = 64,
) -> MediaScoreResult:
    """Score media using only its resident embeddings and the raw user query."""
    _validate_query(query_tokens)
    _validate_scoring(
        score_mode=score_mode, token_weighting=token_weighting, match_top_r=match_top_r
    )
    if score_mode == "pooled_cosine":
        return _pooled_scores(items, query_tokens)
    return _late_interaction_scores(
        items,
        query_tokens,
        token_weighting=token_weighting,
        match_top_r=match_top_r,
        batch_size=batch_size,
    )


def score_packed_frames(
    snapshot: PackedMemorySnapshot,
    candidate_ids: Sequence[int],
    query_tokens: torch.Tensor,
    *,
    score_mode: ScoreMode = "late_interaction",
    token_weighting: TokenWeighting = "uniform",
    match_top_r: int = 1,
) -> dict[int, float]:
    """Return frame-indexed scores."""
    ids = tuple(candidate_ids)
    by_frame = {frame.frame_index: frame for frame in snapshot.frames}
    if any((frame_index not in by_frame for frame_index in ids)):
        raise ValueError("candidate_ids must reference resident frames")
    result = score_media_items(
        tuple((by_frame[frame_index].embeddings for frame_index in ids)),
        query_tokens,
        score_mode=score_mode,
        token_weighting=token_weighting,
        match_top_r=match_top_r,
        batch_size=64,
    )
    return {
        frame_index: result.scores[position]
        for (position, frame_index) in enumerate(ids)
    }
