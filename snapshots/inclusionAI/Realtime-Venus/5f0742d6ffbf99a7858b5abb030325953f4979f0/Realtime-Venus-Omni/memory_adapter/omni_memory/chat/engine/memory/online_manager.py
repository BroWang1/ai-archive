# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Streaming SAVEMem visual state without a full-video embedding tensor."""

from __future__ import annotations
from dataclasses import dataclass
import torch
from .types import FrameTokenStore, MemoryTier


@dataclass(frozen=True)
class PackedVisualFrame:
    """Owned surviving embeddings for one original sampled frame."""

    frame_index: int
    timestamp_seconds: float
    source_frame_index: int
    tier: str
    token_indices: tuple[int, ...]
    semantic_scores: tuple[float, ...]
    embeddings: torch.Tensor


@dataclass(frozen=True)
class PackedMemorySnapshot:
    """Bounded visual embeddings with frame metadata."""

    frame_count: int
    frames: tuple[PackedVisualFrame, ...]
    tier_by_frame: tuple[MemoryTier, ...]
    scene_change_flags: tuple[bool, ...]
    short_frame_ids: tuple[int, ...]
    mid_frame_ids: tuple[int, ...]
    long_frame_ids: tuple[int, ...]
    pair_mean_distances: tuple[float | None, ...]

    @property
    def kept_token_count(self) -> int:
        return sum((len(frame.token_indices) for frame in self.frames))

    def dense_keep_mask(self, *, device: torch.device | str = "cpu") -> torch.Tensor:
        mask = torch.zeros((self.frame_count, 64), dtype=torch.bool, device=device)
        for frame in self.frames:
            if frame.token_indices:
                mask[frame.frame_index, list(frame.token_indices)] = True
        return mask


def _validate_nonnegative_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _validate_positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def pack_dense_visual_store(
    store: FrameTokenStore, *, short_capacity: int, mid_capacity: int
) -> PackedMemorySnapshot:
    """Expose a complete visual store through the packed retrieval contract.

    Each packed frame is a view into the single dense tensor owned by ``store``;
    this function does not clone visual embeddings or apply compression.
    """
    short_capacity = _validate_nonnegative_int(short_capacity, "short_capacity")
    mid_capacity = _validate_positive_int(mid_capacity, "mid_capacity")
    short_start = max(0, store.frame_count - short_capacity)
    mid_start = max(0, short_start - mid_capacity)
    long_ids = tuple(range(mid_start))
    mid_ids = tuple(range(mid_start, short_start))
    short_ids = tuple(range(short_start, store.frame_count))
    tier_by_frame: tuple[MemoryTier, ...] = tuple(
        (
            (
                "long"
                if frame_index < mid_start
                else "mid" if frame_index < short_start else "short"
            )
            for frame_index in range(store.frame_count)
        )
    )
    token_indices = tuple(range(store.tokens_per_frame))
    zero_scores = (0.0,) * store.tokens_per_frame
    timestamps = tuple(
        (float(value) for value in store.timestamps.detach().cpu().tolist())
    )
    source_indices = tuple(
        (int(value) for value in store.source_frame_indices.detach().cpu().tolist())
    )
    frames = tuple(
        (
            PackedVisualFrame(
                frame_index=frame_index,
                timestamp_seconds=timestamps[frame_index],
                source_frame_index=source_indices[frame_index],
                tier=str(tier_by_frame[frame_index]),
                token_indices=token_indices,
                semantic_scores=zero_scores,
                embeddings=store.embeddings[frame_index],
            )
            for frame_index in range(store.frame_count)
        )
    )
    return PackedMemorySnapshot(
        frame_count=store.frame_count,
        frames=frames,
        tier_by_frame=tier_by_frame,
        scene_change_flags=(False,) * store.frame_count,
        short_frame_ids=short_ids,
        mid_frame_ids=mid_ids,
        long_frame_ids=long_ids,
        pair_mean_distances=(None,) * store.frame_count,
    )
