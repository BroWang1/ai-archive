# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Protected live window and bounded KV-backed historical retrieval memory."""

from __future__ import annotations
import math
from collections import deque
from dataclasses import dataclass, replace
from typing import Any, Callable, Iterable
import torch
import torch.nn.functional as functional
from torch.nn.utils.rnn import pad_sequence


@dataclass(frozen=True)
class MemoryUnit:
    """One complete duplex unit and the artifacts required to retrieve it."""

    unit_id: int
    timestamp_seconds: float
    visual_embeddings: torch.Tensor | None
    descriptor: torch.Tensor | None
    kv_cache: Any
    kv_bytes: int
    kv_source_start: int
    kv_source_end: int
    kv_capture_local_start: int
    kv_capture_local_end: int
    keep_after_hot_window: bool
    visual_frame_count: int = 0
    has_audio: bool = False
    pcost_role: str = "I"
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.unit_id < 0:
            raise ValueError("unit_id must be nonnegative")
        if self.timestamp_seconds < 0:
            raise ValueError("timestamp_seconds must be nonnegative")
        if self.kv_bytes < 0:
            raise ValueError("kv_bytes must be nonnegative")
        if self.visual_frame_count < 0:
            raise ValueError("visual_frame_count must be nonnegative")
        if self.kv_source_start < 0 or self.kv_source_end <= self.kv_source_start:
            raise ValueError("invalid absolute KV timeline span")
        if (
            self.kv_capture_local_start < 0
            or self.kv_capture_local_end <= self.kv_capture_local_start
        ):
            raise ValueError("invalid capture-local KV token span")
        if (
            self.kv_source_end - self.kv_source_start
            != self.kv_capture_local_end - self.kv_capture_local_start
        ):
            raise ValueError(
                "absolute and capture-local KV spans must have equal length"
            )
        if self.visual_embeddings is not None and self.visual_embeddings.ndim != 2:
            raise ValueError("visual_embeddings must have shape [tokens, hidden]")
        if self.descriptor is not None and self.descriptor.ndim != 1:
            raise ValueError("descriptor must have shape [hidden]")


@dataclass(frozen=True)
class RetrievalSelection:
    """Immutable query result used to assemble a query-specific cache."""

    units: tuple[MemoryUnit, ...]
    history_unit_ids: tuple[int, ...]
    recent_unit_ids: tuple[int, ...]
    relevance_scores: tuple[tuple[int, float], ...]
    final_scores: tuple[tuple[int, float], ...]


@dataclass(frozen=True)
class QueryMemoryView:
    """Immutable unit references frozen when one text query arrives."""

    archived_units: tuple[MemoryUnit, ...]
    recent_units: tuple[MemoryUnit, ...]


@dataclass(frozen=True)
class ArchiveEviction:
    """One whole-unit FIFO eviction and the limits that triggered it."""

    unit_id: int
    timestamp_seconds: float
    kv_bytes: int
    visual_bytes: int
    payload_bytes: int
    reasons: tuple[str, ...]


def pooled_descriptor(visual_embeddings: torch.Tensor) -> torch.Tensor:
    """Normalize, mean-pool and normalize the 64 Realtime-Venus-Omni visual tokens."""
    if visual_embeddings.ndim != 2 or visual_embeddings.shape[0] == 0:
        raise ValueError("visual_embeddings must be non-empty [tokens, hidden]")
    tokens = functional.normalize(visual_embeddings.float(), dim=-1, eps=1e-12)
    return functional.normalize(tokens.mean(dim=0), dim=-1, eps=1e-12)


def unit_visual_bytes(unit: MemoryUnit) -> int:
    """Return visual-token plus descriptor tensor payload for one unit."""
    total = 0
    for tensor in (unit.visual_embeddings, unit.descriptor):
        if tensor is not None:
            total += int(tensor.numel()) * int(tensor.element_size())
    return total


