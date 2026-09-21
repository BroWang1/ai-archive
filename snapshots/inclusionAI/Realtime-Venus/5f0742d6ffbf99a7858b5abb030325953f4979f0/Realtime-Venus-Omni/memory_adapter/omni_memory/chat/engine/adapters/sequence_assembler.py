# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Compact visual placeholders while preserving audio and text exactly."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import torch


@dataclass(frozen=True)
class CanonicalOmniInput:
    """Processor output needed to reconstruct a batch-size-one omni sequence."""

    input_ids: torch.LongTensor
    image_bounds: torch.LongTensor
    audio_bounds: torch.LongTensor
    image_block_spans: tuple[tuple[int, int], ...]
    max_input_length: int


@dataclass(frozen=True)
class ContextBudget:
    """Token accounting only; negative headroom does not block generation."""

    final_input_tokens: int
    selected_visual_tokens: int
    selected_audio_tokens: int
    media_boundary_tokens: int
    text_control_tokens: int
    reserved_generation_tokens: int
    max_position_embeddings: int
    headroom_tokens: int


@dataclass(frozen=True)
class AssembledInput:
    """Final prefill tensors plus provenance mappings."""

    inputs_embeds: torch.Tensor
    attention_mask: torch.LongTensor
    position_ids: torch.LongTensor
    image_bounds: torch.LongTensor
    audio_bounds: torch.LongTensor
    old_to_new: torch.LongTensor
    selected_frame_indices: tuple[int, ...]
    selected_audio_indices: tuple[int, ...]
    context_budget: ContextBudget


def _validate_bounds(bounds: torch.Tensor, name: str, sequence_length: int) -> None:
    if bounds.ndim != 2 or bounds.shape[1] != 2:
        raise ValueError(f"{name} must have shape [N,2]")
    if bounds.dtype == torch.bool or torch.is_floating_point(bounds):
        raise ValueError(f"{name} must use an integer dtype")
    previous_end = -1
    for index, (start, end) in enumerate(bounds.detach().cpu().tolist()):
        if start < 0 or end <= start or end > sequence_length:
            raise ValueError(f"{name}[{index}] is out of range: [{start},{end})")
        if start < previous_end:
            raise ValueError(f"{name} must be sorted and non-overlapping")
        previous_end = end


def _validate_canonical(canonical: CanonicalOmniInput) -> None:
    if canonical.input_ids.ndim != 2 or canonical.input_ids.shape[0] != 1:
        raise ValueError("input_ids must have shape [1,L]")
    if canonical.input_ids.dtype == torch.bool or torch.is_floating_point(
        canonical.input_ids
    ):
        raise ValueError("input_ids must use an integer dtype")
    sequence_length = canonical.input_ids.shape[1]
    _validate_bounds(canonical.image_bounds, "image_bounds", sequence_length)
    _validate_bounds(canonical.audio_bounds, "audio_bounds", sequence_length)
    if len(canonical.image_block_spans) != canonical.image_bounds.shape[0]:
        raise ValueError("image_block_spans must align one-to-one with image_bounds")
    occupied = torch.zeros(sequence_length, dtype=torch.bool)
    for frame_index, ((block_start, block_end), bound) in enumerate(
        zip(canonical.image_block_spans, canonical.image_bounds.detach().cpu().tolist())
    ):
        (image_start, image_end) = bound
        if image_end - image_start != 64:
            raise ValueError(
                f"image frame {frame_index} must contain exactly 64 placeholders"
            )
        if block_start + 1 != image_start or image_end + 1 != block_end:
            raise ValueError(
                "each image block must be start marker + 64 placeholders + end marker"
            )
        if block_start < 0 or block_end > sequence_length or block_end <= block_start:
            raise ValueError(f"image block {frame_index} is out of range")
        if occupied[block_start:block_end].any():
            raise ValueError("image blocks must not overlap")
        occupied[block_start:block_end] = True
    for audio_index, (start, end) in enumerate(
        canonical.audio_bounds.detach().cpu().tolist()
    ):
        (block_start, block_end) = (start - 1, end + 1)
        if block_start < 0 or block_end > sequence_length:
            raise ValueError(f"audio block {audio_index} markers are out of range")
        if occupied[block_start:block_end].any():
            raise ValueError(f"audio bound {audio_index} overlaps an image block")
        occupied[block_start:block_end] = True
    if (
        isinstance(canonical.max_input_length, bool)
        or not isinstance(canonical.max_input_length, int)
        or canonical.max_input_length <= 0
    ):
        raise ValueError("max_input_length must be a positive integer")


