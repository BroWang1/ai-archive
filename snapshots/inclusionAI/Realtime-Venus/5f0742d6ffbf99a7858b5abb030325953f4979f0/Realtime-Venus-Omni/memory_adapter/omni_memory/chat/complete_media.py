# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Complete-media Chat path without long-term memory or retrieval."""

from __future__ import annotations
import math
from dataclasses import replace
from typing import Any, Sequence
import numpy as np
import torch
from .._engine_schema import Answer as EngineAnswer
from ..schema import MediaChunk
from .engine.data.sampling import SampledFrame
from .engine.memory.audio_context import select_audio_context
from .engine.memory.online_manager import pack_dense_visual_store
from .engine.memory.types import FrameTokenStore
from .model_adapter import OfficialChatMemoryAdapter


class CompleteMediaChat:
    """Encode a bounded complete-media input and answer without building memory."""

    def __init__(
        self,
        *,
        model: Any,
        processor: Any,
        max_new_tokens: int,
        visual_encoding_frames_per_batch: int,
        max_visual_frames: int = 128,
        adapter: Any | None = None,
    ) -> None:
        """Create an idle offline session around one already loaded model."""
        self.adapter = adapter or OfficialChatMemoryAdapter(model, processor)
        self.max_new_tokens = int(max_new_tokens)
        self.visual_encoding_frames_per_batch = int(visual_encoding_frames_per_batch)
        self.max_visual_frames = int(max_visual_frames)
        if self.max_new_tokens <= 0 or self.visual_encoding_frames_per_batch <= 0:
            raise ValueError("generation and visual batch sizes must be positive")
        if self.max_visual_frames <= 0:
            raise ValueError("max_visual_frames must be positive")
        self._state = "idle"
        self._expected_sequence = 0
        self._last_end = 0.0
        self._images: list[Any] = []
        self._sampled_frames: list[SampledFrame] = []
        self._audio_parts: list[np.ndarray] = []
        self._visual_store: FrameTokenStore | None = None
        self._audio_embeddings: tuple[torch.Tensor, ...] = ()
        self._audio_metadata: Any | None = None
        self._selected_positions: tuple[int, ...] = ()

    def begin_media(self, media_id: str = "media") -> None:
        """Reset the session and begin accepting chronological media chunks."""
        if self._state != "idle":
            raise RuntimeError("begin_media requires an idle session")
        if not isinstance(media_id, str) or not media_id.strip():
            raise ValueError("media_id must be a non-empty string")
        self._state = "receiving_media"
        self._expected_sequence = 0
        self._last_end = 0.0
        self._images = []
        self._sampled_frames = []
        self._audio_parts = []
        self._visual_store = None
        self._audio_embeddings = ()
        self._audio_metadata = None
        self._selected_positions = ()

    def add_media_chunk(self, chunk: MediaChunk) -> None:
        """Append one validated chunk without performing hidden resampling."""
        if self._state != "receiving_media":
            raise RuntimeError("add_media_chunk requires an open media stream")
        if chunk.sequence_number != self._expected_sequence:
            raise ValueError(
                f"expected media sequence {self._expected_sequence}, got {chunk.sequence_number}"
            )
        if self._expected_sequence and (
            not math.isclose(
                chunk.start_seconds, self._last_end, rel_tol=0.0, abs_tol=1e-06
            )
        ):
            raise ValueError("MediaChunk intervals must be contiguous")
        for frame, timestamp in zip(chunk.frames, chunk.frame_timestamps_seconds):
            ordinal = len(self._sampled_frames)
            self._images.append(frame)
            self._sampled_frames.append(
                SampledFrame(
                    ordinal=ordinal,
                    source_frame_index=ordinal,
                    target_timestamp_seconds=timestamp,
                    decoded_timestamp_seconds=timestamp,
                    sampling_reason="caller_visual_fps",
                )
            )
        if chunk.audio_waveform is not None:
            self._audio_parts.append(_audio_array(chunk.audio_waveform))
        self._expected_sequence += 1
        self._last_end = chunk.end_seconds
        if chunk.is_final:
            self.end_media()

    def end_media(self) -> None:
        """Uniformly cap visual candidates, then encode visual and 1-second audio."""
        if self._state != "receiving_media":
            raise RuntimeError("end_media requires an open media stream")
        if not self._sampled_frames:
            raise RuntimeError("complete-media Chat requires at least one frame")
        if not self._audio_parts:
            raise RuntimeError("complete-media Chat requires input audio")
        self._selected_positions = _uniform_positions(
            len(self._sampled_frames),
            min(self.max_visual_frames, len(self._sampled_frames)),
        )
        selected_images = tuple(
            (self._images[index] for index in self._selected_positions)
        )
        selected_frames = tuple(
            (
                replace(self._sampled_frames[index], ordinal=ordinal)
                for (ordinal, index) in enumerate(self._selected_positions)
            )
        )
        stores: list[FrameTokenStore] = []
        for start in range(
            0, len(selected_images), self.visual_encoding_frames_per_batch
        ):
            end = start + self.visual_encoding_frames_per_batch
            stores.append(
                self.adapter.encode_visual(
                    selected_images[start:end], selected_frames[start:end]
                )
            )
        self._visual_store = _concatenate_stores(stores)
        waveform = np.ascontiguousarray(
            np.concatenate(self._audio_parts), dtype=np.float32
        )
        audio_grid = _one_second_audio_grid(self._last_end)
        (audio_embeddings, metadata) = self.adapter.encode_audio(waveform, audio_grid)
        selected_audio_ids = _select_fixed_local_audio(
            store=self._visual_store,
            metadata=metadata,
            audio_block_count=len(audio_embeddings),
        )
        self._audio_embeddings = tuple(
            (audio_embeddings[index] for index in selected_audio_ids)
        )
        self._audio_metadata = _select_audio_metadata(metadata, selected_audio_ids)
        self._images = []
        self._audio_parts = []
        self._state = "ready"

    def ask(self, *, text: str, query_id: str) -> EngineAnswer:
        """Generate one answer from capped frames and their local audio windows."""
        if self._state != "ready":
            raise RuntimeError("ask requires completed media")
        if not text.strip() or not query_id.strip():
            raise ValueError("query_id and text must be non-empty")
        store = self._visual_store
        metadata = self._audio_metadata
        if store is None or metadata is None:
            raise RuntimeError("complete-media encoding is incomplete")
        visual_memory = pack_dense_visual_store(
            store, short_capacity=0, mid_capacity=max(1, store.frame_count)
        )
        selected_visual_ids = tuple(range(store.frame_count))
        selected_audio_ids = tuple(range(len(self._audio_embeddings)))
        prepared = self.adapter.prepare_answer(
            visual_memory=visual_memory,
            selected_visual_ids=selected_visual_ids,
            audio_embeddings=self._audio_embeddings,
            audio_start_seconds=tuple(metadata.segment_start_seconds),
            audio_end_seconds=tuple(metadata.segment_end_seconds),
            selected_audio_ids=selected_audio_ids,
            prompt=text,
            max_new_tokens=self.max_new_tokens,
            generate_audio=False,
        )
        self._audio_embeddings = _offload_audio_embeddings(self._audio_embeddings)
        generated = self.adapter.generate_prepared_answer(
            prepared, max_new_tokens=self.max_new_tokens
        )
        return EngineAnswer(
            query_id=query_id,
            text=generated.text,
            mode="chat",
            memory_used=False,
            answer_type="explicit_question",
            timestamp_seconds=self._last_end,
            raw={
                "text": generated.text,
                "context_budget": generated.context_budget,
                "sampled_visual_frames": len(self._sampled_frames),
                "pcost_kept_visual_frames": None,
                "candidate_visual_frames": None,
                "selected_history_visual_frames": None,
                "selected_recent_visual_frames": None,
                "selected_audio_blocks": len(selected_audio_ids),
            },
        )

    def close(self) -> None:
        """Release all media and encoded state held by this session."""
        self._state = "idle"
        self._images = []
        self._sampled_frames = []
        self._audio_parts = []
        self._visual_store = None
        self._audio_embeddings = ()
        self._audio_metadata = None