def unit_payload_bytes(unit: MemoryUnit) -> int:
    """Return the archive payload governed by the FIFO byte budget."""
    return int(unit.kv_bytes) + unit_visual_bytes(unit)


class OmniLongTermMemory:
    """Recent-frame retrieval memory plus a time-bounded long-term archive."""

    def __init__(
        self,
        *,
        retrieval_recent_frames: int = 4,
        candidate_pool_size: int = 128,
        history_top_k: int = 64,
        retrieval_score_batch_size: int = 128,
        archive_retention_seconds: float = 1800.0,
        archive_memory_budget_bytes: int | None = None,
        max_archived_units: int | None = None,
        relevance_weight: float = 0.5,
        archive_transform: Callable[[MemoryUnit], MemoryUnit] | None = None,
    ) -> None:
        if retrieval_recent_frames <= 0:
            raise ValueError("retrieval_recent_frames must be positive")
        if candidate_pool_size <= 0 or history_top_k <= 0:
            raise ValueError("candidate_pool_size and history_top_k must be positive")
        if candidate_pool_size < history_top_k:
            raise ValueError("candidate_pool_size must be at least history_top_k")
        if retrieval_score_batch_size <= 0:
            raise ValueError("retrieval_score_batch_size must be positive")
        if archive_retention_seconds <= 0:
            raise ValueError("archive_retention_seconds must be positive")
        if archive_memory_budget_bytes is not None and archive_memory_budget_bytes <= 0:
            raise ValueError("archive_memory_budget_bytes must be positive or None")
        if max_archived_units is not None and max_archived_units <= 0:
            raise ValueError("max_archived_units must be positive or None")
        if not 0 <= relevance_weight <= 1:
            raise ValueError("relevance_weight must be in [0, 1]")
        self.retrieval_recent_frames = int(retrieval_recent_frames)
        self.candidate_pool_size = candidate_pool_size
        self.history_top_k = history_top_k
        self.retrieval_score_batch_size = retrieval_score_batch_size
        self.archive_retention_seconds = float(archive_retention_seconds)
        self.archive_memory_budget_bytes = archive_memory_budget_bytes
        self.max_archived_units = max_archived_units
        self.relevance_weight = relevance_weight
        self.archive_transform = archive_transform
        self._hot: list[MemoryUnit] = []
        self._archive: deque[MemoryUnit] = deque()
        self._resident_unit_ids: set[int] = set()
        self._dropped_unit_ids: list[int] = []
        self._archived_kv_bytes = 0
        self._archived_visual_bytes = 0
        self._last_archive_evictions: tuple[ArchiveEviction, ...] = ()
        self._last_archived_unit_ids: tuple[int, ...] = ()
        self._latest_timestamp_seconds: float | None = None

    @property
    def hot_units(self) -> tuple[MemoryUnit, ...]:
        return tuple(self._hot)

    @property
    def archived_units(self) -> tuple[MemoryUnit, ...]:
        return tuple(self._archive)

    @property
    def dropped_unit_ids(self) -> tuple[int, ...]:
        return tuple(self._dropped_unit_ids)

    @property
    def last_archive_evictions(self) -> tuple[ArchiveEviction, ...]:
        """FIFO evictions caused by the most recent :meth:`add_unit` call."""
        return self._last_archive_evictions

    @property
    def last_archived_unit_ids(self) -> tuple[int, ...]:
        """Units moved from the hot window to archive by the latest add."""
        return self._last_archived_unit_ids

    @property
    def archived_kv_bytes(self) -> int:
        return self._archived_kv_bytes

    @property
    def archived_visual_bytes(self) -> int:
        """Tensor payload retained for visual retrieval, including descriptors."""
        return self._archived_visual_bytes

    @property
    def archived_total_bytes(self) -> int:
        return self._archived_kv_bytes + self._archived_visual_bytes

    def add_unit(self, unit: MemoryUnit) -> tuple[MemoryUnit, ...]:
        """Add to memory and return units logically removed from live/archive."""
        if unit.unit_id in self._resident_unit_ids:
            raise ValueError(f"duplicate unit_id: {unit.unit_id}")
        if (
            self._latest_timestamp_seconds is not None
            and unit.timestamp_seconds < self._latest_timestamp_seconds
        ):
            raise ValueError("streaming memory requires nondecreasing timestamps")
        if unit.descriptor is None and unit.visual_embeddings is not None:
            unit = replace(unit, descriptor=pooled_descriptor(unit.visual_embeddings))
        self._latest_timestamp_seconds = unit.timestamp_seconds
        self._last_archive_evictions = ()
        self._last_archived_unit_ids = ()
        self._hot.append(unit)
        self._resident_unit_ids.add(unit.unit_id)
        removed: list[MemoryUnit] = []
        newly_archived: list[int] = []
        expire_count = self._expired_recent_unit_count()
        for _ in range(expire_count):
            expired = self._hot.pop(0)
            if expired.keep_after_hot_window and expired.kv_cache is not None:
                if self.archive_transform is not None:
                    expired = self.archive_transform(expired)
                self._append_archive(expired)
                newly_archived.append(expired.unit_id)
            else:
                self._resident_unit_ids.remove(expired.unit_id)
                self._dropped_unit_ids.append(expired.unit_id)
                removed.append(expired)
        self._last_archived_unit_ids = tuple(newly_archived)
        removed.extend(self._enforce_archive_limits(unit.timestamp_seconds))
        return tuple(removed)

    def _expired_recent_unit_count(self) -> int:
        """Return whole leading units outside the latest sampled-frame window."""
        accumulated_frames = 0
        keep_from = 0
        found_boundary = False
        for index in range(len(self._hot) - 1, -1, -1):
            accumulated_frames += self._hot[index].visual_frame_count
            if accumulated_frames >= self.retrieval_recent_frames:
                keep_from = index
                found_boundary = True
                break
        if found_boundary:
            return keep_from
        first_visual = next(
            (
                index
                for (index, candidate) in enumerate(self._hot)
                if candidate.visual_frame_count > 0
            ),
            None,
        )
        if first_visual is not None:
            return first_visual
        return max(0, len(self._hot) - self.retrieval_recent_frames)

    def all_units(self) -> tuple[MemoryUnit, ...]:
        return tuple(self._archive) + tuple(self._hot)

    def eligible_unit_ids(self) -> tuple[int, ...]:
        """Return immutable IDs that a query arriving now may observe."""
        return tuple((unit.unit_id for unit in self.all_units()))

    def select(
        self,
        query_tokens: torch.Tensor,
        *,
        eligible_unit_ids: Iterable[int] | None = None,
    ) -> RetrievalSelection:
        """Select against a view of the memory captured by this call."""
        view = self.snapshot_for_query(eligible_unit_ids=eligible_unit_ids)
        return self.select_from_view(query_tokens, view)

    def snapshot_for_query(
        self, *, eligible_unit_ids: Iterable[int] | None = None
    ) -> QueryMemoryView:
        """Freeze archive and recent-unit references for one arriving query."""
        eligible = None if eligible_unit_ids is None else set(eligible_unit_ids)
        archived = tuple(
            (
                unit
                for unit in self._archive
                if unit.visual_embeddings is not None
                and unit.kv_cache is not None
                and (eligible is None or unit.unit_id in eligible)
            )
        )
        recent = tuple(
            (
                unit
                for unit in self._hot
                if unit.kv_cache is not None
                and (eligible is None or unit.unit_id in eligible)
            )
        )
        return QueryMemoryView(archived_units=archived, recent_units=recent)

    def select_from_view(
        self, query_tokens: torch.Tensor, view: QueryMemoryView
    ) -> RetrievalSelection:
        """Run retrieval without consulting mutable live-memory containers."""
        if query_tokens.ndim != 2 or query_tokens.shape[0] == 0:
            raise ValueError("query_tokens must be non-empty [tokens, hidden]")
        if not isinstance(view, QueryMemoryView):
            raise TypeError("view must be a QueryMemoryView")
        history = list(view.archived_units)
        recent = list(view.recent_units)
        (relevance, visual_token_count, score_batch_count) = self._relevance(
            history, query_tokens
        )
        ranked = sorted(
            history, key=lambda unit: (-relevance[unit.unit_id], unit.unit_id)
        )
        pool = ranked[: self.candidate_pool_size]
        final = self._parallel_novelty_scores(pool, relevance, history)
        selected_history = sorted(
            pool, key=lambda unit: (-final[unit.unit_id], unit.unit_id)
        )[: self.history_top_k]
        by_id = {unit.unit_id: unit for unit in (*selected_history, *recent)}
        selected = tuple(
            sorted(
                by_id.values(), key=lambda unit: (unit.timestamp_seconds, unit.unit_id)
            )
        )
        return RetrievalSelection(
            units=selected,
            history_unit_ids=tuple((unit.unit_id for unit in selected_history)),
            recent_unit_ids=tuple((unit.unit_id for unit in recent)),
            relevance_scores=tuple(sorted(relevance.items())),
            final_scores=tuple(sorted(final.items())),
        )

    def _relevance(
        self, units: list[MemoryUnit], query_tokens: torch.Tensor
    ) -> tuple[dict[int, float], int, int]:
        """Batched MAD-weighted Top-1 late interaction over visual tokens."""
        if not units:
            return ({}, 0, 0)
        target_device = units[0].visual_embeddings.device
        hidden_size = int(query_tokens.shape[1])
        visual_token_count = 0
        matched: list[torch.Tensor] = []
        query = functional.normalize(
            query_tokens.float().to(target_device), dim=-1, eps=1e-12
        )
        for start in range(0, len(units), self.retrieval_score_batch_size):
            batch_units = units[start : start + self.retrieval_score_batch_size]
            visuals: list[torch.Tensor] = []
            lengths: list[int] = []
            for unit in batch_units:
                visual = unit.visual_embeddings
                if visual is None:
                    raise ValueError(
                        f"archived unit {unit.unit_id} has no visual embeddings"
                    )
                if visual.ndim != 2 or visual.shape[0] == 0:
                    raise ValueError(
                        f"archived unit {unit.unit_id} has invalid visual embeddings"
                    )
                if int(visual.shape[1]) != hidden_size:
                    raise ValueError(
                        "query and archived visual hidden sizes must match"
                    )
                moved = visual.to(target_device)
                visuals.append(moved)
                lengths.append(int(moved.shape[0]))
            visual_token_count += sum(lengths)
            same_length = len(set(lengths)) == 1
            visual_batch = (
                torch.stack(visuals, dim=0).float()
                if same_length
                else pad_sequence(
                    [visual.float() for visual in visuals],
                    batch_first=True,
                    padding_value=0.0,
                )
            )
            visual_batch = functional.normalize(visual_batch, dim=-1, eps=1e-12)
            valid_tokens = None
            if not same_length:
                positions = torch.arange(visual_batch.shape[1], device=target_device)
                valid_tokens = positions.unsqueeze(0) < torch.tensor(
                    lengths, device=target_device
                ).unsqueeze(1)
            similarities = visual_batch @ query.T
            if valid_tokens is not None:
                similarities = similarities.masked_fill(
                    ~valid_tokens.unsqueeze(-1), float("-inf")
                )
            matched.append(similarities.amax(dim=1))
        match_matrix = torch.cat(matched, dim=0)
        median = match_matrix.median(dim=0).values
        absolute = (match_matrix - median).abs()
        raw_weights = absolute.median(dim=0).values
        if float(raw_weights.sum().item()) <= 1e-12:
            raw_weights = absolute.mean(dim=0)
        if float(raw_weights.sum().item()) <= 1e-12:
            raw_weights = torch.ones_like(raw_weights)
        weights = raw_weights / raw_weights.sum().clamp_min(1e-12)
        values = match_matrix @ weights
        score_values = values.detach().cpu().tolist()
        return (
            {unit.unit_id: float(value) for (unit, value) in zip(units, score_values)},
            visual_token_count,
            math.ceil(len(units) / self.retrieval_score_batch_size),
        )

    def _parallel_novelty_scores(
        self,
        units: list[MemoryUnit],
        relevance: dict[int, float],
        all_history: list[MemoryUnit],
    ) -> dict[int, float]:
        if not units:
            return {}
        global_raw = torch.tensor(
            [relevance[unit.unit_id] for unit in all_history], dtype=torch.float32
        )
        normalized_by_id = {
            unit.unit_id: value
            for (unit, value) in zip(all_history, _minmax(global_raw))
        }
        descriptors = torch.stack(
            [
                (
                    unit.descriptor.float()
                    if unit.descriptor is not None
                    else pooled_descriptor(unit.visual_embeddings)
                )
                for unit in units
            ]
        )
        normalized = torch.stack([normalized_by_id[unit.unit_id] for unit in units]).to(
            descriptors.device
        )
        similarities = (descriptors @ descriptors.T + 1.0).mul(0.5).clamp(0, 1)
        novelty = torch.ones(len(units), dtype=torch.float32, device=descriptors.device)
        for index in range(1, len(units)):
            novelty[index] = 1.0 - similarities[index, :index].amax()
        combined = (
            self.relevance_weight * normalized + (1.0 - self.relevance_weight) * novelty
        )
        combined_values = combined.detach().cpu().tolist()
        return {
            unit.unit_id: float(value) for (unit, value) in zip(units, combined_values)
        }

    def _append_archive(self, unit: MemoryUnit) -> None:
        self._archive.append(unit)
        self._archived_kv_bytes += int(unit.kv_bytes)
        self._archived_visual_bytes += unit_visual_bytes(unit)

    def _enforce_archive_limits(
        self, reference_timestamp_seconds: float
    ) -> list[MemoryUnit]:
        """Evict oldest whole units using only counters and timestamps."""
        removed: list[MemoryUnit] = []
        evictions: list[ArchiveEviction] = []
        while self._archive:
            oldest = self._archive[0]
            reasons: list[str] = []
            if (
                reference_timestamp_seconds - oldest.timestamp_seconds
                >= self.archive_retention_seconds
            ):
                reasons.append("time")
            if (
                self.archive_memory_budget_bytes is not None
                and self.archived_total_bytes > self.archive_memory_budget_bytes
            ):
                reasons.append("bytes")
            if (
                self.max_archived_units is not None
                and len(self._archive) > self.max_archived_units
            ):
                reasons.append("count")
            if not reasons:
                break
            victim = self._archive.popleft()
            visual_bytes = unit_visual_bytes(victim)
            payload_bytes = int(victim.kv_bytes) + visual_bytes
            self._archived_kv_bytes -= int(victim.kv_bytes)
            self._archived_visual_bytes -= visual_bytes
            self._resident_unit_ids.remove(victim.unit_id)
            self._dropped_unit_ids.append(victim.unit_id)
            removed.append(victim)
            evictions.append(
                ArchiveEviction(
                    unit_id=victim.unit_id,
                    timestamp_seconds=victim.timestamp_seconds,
                    kv_bytes=int(victim.kv_bytes),
                    visual_bytes=visual_bytes,
                    payload_bytes=payload_bytes,
                    reasons=tuple(reasons),
                )
            )
        self._last_archive_evictions = tuple(evictions)
        if self._archived_kv_bytes < 0 or self._archived_visual_bytes < 0:
            raise RuntimeError("archive byte accounting became negative")
        return removed


def _minmax(values: torch.Tensor) -> torch.Tensor:
    if values.numel() <= 1:
        return torch.ones_like(values, dtype=torch.float32)
    (low, high) = (values.amin(), values.amax())
    if float((high - low).abs()) <= 1e-12:
        return torch.ones_like(values, dtype=torch.float32)
    return (values - low) / (high - low)