def _validate_selected_indices(
    selected: Mapping[int, tuple[int, ...]], frame_count: int
) -> None:
    for frame_index, token_indices in selected.items():
        if (
            isinstance(frame_index, bool)
            or not isinstance(frame_index, int)
            or frame_index < 0
            or (frame_index >= frame_count)
        ):
            raise ValueError(f"selected visual frame index is invalid: {frame_index}")
        if not isinstance(token_indices, tuple):
            raise ValueError("selected visual token indices must be tuples")
        if tuple(sorted(set(token_indices))) != token_indices or any(
            (
                isinstance(index, bool)
                or not isinstance(index, int)
                or index < 0
                or (index >= 64)
                for index in token_indices
            )
        ):
            raise ValueError(
                "selected visual token indices must be unique, sorted, and in [0,63]"
            )


def _validate_selected_audio_indices(
    selected: tuple[int, ...], block_count: int
) -> None:
    if tuple(sorted(set(selected))) != selected or any(
        (
            isinstance(index, bool)
            or not isinstance(index, int)
            or index < 0
            or (index >= block_count)
            for index in selected
        )
    ):
        raise ValueError(
            "selected audio block indices must be unique, sorted, and in range"
        )


def _remap_contiguous_bound(
    old_to_new: torch.Tensor, start: int, end: int, name: str
) -> tuple[int, int]:
    remapped = old_to_new[start:end]
    if remapped.numel() != end - start or (remapped < 0).any():
        raise ValueError(f"{name} was unexpectedly removed")
    expected = torch.arange(
        int(remapped[0].item()),
        int(remapped[0].item()) + remapped.numel(),
        device=remapped.device,
    )
    if not torch.equal(remapped, expected):
        raise ValueError(f"{name} is not contiguous after compaction")
    return (int(remapped[0].item()), int(remapped[-1].item()) + 1)