def _uniform_positions(count: int, selected_count: int) -> tuple[int, ...]:
    """Select deterministic positions over the complete candidate timeline."""
    if selected_count >= count:
        return tuple(range(count))
    if selected_count == 1:
        return (0,)
    return tuple(
        (
            round(position * (count - 1) / (selected_count - 1))
            for position in range(selected_count)
        )
    )


def _one_second_audio_grid(duration_seconds: float) -> tuple[SampledFrame, ...]:
    """Build an audio-only segmentation grid independent of visual sampling."""
    count = max(1, math.ceil(duration_seconds - 1e-12))
    return tuple(
        (
            SampledFrame(
                ordinal=index,
                source_frame_index=index,
                target_timestamp_seconds=float(index),
                decoded_timestamp_seconds=float(index),
                sampling_reason="one_second_audio_grid",
            )
            for index in range(count)
        )
    )


def _concatenate_stores(stores: Sequence[FrameTokenStore]) -> FrameTokenStore:
    """Concatenate bounded visual batches into one dense encoded store."""
    if not stores:
        raise RuntimeError("visual encoder produced no frame store")
    if len(stores) == 1:
        return stores[0]
    return FrameTokenStore(
        embeddings=torch.cat(tuple((item.embeddings for item in stores)), dim=0),
        timestamps=torch.cat(tuple((item.timestamps for item in stores)), dim=0),
        source_frame_indices=torch.cat(
            tuple((item.source_frame_indices for item in stores)), dim=0
        ),
    )


