# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Stable public data contracts for Omni Memory runtimes."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any


def _finite_seconds(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


@dataclass(frozen=True)
class MediaChunk:
    """One already sampled, chronological media unit.

    Intervals use the half-open convention ``[start_seconds, end_seconds)``.
    Each chunk contains at most one sampled frame. Emit additional chunks
    for multiple visual observations within an interval.
    """

    sequence_number: int
    start_seconds: float
    end_seconds: float
    frames: tuple[Any, ...] = ()
    audio_waveform: Any | None = None
    is_final: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.sequence_number, bool)
            or not isinstance(self.sequence_number, int)
            or self.sequence_number < 0
        ):
            raise ValueError("sequence_number must be a nonnegative integer")
        start = _finite_seconds(self.start_seconds, "start_seconds")
        end = _finite_seconds(self.end_seconds, "end_seconds")
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        if not isinstance(self.frames, tuple):
            raise TypeError("frames must be a tuple")
        if len(self.frames) > 1:
            raise ValueError(
                "one MediaChunk may contain at most one production frame; emit additional chunks instead of hiding a second sampler"
            )
        if not isinstance(self.is_final, bool):
            raise TypeError("is_final must be boolean")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)


@dataclass(frozen=True)
class Question:
    """One explicit text retrieval request."""

    query_id: str
    text: str
    timestamp_seconds: float | None = None
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.query_id, str) or not self.query_id.strip():
            raise ValueError("query_id must be a non-empty string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a non-empty string")
        if self.timestamp_seconds is not None:
            object.__setattr__(
                self,
                "timestamp_seconds",
                _finite_seconds(self.timestamp_seconds, "timestamp_seconds"),
            )
        if not isinstance(self.options, tuple) or any(
            (not isinstance(item, str) or not item.strip() for item in self.options)
        ):
            raise ValueError("options must be a tuple of non-empty strings")

    @property
    def retrieval_text(self) -> str:
        """Return the exact user-visible query text, including choices."""
        if not self.options:
            return self.text
        return "\n".join((self.text, *self.options))


@dataclass(frozen=True)
class Answer:
    """Answer returned by a memory runtime."""

    query_id: str
    text: str
    mode: str
    memory_used: bool
    memory_enabled: bool | None = None
    answer_type: str = "explicit_question"
    timestamp_seconds: float | None = None
    is_listen: bool | None = None
    end_of_turn: bool | None = None
    termination_reason: str | None = None
    audio_waveform: Any | None = field(default=None, repr=False, compare=False)
    raw: Any | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.mode not in {"chat", "duplex"}:
            raise ValueError("mode must be chat or duplex")
        if not isinstance(self.memory_used, bool):
            raise TypeError("memory_used must be boolean")
        if self.memory_enabled is None:
            object.__setattr__(self, "memory_enabled", self.memory_used)
        elif not isinstance(self.memory_enabled, bool):
            raise TypeError("memory_enabled must be boolean")
        if self.answer_type not in {"explicit_question", "proactive"}:
            raise ValueError("answer_type must be explicit_question or proactive")
        if self.is_listen is not None and (not isinstance(self.is_listen, bool)):
            raise TypeError("is_listen must be boolean or None")
        if self.end_of_turn is not None and (not isinstance(self.end_of_turn, bool)):
            raise TypeError("end_of_turn must be boolean or None")
        if self.termination_reason is not None and (
            not isinstance(self.termination_reason, str)
            or not self.termination_reason.strip()
        ):
            raise ValueError("termination_reason must be a non-empty string or None")
        if self.timestamp_seconds is not None:
            object.__setattr__(
                self,
                "timestamp_seconds",
                _finite_seconds(self.timestamp_seconds, "timestamp_seconds"),
            )

    def to_record(self) -> dict[str, object]:
        """Return the bounded JSON result; tensors and waveforms stay out."""
        return {
            "query_id": self.query_id,
            "text": self.text,
            "mode": self.mode,
            "memory_enabled": self.memory_enabled,
            "memory_used": self.memory_used,
            "answer_type": self.answer_type,
            "timestamp_seconds": self.timestamp_seconds,
            "is_listen": self.is_listen,
            "end_of_turn": self.end_of_turn,
            "termination_reason": self.termination_reason,
            "has_audio": self.audio_waveform is not None,
        }
