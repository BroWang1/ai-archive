# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Stateful single-pass form of the frozen Chat PCost decision policy."""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass
from typing import Any, Mapping
import numpy as np
from ..config import ChatMemoryConfig
from .engine.data.sampling import SampledFrame
from .engine.preencoding_gating.decision import _choose_action, _settings
from .engine.preencoding_gating.matching import match_rgb_pair
from .engine.preencoding_gating.types import GatingDecision, GatingMetrics


@dataclass(frozen=True)
class CommittedCandidate:
    decision: GatingDecision
    frame: Any


@dataclass(frozen=True)
class _PendingCandidate:
    sampled_frame: SampledFrame
    frame: Any
    rgb: np.ndarray
    metrics: GatingMetrics | None


class StreamingPCostGate:
    """Delay four candidates so end-of-stream protection stays exact."""

    def __init__(self, config: ChatMemoryConfig) -> None:
        self.matching = config.pcost_matching.to_engine_mapping()
        self.decision = config.pcost_decision.to_engine_mapping()
        residual = self.decision["residual_p99_guard"]
        assert isinstance(residual, Mapping)
        self.matching_runtime = {
            **self.matching,
            "residual_quantile": residual.get("quantile", 0.99),
        }
        self.settings = _settings(self.decision)
        self.protect_recent = int(self.settings["protect_recent_frames"])
        self._pending: deque[_PendingCandidate] = deque()
        self._previous_rgb: np.ndarray | None = None
        self._next_ordinal = 0
        self._gop_index = -1
        self._p_frames = 0
        self._consecutive_drops = 0
        self._encoded_ordinal = 0
        self._closed = False
        self.decisions: list[GatingDecision] = []

    def push(
        self, *, frame: Any, timestamp_seconds: float, source_frame_index: int
    ) -> tuple[CommittedCandidate, ...]:
        if self._closed:
            raise RuntimeError("cannot push a frame after PCost finalization")
        rgb = _as_rgb(frame)
        metric = None
        if self._previous_rgb is not None and self._previous_rgb.shape == rgb.shape:
            metric = match_rgb_pair(rgb, self._previous_rgb, self.matching_runtime)
        sampled = SampledFrame(
            ordinal=self._next_ordinal,
            source_frame_index=source_frame_index,
            target_timestamp_seconds=float(timestamp_seconds),
            decoded_timestamp_seconds=float(timestamp_seconds),
            sampling_reason="external_stream",
        )
        self._pending.append(
            _PendingCandidate(
                sampled_frame=sampled, frame=frame, rgb=rgb, metrics=metric
            )
        )
        self._previous_rgb = rgb
        self._next_ordinal += 1
        if len(self._pending) <= self.protect_recent:
            return ()
        return (self._commit(self._pending.popleft(), recent=False),)

    def finalize(self) -> tuple[CommittedCandidate, ...]:
        if self._closed:
            raise RuntimeError("PCost gate is already finalized")
        self._closed = True
        committed = tuple(
            (self._commit(item, recent=True) for item in tuple(self._pending))
        )
        self._pending.clear()
        if not self.decisions:
            raise ValueError("media contains no visual candidates")
        if not any((item.keep for item in self.decisions)):
            raise RuntimeError("PCost removed every visual candidate")
        return committed

    def _commit(self, item: _PendingCandidate, *, recent: bool) -> CommittedCandidate:
        ordinal = item.sampled_frame.ordinal
        recent_start = ordinal if recent else ordinal + 1
        (role, action, reasons, p99_block, changed_block) = _choose_action(
            ordinal=ordinal,
            total_candidates=self._next_ordinal,
            recent_start=recent_start,
            metric=item.metrics,
            p_frames_in_gop=self._p_frames,
            consecutive_drops=self._consecutive_drops,
            settings=self.settings,
        )
        if role == "I":
            self._gop_index += 1
            self._p_frames = 0
            self._consecutive_drops = 0
            position = 0
        else:
            self._p_frames += 1
            position = self._p_frames
            if action == "DROP":
                self._consecutive_drops += 1
            else:
                self._consecutive_drops = 0
        encoded = self._encoded_ordinal if action == "KEEP" else None
        if encoded is not None:
            self._encoded_ordinal += 1
        decision = GatingDecision(
            candidate_ordinal=ordinal,
            sampled_frame=item.sampled_frame,
            reference_candidate_ordinal=ordinal - 1 if ordinal else None,
            metrics=item.metrics,
            gop_role=role,
            action=action,
            reason_codes=reasons,
            gop_index=self._gop_index,
            position_in_gop=position,
            p_frames_in_gop=self._p_frames,
            consecutive_drops=self._consecutive_drops,
            encoded_ordinal=encoded,
        )
        self.decisions.append(decision)
        return CommittedCandidate(decision=decision, frame=item.frame)


def _as_rgb(frame: Any) -> np.ndarray:
    if hasattr(frame, "convert"):
        frame = frame.convert("RGB")
    value = np.asarray(frame)
    if value.ndim != 3 or value.shape[-1] != 3:
        raise ValueError("visual frame must have RGB shape [H,W,3]")
    if value.dtype != np.uint8:
        if not np.issubdtype(value.dtype, np.number):
            raise TypeError("visual frame must contain numeric RGB values")
        if not np.isfinite(value).all() or value.min() < 0 or value.max() > 255:
            raise ValueError("visual frame values must be finite and in [0,255]")
        value = value.astype(np.uint8)
    return np.ascontiguousarray(value)