def _audio_array(value: Any) -> np.ndarray:
    """Convert supported audio containers to finite contiguous mono float32."""
    if isinstance(value, torch.Tensor):
        value = value.detach().cpu().numpy()
    result = np.asarray(value, dtype=np.float32)
    if result.ndim == 2 and 1 in result.shape:
        result = result.reshape(-1)
    if result.ndim != 1 or result.size == 0 or (not np.isfinite(result).all()):
        raise ValueError("audio_waveform must contain finite non-empty mono samples")
    return np.ascontiguousarray(result)


def _select_fixed_local_audio(
    *, store: FrameTokenStore, metadata: Any, audio_block_count: int
) -> tuple[int, ...]:
    """Select the fixed local audio bank for all No-Memory Chat questions."""
    selected = select_audio_context(
        selected_history_frame_ids=tuple(range(store.frame_count)),
        included_short_frame_ids=(),
        frame_timestamps_seconds=tuple(
            (float(value) for value in store.timestamps.detach().cpu().tolist())
        ),
        audio_block_start_seconds=metadata.segment_start_seconds,
        audio_block_end_seconds=metadata.segment_end_seconds,
        audio_block_frame_indices=metadata.segment_frame_indices,
        alive_audio_block_indices=tuple(range(audio_block_count)),
        effective_duration_seconds=float(metadata.source_duration_seconds),
        audio_sample_rate=int(metadata.source_sample_rate),
        context_seconds=1.0,
        short_audio_block_indices=(),
    )
    if not selected.selected_block_indices:
        raise RuntimeError("fixed visual frames selected no local audio blocks")
    return selected.selected_block_indices


def _select_audio_metadata(metadata: Any, indices: tuple[int, ...]) -> Any:
    """Keep metadata aligned with the fixed local No-Memory audio bank."""
    return replace(
        metadata,
        segment_sample_counts=tuple(
            (metadata.segment_sample_counts[index] for index in indices)
        ),
        segment_start_seconds=tuple(
            (metadata.segment_start_seconds[index] for index in indices)
        ),
        segment_end_seconds=tuple(
            (metadata.segment_end_seconds[index] for index in indices)
        ),
        segment_frame_indices=tuple(
            (metadata.segment_frame_indices[index] for index in indices)
        ),
        segment_token_counts=tuple(
            (metadata.segment_token_counts[index] for index in indices)
        ),
    )


def _offload_audio_embeddings(
    embeddings: tuple[torch.Tensor, ...],
) -> tuple[torch.Tensor, ...]:
    """Move reusable source audio embeddings off GPU before LLM generation."""
    return tuple((item.detach().to(device="cpu") for item in embeddings))


__all__ = ["CompleteMediaChat"]
