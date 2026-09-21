# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Visual-frame-anchored selection over already encoded audio blocks."""

from __future__ import annotations
import math
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class AudioContextWindow:
    """One clipped history-frame window and its surviving block matches."""

    frame_index: int
    frame_timestamp_seconds: float
    requested_start_seconds: float
    requested_end_seconds: float
    clipped_start_seconds: float
    clipped_end_seconds: float
    matched_block_indices: tuple[int, ...]


@dataclass(frozen=True)
class AudioContextSelection:
    """Deduplicated audio blocks selected from short context and history windows."""

    context_seconds: float
    block_selection: str
    short_frame_ids: tuple[int, ...]
    short_block_indices: tuple[int, ...]
    windows: tuple[AudioContextWindow, ...]
    selected_block_indices: tuple[int, ...]
    missing_history_frame_ids: tuple[int, ...]
    duplicate_match_count: int


def select_audio_context(
    *,
    selected_history_frame_ids: Sequence[int],
    included_short_frame_ids: Sequence[int],
    frame_timestamps_seconds: Sequence[float],
    audio_block_start_seconds: Sequence[float],
    audio_block_end_seconds: Sequence[float],
    audio_block_frame_indices: Sequence[int],
    alive_audio_block_indices: Sequence[int],
    effective_duration_seconds: float,
    audio_sample_rate: int,
    context_seconds: float,
    block_selection: str = "any_overlap",
    short_audio_block_indices: Sequence[int] | None = None,
) -> AudioContextSelection:
    """Select retained audio blocks overlapping visual-frame context windows.

    short_audio_block_indices preserves original audio block indices when
    selected visual frames are compacted into a dense retrieval bank.
    When omitted, indices are inferred from the visual frame mapping.
    """
    if block_selection != "any_overlap":
        raise ValueError("block_selection must be any_overlap")
    if (
        isinstance(context_seconds, bool)
        or not isinstance(context_seconds, (int, float))
        or (not math.isfinite(context_seconds))
        or (context_seconds <= 0)
    ):
        raise ValueError("context_seconds must be a finite positive number")
    if (
        isinstance(effective_duration_seconds, bool)
        or not isinstance(effective_duration_seconds, (int, float))
        or (not math.isfinite(effective_duration_seconds))
        or (effective_duration_seconds <= 0)
    ):
        raise ValueError("effective_duration_seconds must be a finite positive number")
    if (
        isinstance(audio_sample_rate, bool)
        or not isinstance(audio_sample_rate, int)
        or audio_sample_rate <= 0
    ):
        raise ValueError("audio_sample_rate must be a positive integer")
    effective_audio_samples = effective_duration_seconds * audio_sample_rate
    if not math.isfinite(effective_audio_samples):
        raise ValueError("effective duration is too large for the audio sample rate")
    maximum_audio_end_seconds = math.ceil(effective_audio_samples) / audio_sample_rate
    maximum_audio_end_tolerance = math.ulp(maximum_audio_end_seconds)
    frame_timestamps = tuple((float(value) for value in frame_timestamps_seconds))
    if not frame_timestamps or any(
        (
            not math.isfinite(value) or value < 0 or value >= effective_duration_seconds
            for value in frame_timestamps
        )
    ):
        raise ValueError("frame timestamps must be finite and inside visible media")
    starts = tuple((float(value) for value in audio_block_start_seconds))
    ends = tuple((float(value) for value in audio_block_end_seconds))
    frame_indices = tuple(audio_block_frame_indices)
    if not len(starts) == len(ends) == len(frame_indices):
        raise ValueError("audio block metadata must have equal lengths")
    previous_end = 0.0
    for block_index, (start, end, frame_index) in enumerate(
        zip(starts, ends, frame_indices)
    ):
        if (
            not math.isfinite(start)
            or not math.isfinite(end)
            or start < 0
            or (end <= start)
            or (end > maximum_audio_end_seconds + maximum_audio_end_tolerance)
        ):
            raise ValueError(
                f"audio block {block_index} has invalid time bounds: start={start}, end={end}, effective_duration={effective_duration_seconds}, maximum_sample_aligned_end={maximum_audio_end_seconds}, sample_rate={audio_sample_rate}"
            )
        if block_index > 0 and start < previous_end - 1e-06:
            raise ValueError("audio blocks must be sorted and non-overlapping")
        if (
            isinstance(frame_index, bool)
            or not isinstance(frame_index, int)
            or frame_index < 0
        ):
            raise ValueError(f"audio block {block_index} has invalid frame index")
        if short_audio_block_indices is None and frame_index >= len(frame_timestamps):
            raise ValueError(f"audio block {block_index} has invalid frame index")
        previous_end = end
    alive = tuple(alive_audio_block_indices)
    if tuple(sorted(set(alive))) != alive or any(
        (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or (index >= len(starts))
            for index in alive
        )
    ):
        raise ValueError(
            "alive audio block indices must be unique, sorted, and in range"
        )
    history = _validate_frame_ids(
        selected_history_frame_ids, len(frame_timestamps), "history"
    )
    short = _validate_frame_ids(
        included_short_frame_ids, len(frame_timestamps), "short"
    )
    if set(history).intersection(short):
        raise ValueError("history and short frame ids must be disjoint")
    alive_set = set(alive)
    short_set = set(short)
    if short_audio_block_indices is None:
        short_blocks = tuple(
            (
                index
                for (index, frame_index) in enumerate(frame_indices)
                if index in alive_set and frame_index in short_set
            )
        )
    else:
        requested_short_blocks = tuple(short_audio_block_indices)
        if tuple(sorted(set(requested_short_blocks))) != requested_short_blocks or any(
            (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or (index >= len(starts))
                for index in requested_short_blocks
            )
        ):
            raise ValueError(
                "short audio block indices must be unique, sorted, and in range"
            )
        short_blocks = tuple(
            (index for index in requested_short_blocks if index in alive_set)
        )
    windows: list[AudioContextWindow] = []
    missing: list[int] = []
    all_matches: list[int] = list(short_blocks)
    for frame_index in history:
        timestamp = frame_timestamps[frame_index]
        requested_start = timestamp - float(context_seconds)
        requested_end = timestamp + float(context_seconds)
        clipped_start = max(0.0, requested_start)
        clipped_end = min(float(effective_duration_seconds), requested_end)
        matches = tuple(
            (
                block_index
                for block_index in alive
                if starts[block_index] < clipped_end
                and ends[block_index] > clipped_start
            )
        )
        if not matches:
            missing.append(frame_index)
        all_matches.extend(matches)
        windows.append(
            AudioContextWindow(
                frame_index=frame_index,
                frame_timestamp_seconds=timestamp,
                requested_start_seconds=requested_start,
                requested_end_seconds=requested_end,
                clipped_start_seconds=clipped_start,
                clipped_end_seconds=clipped_end,
                matched_block_indices=matches,
            )
        )
    selected = tuple(sorted(set(all_matches)))
    return AudioContextSelection(
        context_seconds=float(context_seconds),
        block_selection=block_selection,
        short_frame_ids=short,
        short_block_indices=short_blocks,
        windows=tuple(windows),
        selected_block_indices=selected,
        missing_history_frame_ids=tuple(missing),
        duplicate_match_count=len(all_matches) - len(selected),
    )


def _validate_frame_ids(
    values: Sequence[int], frame_count: int, name: str
) -> tuple[int, ...]:
    result = tuple(values)
    if tuple(sorted(set(result))) != result or any(
        (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or (index >= frame_count)
            for index in result
        )
    ):
        raise ValueError(f"{name} frame ids must be unique, sorted, and in range")
    return result
