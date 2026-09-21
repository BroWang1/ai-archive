# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Two-phase Duplex adapter for proactive output plus Memory capture."""

from __future__ import annotations
import math
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Mapping, Sequence
from .engine.audio_context import locate_audio_span
from .engine.kv_cache import slice_kv_cache
from .engine.model_adapter import (
    EncodedDuplexUnit,
    RealtimeVenusOmniDuplexAdapter,
    _capture_method_output,
    _flatten_visual_embeddings,
)


@dataclass(frozen=True)
class PendingDuplexMedia:
    """Artifacts known after prefill but before generation."""

    unit_id: int
    timestamp_seconds: float
    local_start: int
    timeline_start: int
    prefill_local_end: int
    captured_vision: tuple[Any, ...]
    visual_frame_count: int
    capture_memory_artifacts: bool
    audio_local_start: int | None
    audio_local_end: int | None


class DuplexMemoryAdapter(RealtimeVenusOmniDuplexAdapter):
    """Capture memory artifacts for one prefill and generation cycle."""

    def begin_media_prefill(
        self,
        *,
        timestamp_seconds: float,
        frame_list: Sequence[Any] | None,
        audio_waveform: Any | None,
        text_list: Sequence[Any] | None = None,
        max_slice_nums: Any = 1,
        batch_vision_feed: bool = False,
        capture_memory_artifacts: bool = True,
        capture_audio_artifacts: bool = False,
    ) -> tuple[PendingDuplexMedia, dict[str, Any]]:
        """Run prefill exactly once and retain only capture metadata."""
        timestamp = _timestamp(timestamp_seconds)
        if (
            self._live_media_timestamps
            and timestamp < self._live_media_timestamps[-1][1]
        ):
            raise ValueError("media timestamps must be nondecreasing")
        if not isinstance(batch_vision_feed, bool):
            raise TypeError("batch_vision_feed must be a boolean")
        local_start = self.cache_length()
        timeline_start = self._absolute_cache_position(local_start)
        captured_vision: list[Any] = []
        capture_context = (
            _capture_method_output(
                self.duplex.model, "get_vision_embedding", captured_vision
            )
            if capture_memory_artifacts
            else nullcontext()
        )
        with capture_context:
            raw_result = self.duplex.streaming_prefill(
                audio_waveform=audio_waveform,
                frame_list=list(frame_list) if frame_list else None,
                text_list=list(text_list) if text_list else None,
                max_slice_nums=max_slice_nums,
                batch_vision_feed=batch_vision_feed,
            )
        if not isinstance(raw_result, Mapping) or raw_result.get("success") is not True:
            reason = (
                raw_result.get("reason")
                if isinstance(raw_result, Mapping)
                else raw_result
            )
            raise RuntimeError(f"Realtime-Venus-Omni streaming_prefill failed: {reason}")
        result = dict(raw_result)
        prefill_local_end = self.cache_length()
        if prefill_local_end <= local_start:
            raise RuntimeError("Duplex prefill did not append media K/V tokens")
        audio_local_start: int | None = None
        audio_local_end: int | None = None
        if capture_audio_artifacts and audio_waveform is not None:
            schemas = getattr(self.duplex, "prefill_schema_tokens", None)
            if not isinstance(schemas, (list, tuple)) or not schemas:
                raise RuntimeError(
                    "audio context capture requires official prefill_schema_tokens"
                )
            schema = schemas[-1]
            if not isinstance(schema, (list, tuple)):
                raise RuntimeError(
                    "latest official media prefill schema must be a sequence"
                )
            (relative_start, relative_end) = locate_audio_span(
                schema, expected_token_count=prefill_local_end - local_start
            )
            audio_local_start = local_start + relative_start
            audio_local_end = local_start + relative_end
        pending = PendingDuplexMedia(
            unit_id=self._next_unit_id,
            timestamp_seconds=timestamp,
            local_start=local_start,
            timeline_start=timeline_start,
            prefill_local_end=prefill_local_end,
            captured_vision=tuple(captured_vision),
            visual_frame_count=len(tuple(frame_list or ())),
            capture_memory_artifacts=capture_memory_artifacts,
            audio_local_start=audio_local_start,
            audio_local_end=audio_local_end,
        )
        return (pending, result)

    def generate_and_capture_media_unit(
        self, pending: PendingDuplexMedia, **generate_kwargs: Any
    ) -> tuple[EncodedDuplexUnit, dict[str, Any]]:
        """Run generation once, then capture the completed media unit."""
        if pending.unit_id != self._next_unit_id:
            raise RuntimeError("pending Duplex unit no longer matches adapter state")
        raw_result = self.duplex.streaming_generate(**generate_kwargs)
        if not isinstance(raw_result, Mapping):
            raise RuntimeError("Realtime-Venus-Omni streaming_generate must return a mapping")
        result = dict(raw_result)
        local_end = self.cache_length()
        if local_end <= pending.prefill_local_end:
            raise RuntimeError(
                "official streaming_generate did not finalize the Duplex unit"
            )
        unit_cache = (
            slice_kv_cache(self.decoder.cache, pending.local_start, local_end)
            if pending.capture_memory_artifacts
            else None
        )
        visual = _merge_visual_embedding_calls(pending.captured_vision)
        audio_cache = (
            slice_kv_cache(
                self.decoder.cache, pending.audio_local_start, pending.audio_local_end
            )
            if pending.audio_local_start is not None
            and pending.audio_local_end is not None
            else None
        )
        unit = EncodedDuplexUnit(
            unit_id=pending.unit_id,
            timestamp_seconds=pending.timestamp_seconds,
            visual_embeddings=visual,
            visual_frame_count=pending.visual_frame_count,
            unit_cache=unit_cache,
            cache_start=pending.timeline_start,
            cache_end=pending.timeline_start + local_end - pending.local_start,
            capture_local_start=pending.local_start,
            capture_local_end=local_end,
            audio_cache=audio_cache,
            audio_cache_start=(
                None
                if pending.audio_local_start is None
                else pending.timeline_start
                + pending.audio_local_start
                - pending.local_start
            ),
            audio_cache_end=(
                None
                if pending.audio_local_end is None
                else pending.timeline_start
                + pending.audio_local_end
                - pending.local_start
            ),
            audio_capture_local_start=pending.audio_local_start,
            audio_capture_local_end=pending.audio_local_end,
            audio_token_count=(
                0
                if pending.audio_local_start is None or pending.audio_local_end is None
                else pending.audio_local_end - pending.audio_local_start
            ),
        )
        self._live_media_timestamps.append((unit.unit_id, unit.timestamp_seconds))
        self._next_unit_id += 1
        return (unit, result)


def _timestamp(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("timestamp_seconds must be a real number")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError("timestamp_seconds must be finite and nonnegative")
    return result


def _merge_visual_embedding_calls(captured: Sequence[Any]) -> Any | None:
    """Flatten every vision call and preserve its chronological order."""
    flattened = tuple(
        (
            item
            for item in (_flatten_visual_embeddings(value) for value in captured)
            if item is not None
        )
    )
    if not flattened:
        return None
    if len(flattened) == 1:
        return flattened[0]
    try:
        import torch
    except ImportError as error:
        raise RuntimeError(
            "capturing multiple visual batches requires PyTorch"
        ) from error
    return torch.cat(flattened, dim=0)


__all__ = ["DuplexMemoryAdapter", "PendingDuplexMedia"]
