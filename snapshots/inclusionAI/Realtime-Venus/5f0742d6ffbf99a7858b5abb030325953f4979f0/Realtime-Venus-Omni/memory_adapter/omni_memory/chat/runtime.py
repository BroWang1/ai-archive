# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Encode complete media, retrieve relevant memory, and generate Chat answers."""

from __future__ import annotations
import math
from dataclasses import replace
from typing import Any, Mapping, Sequence
import numpy as np
import torch
from ..config import ChatMemoryConfig
from .._engine_schema import Answer
from ..schema import MediaChunk
from .engine.memory.audio_context import select_audio_context
from .engine.memory.experimental_retrieval import (
    retrieve_parallel_dominance_novelty_packed,
)
from .engine.memory.online_manager import pack_dense_visual_store
from .engine.memory.scoring import build_dense_token_inverse_norms
from .engine.memory.types import FrameTokenStore
from .model_adapter import OfficialChatMemoryAdapter
from .pcost import CommittedCandidate, StreamingPCostGate
from .engine.data.sampling import SampledFrame


class MemoryChatRuntime:
    """Encode one media stream once, then answer multiple text questions."""

    def __init__(
        self,
        *,
        model: Any,
        processor: Any,
        config: ChatMemoryConfig,
        generate_audio: bool,
        adapter: Any | None = None,
        prompt_context: Mapping[str, Any] | None = None,
    ) -> None:
        self.model = model
        self.config = config
        self.generate_audio = generate_audio
        self.adapter = adapter or OfficialChatMemoryAdapter(model, processor)
        self.prompt_context = None if prompt_context is None else dict(prompt_context)
        self._state = "idle"
        self._media_id: str | None = None
        self._expected_sequence = 0
        self._last_end: float | None = None
        self._gate: StreamingPCostGate | None = None
        self._original_frames: list[Any] = []
        self._kept_images: list[Any] = []
        self._kept_frames: list[Any] = []
        self._kept_total = 0
        self._audio_parts: list[np.ndarray] = []
        self._visual_store: FrameTokenStore | None = None
        self._visual_snapshot: Any | None = None
        self._inverse_norms: torch.Tensor | None = None
        self._audio_embeddings: tuple[torch.Tensor, ...] = ()
        self._audio_metadata: Any | None = None
        self._last_rendered_prompt: str | None = None

    @property
    def last_rendered_prompt(self) -> str | None:
        """Return the rendered prompt used for the most recent answer."""
        return self._last_rendered_prompt

    def begin_media(self, media_id: str = "media") -> None:
        if self._state != "idle":
            raise RuntimeError("begin_media requires an idle runtime")
        if not isinstance(media_id, str) or not media_id.strip():
            raise ValueError("media_id must be a non-empty string")
        self._media_id = media_id
        self._expected_sequence = 0
        self._last_end = None
        self._gate = StreamingPCostGate(self.config)
        self._original_frames = []
        self._kept_images = []
        self._kept_frames = []
        self._kept_total = 0
        self._audio_parts = []
        self._visual_store = None
        self._visual_snapshot = None
        self._inverse_norms = None
        self._audio_embeddings = ()
        self._audio_metadata = None
        self._last_rendered_prompt = None
        self._state = "receiving_media"

    def add_media_chunk(self, chunk: MediaChunk) -> None:
        """Add one chronological media chunk to the current Chat session."""
        if self._state != "receiving_media":
            raise RuntimeError(
                "add_media_chunk requires begin_media() and an open stream"
            )
        if not isinstance(chunk, MediaChunk):
            raise TypeError("chunk must be a MediaChunk")
        if chunk.sequence_number != self._expected_sequence:
            raise ValueError(
                f"expected media sequence {self._expected_sequence}, got {chunk.sequence_number}"
            )
        if self._last_end is not None and (
            not math.isclose(
                chunk.start_seconds, self._last_end, rel_tol=0.0, abs_tol=1e-06
            )
        ):
            raise ValueError("MediaChunk intervals must be contiguous")
        self._expected_sequence += 1
        self._last_end = chunk.end_seconds
        if chunk.audio_waveform is not None:
            self._audio_parts.append(_audio_array(chunk.audio_waveform))
        if chunk.frames:
            gate = self._require_gate()
            for frame, timestamp in zip(chunk.frames, chunk.frame_timestamps_seconds):
                source_index = len(self._original_frames)
                committed = gate.push(
                    frame=frame,
                    timestamp_seconds=timestamp,
                    source_frame_index=source_index,
                )
                self._original_frames.append(
                    SampledFrame(
                        ordinal=source_index,
                        source_frame_index=source_index,
                        target_timestamp_seconds=float(timestamp),
                        decoded_timestamp_seconds=float(timestamp),
                        sampling_reason="caller_visual_fps",
                    )
                )
                self._accept_committed(committed)
        if chunk.is_final:
            self.end_media()

    def end_media(self) -> None:
        if self._state != "receiving_media":
            raise RuntimeError("end_media requires an open media stream")
        gate = self._require_gate()
        self._accept_committed(gate.finalize())
        self._flush_visual_batch(force=True)
        if self._visual_store is None:
            raise RuntimeError("visual encoder produced no kept frame embeddings")
        if not self._audio_parts:
            raise RuntimeError("Memory Chat requires complete input audio")
        waveform = np.ascontiguousarray(
            np.concatenate(self._audio_parts), dtype=np.float32
        )
        (audio_embeddings, metadata) = self.adapter.encode_audio(
            waveform, tuple(self._original_frames)
        )
        self._audio_embeddings = tuple(audio_embeddings)
        self._audio_metadata = metadata
        self._visual_snapshot = pack_dense_visual_store(
            self._visual_store,
            short_capacity=self.config.recent_frames,
            mid_capacity=max(1, self._visual_store.frame_count),
        )
        self._inverse_norms = build_dense_token_inverse_norms(
            self._visual_store.embeddings,
            frame_chunk_size=self.config.dense_frame_chunk_size,
        )
        self._audio_parts = []
        self._state = "ready"

    def ask(
        self,
        *,
        text: str,
        retrieval_text: str,
        query_id: str = "query",
        generate_audio: bool | None = None,
        generation_options: Mapping[str, Any] | None = None,
    ) -> Answer:
        if self._state != "ready":
            raise RuntimeError("ask requires a completed media stream")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        if not isinstance(retrieval_text, str) or not retrieval_text.strip():
            raise ValueError("retrieval_text must be a non-empty string")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("query_id must be a non-empty string")
        visible_time = self._last_end
        if visible_time is None:
            raise RuntimeError("completed media has no visible end time")
        store = self._require_visual_store()
        snapshot = self._visual_snapshot
        inverse_norms = self._inverse_norms
        if snapshot is None or inverse_norms is None or self._audio_metadata is None:
            raise RuntimeError("memory index is incomplete")
        query_tokens = self.adapter.embed_query(retrieval_text)
        retrieval = retrieve_parallel_dominance_novelty_packed(
            snapshot,
            question_id=query_id,
            query_tokens=query_tokens,
            k_mode="fixed",
            fixed_k=self.config.history_top_k,
            base_k=10,
            low_cv=0.05,
            high_cv=0.3,
            minimum_fraction=0.9,
            score_mode="late_interaction",
            token_weighting="mad",
            match_top_r=1,
            candidate_pool_size=self.config.candidate_pool_size,
            relevance_weight=self.config.relevance_weight,
            relevance_normalization="global",
            novelty_mode="prior_max",
            rank_window=64,
            temporal_decay_fraction=0.05,
            dense_visual_embeddings=store.embeddings,
            dense_inverse_token_norms=inverse_norms,
            dense_frame_chunk_size=self.config.dense_frame_chunk_size,
        )
        metadata = self._audio_metadata
        frame_indices = tuple((int(value) for value in metadata.segment_frame_indices))
        decisions = self._require_gate().decisions
        protected_candidates = {
            item.candidate_ordinal
            for item in tuple((item for item in decisions if item.keep))[
                -len(retrieval.included_short_frame_ids) :
            ]
        }
        short_audio = tuple(
            (
                index
                for (index, candidate) in enumerate(frame_indices)
                if candidate in protected_candidates
            )
        )
        audio = select_audio_context(
            selected_history_frame_ids=retrieval.selected_history_frame_ids,
            included_short_frame_ids=retrieval.included_short_frame_ids,
            frame_timestamps_seconds=tuple(
                (float(value) for value in store.timestamps.detach().cpu().tolist())
            ),
            audio_block_start_seconds=metadata.segment_start_seconds,
            audio_block_end_seconds=metadata.segment_end_seconds,
            audio_block_frame_indices=frame_indices,
            alive_audio_block_indices=tuple(range(len(self._audio_embeddings))),
            effective_duration_seconds=float(metadata.source_duration_seconds),
            audio_sample_rate=int(metadata.source_sample_rate),
            context_seconds=self.config.audio_context_seconds,
            block_selection="any_overlap",
            short_audio_block_indices=short_audio,
        )
        prepared = self.adapter.prepare_answer(
            visual_memory=snapshot,
            selected_visual_ids=retrieval.selected_frame_ids,
            audio_embeddings=self._audio_embeddings,
            audio_start_seconds=tuple(metadata.segment_start_seconds),
            audio_end_seconds=tuple(metadata.segment_end_seconds),
            selected_audio_ids=audio.selected_block_indices,
            prompt=text,
            max_new_tokens=self.config.max_new_tokens,
            generate_audio=(
                self.generate_audio if generate_audio is None else generate_audio
            ),
            prompt_context=self.prompt_context,
        )
        self._audio_embeddings = _offload_audio_embeddings(self._audio_embeddings)
        generated = self.adapter.generate_prepared_answer(
            prepared,
            max_new_tokens=self.config.max_new_tokens,
            generation_options=generation_options,
        )
        self._last_rendered_prompt = generated.rendered_prompt
        return Answer(
            query_id=query_id,
            text=generated.text,
            mode="chat",
            memory_used=True,
            answer_type="explicit_question",
            timestamp_seconds=visible_time,
        )

    def chat(self, msgs: Sequence[Mapping[str, Any]], **kwargs: Any) -> Answer:
        """Accept normal message dictionaries after media collection finishes."""
        text = _last_user_text(msgs)
        query_id = str(kwargs.pop("query_id", "query"))
        generate_audio = kwargs.pop("generate_audio", None)
        if kwargs:
            raise ValueError(
                "unknown Memory Chat arguments: " + ", ".join(sorted(kwargs))
            )
        return self.ask(
            text=text,
            retrieval_text=text,
            query_id=query_id,
            generate_audio=generate_audio,
        )

    def reset_memory(self) -> None:
        self._state = "idle"
        self._media_id = None
        self._gate = None
        self._original_frames = []
        self._kept_images = []
        self._kept_frames = []
        self._kept_total = 0
        self._audio_parts = []
        self._visual_store = None
        self._visual_snapshot = None
        self._inverse_norms = None
        self._audio_embeddings = ()
        self._audio_metadata = None
        self._last_rendered_prompt = None

    close = reset_memory

    def _accept_committed(self, committed: Sequence[CommittedCandidate]) -> None:
        for item in committed:
            if not item.decision.keep:
                continue
            dense_ordinal = self._kept_total
            self._kept_total += 1
            self._kept_images.append(item.frame)
            self._kept_frames.append(
                replace(item.decision.sampled_frame, ordinal=dense_ordinal)
            )
            self._flush_visual_batch(force=False)

    def _flush_visual_batch(self, *, force: bool) -> None:
        limit = self.config.visual_chunk_frames
        while len(self._kept_images) >= limit or (force and self._kept_images):
            count = limit if len(self._kept_images) >= limit else len(self._kept_images)
            images = tuple(self._kept_images[:count])
            frames = tuple(self._kept_frames[:count])
            del self._kept_images[:count]
            del self._kept_frames[:count]
            store = self.adapter.encode_visual(images, frames)
            self._append_store(store)

    def _append_store(self, store: FrameTokenStore) -> None:
        if self._visual_store is None:
            self._visual_store = store
            return
        current = self._visual_store
        self._visual_store = FrameTokenStore(
            embeddings=torch.cat((current.embeddings, store.embeddings), dim=0),
            timestamps=torch.cat((current.timestamps, store.timestamps), dim=0),
            source_frame_indices=torch.cat(
                (current.source_frame_indices, store.source_frame_indices), dim=0
            ),
        )

    def _require_gate(self) -> StreamingPCostGate:
        if self._gate is None:
            raise RuntimeError("PCost gate is not initialized")
        return self._gate

    def _require_visual_store(self) -> FrameTokenStore:
        if self._visual_store is None:
            raise RuntimeError("visual memory is not encoded")
        return self._visual_store


def _offload_audio_embeddings(
    embeddings: tuple[torch.Tensor, ...],
) -> tuple[torch.Tensor, ...]:
    """Move reusable source audio embeddings off GPU before LLM generation."""
    return tuple((item.detach().to(device="cpu") for item in embeddings))


def _audio_array(value: Any) -> np.ndarray:
    if isinstance(value, torch.Tensor):
        value = value.detach().cpu().numpy()
    result = np.asarray(value, dtype=np.float32)
    if result.ndim == 2 and 1 in result.shape:
        result = result.reshape(-1)
    if result.ndim != 1 or result.size == 0 or (not np.isfinite(result).all()):
        raise ValueError("audio_waveform must be finite non-empty mono samples")
    return np.ascontiguousarray(result)


def _last_user_text(msgs: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(tuple(msgs)):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, Sequence) and (not isinstance(content, (str, bytes))):
            parts = [item for item in content if isinstance(item, str) and item.strip()]
            if parts:
                return "\n".join(parts)
    raise ValueError("msgs must contain a non-empty user text message")
