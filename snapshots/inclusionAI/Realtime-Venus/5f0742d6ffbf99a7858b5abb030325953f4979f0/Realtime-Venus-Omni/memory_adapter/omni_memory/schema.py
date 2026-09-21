# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Public input and output contracts for memory-enabled model sessions."""

from __future__ import annotations
from dataclasses import dataclass, field
import math
from typing import Any

_MULTIPLE_CHOICE_INSTRUCTION = "Select the best answer from the options above. Directly provide the letter representing your choice and nothing else. Do not include the full text of the option, do not provide any explanation."


def _seconds(value: object, name: str) -> float:
    """Return a finite nonnegative time value."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError(f"{name} must be finite and nonnegative")
    return result


@dataclass(frozen=True)
class MediaChunk:
    """Represent one chronological audio/video interval supplied by the caller.

    ``frames`` contains zero or more RGB image objects in chronological order.
    ``frame_timestamps_seconds`` gives their source-media timestamps.  If it is
    omitted, timestamps are distributed uniformly through the half-open chunk
    interval.  ``audio_waveform`` is one-dimensional 16 kHz mono float32 PCM.
    """

    sequence_number: int
    start_seconds: float
    end_seconds: float
    frames: tuple[Any, ...] = ()
    frame_timestamps_seconds: tuple[float, ...] = ()
    audio_waveform: Any | None = field(default=None, repr=False, compare=False)
    is_final: bool = False

    def __post_init__(self) -> None:
        """Normalize timestamps and reject malformed media boundaries."""
        if (
            isinstance(self.sequence_number, bool)
            or not isinstance(self.sequence_number, int)
            or self.sequence_number < 0
        ):
            raise ValueError("sequence_number must be a nonnegative integer")
        start = _seconds(self.start_seconds, "start_seconds")
        end = _seconds(self.end_seconds, "end_seconds")
        if end <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        if not isinstance(self.frames, tuple):
            raise TypeError("frames must be a tuple")
        if not isinstance(self.frame_timestamps_seconds, tuple):
            raise TypeError("frame_timestamps_seconds must be a tuple")
        timestamps = self.frame_timestamps_seconds
        if timestamps and len(timestamps) != len(self.frames):
            raise ValueError("frame timestamps must align one-to-one with frames")
        if not timestamps and self.frames:
            step = (end - start) / len(self.frames)
            timestamps = tuple(
                (start + step * index for index in range(len(self.frames)))
            )
        normalized = tuple((_seconds(item, "frame timestamp") for item in timestamps))
        if any((item < start or item >= end for item in normalized)):
            raise ValueError("every frame timestamp must lie inside the chunk interval")
        if any((right <= left for (left, right) in zip(normalized, normalized[1:]))):
            raise ValueError("frame timestamps must be strictly increasing")
        if not isinstance(self.is_final, bool):
            raise TypeError("is_final must be boolean")
        if self.audio_waveform is not None:
            ndim = getattr(self.audio_waveform, "ndim", None)
            if ndim is not None and int(ndim) != 1:
                raise ValueError("audio_waveform must be one-dimensional mono samples")
        object.__setattr__(self, "start_seconds", start)
        object.__setattr__(self, "end_seconds", end)
        object.__setattr__(self, "frame_timestamps_seconds", normalized)


@dataclass(frozen=True)
class Question:
    """Represent one independent question submitted to a session."""

    query_id: str
    text: str
    timestamp_seconds: float | None = None
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate identity, text, optional choices, and optional stream time."""
        if not isinstance(self.query_id, str) or not self.query_id.strip():
            raise ValueError("query_id must be a non-empty string")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be a non-empty string")
        if self.timestamp_seconds is not None:
            object.__setattr__(
                self,
                "timestamp_seconds",
                _seconds(self.timestamp_seconds, "timestamp_seconds"),
            )
        if not isinstance(self.options, tuple) or any(
            (not isinstance(item, str) or not item.strip() for item in self.options)
        ):
            raise ValueError("options must contain non-empty strings")

    @property
    def model_text(self) -> str:
        """Return the exact question text sent to the model."""
        if not self.options:
            return self.text
        return (
            f"Question: {self.text}\nOptions:\n"
            + "\n".join(self.options)
            + f"\n\n{_MULTIPLE_CHOICE_INSTRUCTION}"
        )

    @property
    def retrieval_text(self) -> str:
        """Return the option-free question used by visual retrieval."""
        return self.text


@dataclass(frozen=True)
class Answer:
    """Return one final text answer and an optional future audio waveform."""

    query_id: str
    text: str
    audio_waveform: Any | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate stable answer fields without imposing semantic correctness."""
        if not isinstance(self.query_id, str) or not self.query_id.strip():
            raise ValueError("query_id must be a non-empty string")
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")

    def to_record(self) -> dict[str, object]:
        """Return the small JSON record written by evaluation scripts."""
        return {
            "query_id": self.query_id,
            "text": self.text,
            "has_audio": self.audio_waveform is not None,
        }


@dataclass(frozen=True)
class MainStreamOutput:
    """Describe the main Duplex decision for one processed chunk."""

    text: str
    is_listen: bool
    end_of_turn: bool
    audio_waveform: Any | None = field(default=None, repr=False, compare=False)


@dataclass(frozen=True)
class QueryAnswerChunk:
    """Describe one incremental chunk produced by a question-answer branch."""

    query_id: str
    chunk_index: int
    text_delta: str
    is_listen: bool
    end_of_turn: bool
    audio_waveform: Any | None = field(default=None, repr=False, compare=False)


__all__ = ["Answer", "MainStreamOutput", "MediaChunk", "QueryAnswerChunk", "Question"]