def assemble_packed_inputs(
    canonical: CanonicalOmniInput,
    text_embedding_layer: torch.nn.Module,
    visual_frames: Sequence[tuple[tuple[int, ...], torch.Tensor]],
    audio_embeddings: Sequence[torch.Tensor],
    selected_audio_indices: tuple[int, ...] | None = None,
    reserved_generation_tokens: int = 0,
) -> AssembledInput:
    """Assemble sparse per-frame visual rows without materializing ``[F,64,D]``.

    ``visual_frames`` aligns one-to-one with the canonical image blocks.  Each
    item stores original Resampler token indices and the already packed rows in
    the same order.  Empty items remove the complete image block.
    """
    _validate_canonical(canonical)
    frame_count = int(canonical.image_bounds.shape[0])
    frames = tuple(visual_frames)
    if len(frames) != frame_count:
        raise ValueError("visual_frames must align one-to-one with image_bounds")
    selection: dict[int, tuple[int, ...]] = {}
    hidden_size: int | None = None
    for frame_index, (token_indices, embeddings) in enumerate(frames):
        if token_indices:
            selection[frame_index] = token_indices
        if not isinstance(embeddings, torch.Tensor) or embeddings.ndim != 2:
            raise ValueError("packed visual embeddings must have shape [T,D]")
        if int(embeddings.shape[0]) != len(token_indices):
            raise ValueError(
                "packed visual rows must align with original token indices"
            )
        if embeddings.shape[1] <= 0:
            raise ValueError("packed visual hidden size must be positive")
        if hidden_size is None:
            hidden_size = int(embeddings.shape[1])
        elif int(embeddings.shape[1]) != hidden_size:
            raise ValueError("packed visual frames must share one hidden size")
    _validate_selected_indices(selection, frame_count)
    if len(audio_embeddings) != canonical.audio_bounds.shape[0]:
        raise ValueError("audio_embeddings must align one-to-one with audio_bounds")
    selected_audio = (
        tuple(range(len(audio_embeddings)))
        if selected_audio_indices is None
        else selected_audio_indices
    )
    _validate_selected_audio_indices(selected_audio, len(audio_embeddings))
    selected_audio_set = set(selected_audio)
    if (
        isinstance(reserved_generation_tokens, bool)
        or not isinstance(reserved_generation_tokens, int)
        or reserved_generation_tokens < 0
    ):
        raise ValueError("reserved_generation_tokens must be a nonnegative integer")
    sequence_length = int(canonical.input_ids.shape[1])
    keep = torch.ones(
        sequence_length, dtype=torch.bool, device=canonical.input_ids.device
    )
    selected_frames: list[int] = []
    for frame_index, ((block_start, block_end), (image_start, image_end)) in enumerate(
        zip(canonical.image_block_spans, canonical.image_bounds.detach().cpu().tolist())
    ):
        token_indices = selection.get(frame_index, ())
        if not token_indices:
            keep[block_start:block_end] = False
            continue
        selected_frames.append(frame_index)
        keep[image_start:image_end] = False
        old_positions = torch.tensor(
            [image_start + token_index for token_index in token_indices],
            dtype=torch.long,
            device=keep.device,
        )
        keep[old_positions] = True
    for audio_index, (start, end) in enumerate(
        canonical.audio_bounds.detach().cpu().tolist()
    ):
        if audio_index not in selected_audio_set:
            keep[start - 1 : end + 1] = False
    old_to_new = torch.full(
        (sequence_length,), -1, dtype=torch.long, device=keep.device
    )
    kept_positions = torch.nonzero(keep, as_tuple=False).flatten()
    old_to_new[kept_positions] = torch.arange(
        kept_positions.numel(), dtype=torch.long, device=keep.device
    )
    new_length = int(kept_positions.numel())
    selected_visual_token_count = sum(
        (len(selection[frame_index]) for frame_index in selected_frames)
    )
    selected_audio_token_count = sum(
        (
            int(canonical.audio_bounds[index, 1] - canonical.audio_bounds[index, 0])
            for index in selected_audio
        )
    )
    media_boundary_token_count = 2 * (len(selected_frames) + len(selected_audio))
    text_control_token_count = (
        new_length
        - selected_visual_token_count
        - selected_audio_token_count
        - media_boundary_token_count
    )
    if text_control_token_count < 0:
        raise RuntimeError("final input token accounting became negative")
    headroom = canonical.max_input_length - new_length - reserved_generation_tokens
    parameter = next(text_embedding_layer.parameters(), None)
    embedding_device = (
        parameter.device if parameter is not None else canonical.input_ids.device
    )
    compact_ids = canonical.input_ids[:, kept_positions].to(embedding_device)
    inputs_embeds = text_embedding_layer(compact_ids)
    if inputs_embeds.ndim != 3 or inputs_embeds.shape[:2] != (1, new_length):
        raise ValueError("text embedding layer must return [1,L_new,D]")
    llm_hidden_size = int(inputs_embeds.shape[2])
    if hidden_size is not None and hidden_size != llm_hidden_size:
        raise ValueError("visual embedding hidden size must match text embeddings")
    new_image_bounds: list[tuple[int, int]] = []
    for frame_index in selected_frames:
        (image_start, _) = canonical.image_bounds[frame_index].detach().cpu().tolist()
        (token_indices, values) = frames[frame_index]
        old_positions = torch.tensor(
            [image_start + token_index for token_index in token_indices],
            dtype=torch.long,
            device=old_to_new.device,
        )
        new_positions = old_to_new[old_positions]
        expected = torch.arange(
            int(new_positions[0].item()),
            int(new_positions[0].item()) + len(token_indices),
            device=new_positions.device,
        )
        if not torch.equal(new_positions, expected):
            raise ValueError("selected visual placeholders are not contiguous")
        start = int(new_positions[0].item())
        end = int(new_positions[-1].item()) + 1
        inputs_embeds[0, start:end] = values.to(
            device=inputs_embeds.device, dtype=inputs_embeds.dtype
        )
        new_image_bounds.append((start, end))
    new_audio_bounds: list[tuple[int, int]] = []
    for audio_index, (start, end) in enumerate(
        canonical.audio_bounds.detach().cpu().tolist()
    ):
        if audio_index not in selected_audio_set:
            continue
        (new_start, new_end) = _remap_contiguous_bound(
            old_to_new, start, end, f"audio bound {audio_index}"
        )
        values = audio_embeddings[audio_index]
        if values.ndim != 2 or values.shape[0] != end - start:
            raise ValueError(
                f"audio embedding length for bound {audio_index} must be {end - start}"
            )
        if values.shape[1] != llm_hidden_size:
            raise ValueError("audio embedding hidden size must match text embeddings")
        inputs_embeds[0, new_start:new_end] = values.to(
            device=inputs_embeds.device, dtype=inputs_embeds.dtype
        )
        new_audio_bounds.append((new_start, new_end))
    output_device = inputs_embeds.device
    return AssembledInput(
        inputs_embeds=inputs_embeds,
        attention_mask=torch.ones(
            (1, new_length), dtype=torch.long, device=output_device
        ),
        position_ids=torch.arange(
            new_length, dtype=torch.long, device=output_device
        ).unsqueeze(0),
        image_bounds=torch.tensor(
            new_image_bounds, dtype=torch.long, device=output_device
        ).reshape(-1, 2),
        audio_bounds=torch.tensor(
            new_audio_bounds, dtype=torch.long, device=output_device
        ).reshape(-1, 2),
        old_to_new=old_to_new,
        selected_frame_indices=tuple(selected_frames),
        selected_audio_indices=selected_audio,
        context_budget=ContextBudget(
            final_input_tokens=new_length,
            selected_visual_tokens=selected_visual_token_count,
            selected_audio_tokens=selected_audio_token_count,
            media_boundary_tokens=media_boundary_token_count,
            text_control_tokens=text_control_token_count,
            reserved_generation_tokens=reserved_generation_tokens,
            max_position_embeddings=canonical.max_input_length,
            headroom_tokens=headroom,
        ),
    )
