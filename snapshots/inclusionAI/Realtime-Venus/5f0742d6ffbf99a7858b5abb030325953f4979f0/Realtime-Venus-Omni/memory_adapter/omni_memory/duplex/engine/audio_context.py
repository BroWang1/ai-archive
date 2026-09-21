# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Audio-only neighbour selection for Memory queries."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Iterable, Sequence


@dataclass(frozen=True)
class AudioKVBlock:
    """One audio-only KV slice captured from a Duplex media unit."""

    source_unit_id: int
    timestamp_seconds: float
    interval_start_seconds: float
    interval_end_seconds: float
    kv_cache: Any
    kv_bytes: int
    token_count: int
    kv_source_start: int
    kv_source_end: int
    kv_capture_local_start: int
    kv_capture_local_end: int


@dataclass(frozen=True)
class AudioAssemblyUnit:
    """Minimal unit interface consumed by the existing KV assembler."""

    unit_id: int
    source_unit_id: int
    timestamp_seconds: float
    kv_cache: Any
    kv_bytes: int
    kv_source_start: int
    kv_source_end: int
    kv_capture_local_start: int
    kv_capture_local_end: int


@dataclass(frozen=True)
class AudioWindowSelection:
    """Deduplicated audio-only neighbours around frozen visual anchors."""

    anchor_unit_ids: tuple[int, ...]
    matched_block_ids: tuple[int, ...]
    duplicate_full_unit_ids: tuple[int, ...]
    added_blocks: tuple[AudioKVBlock, ...]

    @property
    def added_block_ids(self) -> tuple[int, ...]:
        return tuple((block.source_unit_id for block in self.added_blocks))

    @property
    def added_token_count(self) -> int:
        return sum((block.token_count for block in self.added_blocks))

    @property
    def added_kv_bytes(self) -> int:
        return sum((block.kv_bytes for block in self.added_blocks))


def locate_audio_span(
    schema: Sequence[Any], *, expected_token_count: int
) -> tuple[int, int]:
    """Locate the sole ``("audio", token_count)`` schema span.

    Scalar schema entries consume one cache position; modality tuples consume
    their declared token count.  The full schema must exactly cover the media
    prefill cache delta so stale or malformed state fails loudly.
    """
    if expected_token_count <= 0:
        raise ValueError("expected_token_count must be positive")
    cursor = 0
    audio_spans: list[tuple[int, int]] = []
    for index, item in enumerate(schema):
        if isinstance(item, bool):
            raise ValueError(f"schema item {index} cannot be boolean")
        if isinstance(item, int):
            width = 1
        elif isinstance(item, (tuple, list)) and len(item) == 2:
            (kind, raw_width) = item
            if not isinstance(kind, str) or not kind:
                raise ValueError(f"schema item {index} has invalid modality")
            if isinstance(raw_width, bool) or not isinstance(raw_width, int):
                raise ValueError(f"schema item {index} has invalid token count")
            width = int(raw_width)
            if width <= 0:
                raise ValueError(f"schema item {index} token count must be positive")
            if kind == "audio":
                audio_spans.append((cursor, cursor + width))
        else:
            raise ValueError(f"unsupported schema item {index}: {item!r}")
        cursor += width
    if cursor != expected_token_count:
        raise ValueError(
            f"prefill schema/cache length mismatch: schema={cursor}, cache_delta={expected_token_count}"
        )
    if len(audio_spans) != 1:
        raise ValueError(
            f"expected exactly one audio span in media prefill schema, got {len(audio_spans)}"
        )
    return audio_spans[0]


def select_audio_neighbours(
    *,
    anchor_units: Sequence[Any],
    full_units: Sequence[Any],
    blocks: Iterable[AudioKVBlock],
    context_seconds: float,
) -> AudioWindowSelection:
    """Select audio blocks intersecting +/- context around history anchors."""
    if context_seconds < 0:
        raise ValueError("context_seconds must be nonnegative")
    anchors = tuple(sorted(anchor_units, key=lambda unit: unit.unit_id))
    full_ids = {int(unit.unit_id) for unit in full_units}
    matched: list[AudioKVBlock] = []
    for block in sorted(
        blocks, key=lambda item: (item.timestamp_seconds, item.source_unit_id)
    ):
        if any(
            (
                block.interval_end_seconds > anchor.timestamp_seconds - context_seconds
                and block.interval_start_seconds
                < anchor.timestamp_seconds + context_seconds
                for anchor in anchors
            )
        ):
            matched.append(block)
    duplicates = tuple(
        (block.source_unit_id for block in matched if block.source_unit_id in full_ids)
    )
    added = tuple((block for block in matched if block.source_unit_id not in full_ids))
    return AudioWindowSelection(
        anchor_unit_ids=tuple((int(unit.unit_id) for unit in anchors)),
        matched_block_ids=tuple((block.source_unit_id for block in matched)),
        duplicate_full_unit_ids=duplicates,
        added_blocks=added,
    )


def as_assembly_units(
    blocks: Sequence[AudioKVBlock], *, synthetic_id_base: int = 1000000000
) -> tuple[AudioAssemblyUnit, ...]:
    """Convert selected audio slices into KV-cache assembly units."""
    return tuple(
        (
            AudioAssemblyUnit(
                unit_id=synthetic_id_base + block.source_unit_id,
                source_unit_id=block.source_unit_id,
                timestamp_seconds=block.timestamp_seconds,
                kv_cache=block.kv_cache,
                kv_bytes=block.kv_bytes,
                kv_source_start=block.kv_source_start,
                kv_source_end=block.kv_source_end,
                kv_capture_local_start=block.kv_capture_local_start,
                kv_capture_local_end=block.kv_capture_local_end,
            )
            for block in blocks
        )
    )
