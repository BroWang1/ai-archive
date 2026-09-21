# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Question assembly from bounded resident media blocks only."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Mapping
import torch
from ..memory.online_manager import PackedMemorySnapshot
from .sequence_assembler import AssembledInput, assemble_packed_inputs


@dataclass(frozen=True)
class SelectedSaveMemQuestionInput:
    """Sparse SAVEMem question input with original media provenance."""

    assembled: AssembledInput
    original_visual_indices: tuple[int, ...]
    original_audio_indices: tuple[int, ...]
    rendered_prompt: str


def assemble_savemem_question(
    *,
    adapter: object,
    visual_memory: PackedMemorySnapshot,
    selected_visual_frame_ids: tuple[int, ...],
    audio_embeddings: tuple[torch.Tensor, ...],
    audio_start_seconds: tuple[float, ...],
    audio_end_seconds: tuple[float, ...],
    selected_audio_indices: tuple[int, ...],
    prompt: str,
    reserved_generation_tokens: int,
    prompt_context: Mapping[str, Any] | None = None,
) -> SelectedSaveMemQuestionInput:
    """Assemble only selected packed visual rows and selected audio blocks."""
    by_frame = {frame.frame_index: frame for frame in visual_memory.frames}
    if tuple(sorted(set(selected_visual_frame_ids))) != selected_visual_frame_ids:
        raise ValueError("selected visual frame ids must be unique and sorted")
    if tuple(sorted(set(selected_audio_indices))) != selected_audio_indices:
        raise ValueError("selected audio indices must be unique and sorted")
    try:
        visual = tuple((by_frame[index] for index in selected_visual_frame_ids))
    except KeyError as error:
        raise ValueError(
            f"selected visual frame is not resident: {error.args[0]}"
        ) from error
    if not len(audio_embeddings) == len(audio_start_seconds) == len(audio_end_seconds):
        raise ValueError("audio embeddings and time bounds must align")
    if any(
        (
            index < 0 or index >= len(audio_embeddings)
            for index in selected_audio_indices
        )
    ):
        raise ValueError("selected audio index is out of range")
    events: list[tuple[float, int, str]] = []
    events.extend(
        (
            (float(frame.timestamp_seconds), 0, f"v:{frame.frame_index}")
            for frame in visual
        )
    )
    events.extend(
        (
            (float(audio_start_seconds[index]), 1, f"a:{index}")
            for index in selected_audio_indices
        )
    )
    events.sort(key=lambda item: (item[0], item[1], item[2]))
    modalities = tuple(
        ("visual" if label.startswith("v:") else "audio" for (_, _, label) in events)
    )
    if not modalities:
        raise RuntimeError("SAVEMem selection retained no media")
    selected_audio = tuple(
        (audio_embeddings[index] for index in selected_audio_indices)
    )
    visual_frames = tuple(((frame.token_indices, frame.embeddings) for frame in visual))
    if prompt_context is None:
        canonical = adapter.prepare_selected_canonical(
            modalities=modalities,
            audio_token_counts=tuple((int(item.shape[0]) for item in selected_audio)),
            prompt=prompt,
        )
        final_visual_frames = visual_frames
        final_audio_embeddings = selected_audio
        rendered_prompt = prompt
    else:
        prepared = adapter.prepare_selected_conversation(
            modalities=modalities,
            memory_visual_frames=visual_frames,
            memory_audio_embeddings=selected_audio,
            prompt=prompt,
            prompt_context=prompt_context,
        )
        canonical = prepared.canonical
        final_visual_frames = prepared.visual_frames
        final_audio_embeddings = prepared.audio_embeddings
        rendered_prompt = prepared.rendered_prompt
    assembled = assemble_packed_inputs(
        canonical,
        adapter.text_embedding_layer(),
        final_visual_frames,
        final_audio_embeddings,
        tuple(range(len(final_audio_embeddings))),
        reserved_generation_tokens=reserved_generation_tokens,
    )
    return SelectedSaveMemQuestionInput(
        assembled=assembled,
        original_visual_indices=selected_visual_frame_ids,
        original_audio_indices=selected_audio_indices,
        rendered_prompt=rendered_prompt,
    )
