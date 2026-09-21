# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Snapshot the input audio frontend when live and Query share one model.

Only a new branch deep-copies encoder KV. Context switches exchange branch-owned
KV references and use the processor's public Mel snapshot/restore interface.
TTS and token2wav output state are outside this module's isolation scope.
"""

from __future__ import annotations
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

_AUDIO_INPUT_ATTRIBUTES = ("audio_chunk_idx", "audio_buffer", "input_audio_buffer")


@dataclass
class InputAudioState:
    """Owned encoder KV, Mel snapshot and matching frontend counters/buffers."""

    model_attributes: dict[str, Any]
    duplex_attributes: dict[str, Any]
    processor_snapshot: dict[str, Any]


def capture_input_audio_state(duplex: Any, *, clone: bool = False) -> InputAudioState:
    """Capture input state; ``clone=True`` forks independent mutable KV/buffers."""
    if not isinstance(clone, bool):
        raise TypeError("input audio state clone must be a boolean")
    processor = duplex.processor
    snapshotter = getattr(processor, "get_streaming_snapshot", None)
    restorer = getattr(processor, "restore_streaming_snapshot", None)
    if not callable(snapshotter) or not callable(restorer):
        raise RuntimeError(
            "Query input audio isolation requires processor.get_streaming_snapshot() and restore_streaming_snapshot(); load the matching model processor"
        )
    snapshot = snapshotter()
    if not isinstance(snapshot, dict):
        raise TypeError("processor.get_streaming_snapshot() must return a dictionary")
    model_attributes = (
        {"audio_past_key_values": duplex.model.audio_past_key_values}
        if hasattr(duplex.model, "audio_past_key_values")
        else {}
    )
    duplex_attributes = {
        name: getattr(duplex, name)
        for name in _AUDIO_INPUT_ATTRIBUTES
        if hasattr(duplex, name)
    }
    return InputAudioState(
        model_attributes=deepcopy(model_attributes) if clone else model_attributes,
        duplex_attributes=deepcopy(duplex_attributes) if clone else duplex_attributes,
        processor_snapshot=snapshot,
    )


def restore_input_audio_state(duplex: Any, state: InputAudioState) -> None:
    """Install one frontend state; the Mel restore copies its buffer."""
    if not isinstance(state, InputAudioState):
        raise TypeError("input audio state must be InputAudioState")
    _restore_attributes(
        duplex.model, state.model_attributes, ("audio_past_key_values",)
    )
    _restore_attributes(duplex, state.duplex_attributes, _AUDIO_INPUT_ATTRIBUTES)
    duplex.processor.restore_streaming_snapshot(state.processor_snapshot)


def _restore_attributes(
    target: Any, values: dict[str, Any], names: tuple[str, ...]
) -> None:
    for name in names:
        if name in values:
            setattr(target, name, values[name])
        elif hasattr(target, name):
            delattr(target, name)
