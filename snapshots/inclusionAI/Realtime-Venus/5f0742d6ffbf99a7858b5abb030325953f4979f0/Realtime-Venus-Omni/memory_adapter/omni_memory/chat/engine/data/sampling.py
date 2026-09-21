# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Deterministic full-video frame sampling and reusable manifests."""

from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SampledFrame:
    """One visual frame selected from the target-FPS candidate timeline."""

    ordinal: int
    source_frame_index: int
    target_timestamp_seconds: float
    decoded_timestamp_seconds: float
    sampling_reason: str

    @property
    def timestamp_seconds(self) -> float:
        """Compatibility alias for the actual source-frame timestamp."""
        return self.decoded_timestamp_seconds
