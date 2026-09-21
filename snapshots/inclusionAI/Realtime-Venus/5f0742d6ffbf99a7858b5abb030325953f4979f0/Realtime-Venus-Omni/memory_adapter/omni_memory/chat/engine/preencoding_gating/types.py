# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Typed records for predictive-cost gating."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Literal
from ..data.sampling import SampledFrame

FrameRole = Literal["I", "P"]
FrameAction = Literal["KEEP", "DROP"]


@dataclass(frozen=True)
class GatingMetrics:
    """Decision-independent predictive statistics for one adjacent frame pair."""

    search_radius: int
    pcost: float
    residual_mean: float
    residual_p99: float
    residual_max: float
    changed_block_fraction: float
    motion_mean: float
    block_count: int
    residual_quantile: float = 0.99

    @property
    def residual_quantile_value(self) -> float:
        """Return the residual at the configured quantile used by the guard."""
        return self.residual_p99


@dataclass(frozen=True)
class GatingDecision:
    """A reversible candidate mapping and its immutable KEEP/DROP decision."""

    candidate_ordinal: int
    sampled_frame: SampledFrame
    reference_candidate_ordinal: int | None
    metrics: GatingMetrics | None
    gop_role: FrameRole
    action: FrameAction
    reason_codes: tuple[str, ...]
    gop_index: int
    position_in_gop: int
    p_frames_in_gop: int
    consecutive_drops: int
    encoded_ordinal: int | None

    @property
    def keep(self) -> bool:
        """Whether this candidate is passed to the visual processor."""
        return self.action == "KEEP"
