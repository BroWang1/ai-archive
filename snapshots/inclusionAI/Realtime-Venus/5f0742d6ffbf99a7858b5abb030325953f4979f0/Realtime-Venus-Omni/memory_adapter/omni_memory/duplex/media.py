# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Dependency-light media payload shared by live and answer-only paths."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class MediaWrite:
    """One timestamped media unit submitted to a model execution branch."""

    timestamp_seconds: float
    frame: Any | None
    audio_waveform: Any | None
    monotonic_time: float


__all__ = ["MediaWrite"]
