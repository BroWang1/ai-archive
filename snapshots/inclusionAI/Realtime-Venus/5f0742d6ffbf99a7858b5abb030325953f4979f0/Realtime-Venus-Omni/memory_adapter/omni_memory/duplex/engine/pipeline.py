# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Offline and event-driven online orchestration for retrieval-backed Realtime-Venus-Omni."""

from __future__ import annotations
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from ..media import MediaWrite
from .audio_context import AudioKVBlock, as_assembly_units, select_audio_neighbours
from .config import RuntimeConfig
from .duplex_scheduler import (
    DuplexScheduler,
    GenerationChunk,
    QueryHandle,
    QueryRequest,
)
from .events import QueryScheduler, ScheduledQuery, TextQueryEvent
from .memory import (
    ArchiveEviction,
    MemoryUnit,
    QueryMemoryView,
    RetrievalSelection,
    OmniLongTermMemory,
)
from .model_adapter import EncodedDuplexUnit, RealtimeVenusOmniDuplexAdapter, QueryBranch
from .pcost import PCostConfig, PCostDecision, PCostGate


@dataclass(frozen=True)
class IngestResult:
    unit_id: int
    timestamp_seconds: float
    pcost_role: str
    keep_after_hot_window: bool
    reason_codes: tuple[str, ...]
    kv_bytes: int
    archived_kv_bytes: int
    archived_visual_bytes: int
    archived_total_bytes: int
    evicted_payload_bytes: int
    archive_evictions: tuple[ArchiveEviction, ...]
    dropped_unit_ids: tuple[int, ...]
    online_context_unit_ids: tuple[int, ...]
    online_evicted_unit_ids: tuple[int, ...]


@dataclass
class RuntimeQueryTurn:
    """Pipeline-owned state for one persistent, isolated answer branch."""

    scheduled: ScheduledQuery
    branch: QueryBranch
    pending_live_tail: list[MediaWrite] = field(default_factory=list)
    generation_options: dict[str, Any] = field(default_factory=dict)


class OnlineMemoryRuntime:
    """Stateful single-model runtime with immutable per-query cache branches."""

    def __init__(
        self,
        *,
        config: RuntimeConfig,
        adapter: RealtimeVenusOmniDuplexAdapter,
        answer_audio_dir: Path | None = None,
    ) -> None:
        self.config = config
        self.adapter = adapter
        self.answer_audio_dir = answer_audio_dir
        self.expected_media_units: int | None = None
        self.timeline_scheduler = QueryScheduler(
            max_pending_queries=config.max_pending_queries
        )
        self._state_lock = threading.RLock()
        self._model_lock = threading.RLock()
        self._query_memory_views: dict[int, QueryMemoryView] = {}
        self._query_audio_views: dict[int, tuple[AudioKVBlock, ...]] = {}
        self._pcost_config = PCostConfig(
            i_threshold=config.pcost_i_threshold,
            skip_threshold=config.pcost_skip_threshold,
            residual_p99_guard=config.pcost_residual_p99_guard,
            changed_block_fraction_guard=config.pcost_changed_block_fraction_guard,
            max_consecutive_drops=config.pcost_max_consecutive_drops,
            changed_block_residual_threshold=config.pcost_changed_block_residual_threshold,
            motion_penalty_weight=config.pcost_motion_penalty_weight,
            max_p_frames_per_gop=config.pcost_max_p_frames_per_gop,
            block_size=config.pcost_block_size,
            search_radius_ratio=config.pcost_search_radius_ratio,
            search_radius_min=config.pcost_search_radius_min,
            search_radius_max=config.pcost_search_radius_max,
            analysis_width=config.pcost_resize_width,
            analysis_height=config.pcost_resize_height,
            residual_quantile=config.pcost_residual_quantile,
        )
        self._pcost_gate = PCostGate(self._pcost_config)
        self._previous_rgb: Any | None = None
        self._matching_pool = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="pcost-matching"
        )
        self._query_answer_scheduler: DuplexScheduler | None = None
        self._audio_kv_blocks: list[AudioKVBlock] = []
        self.memory = OmniLongTermMemory(
            retrieval_recent_frames=int(config.retrieval_recent_seconds),
            candidate_pool_size=config.candidate_pool_size,
            history_top_k=config.history_top_k,
            retrieval_score_batch_size=config.retrieval_score_batch_size,
            archive_retention_seconds=config.archive_retention_seconds,
            archive_memory_budget_bytes=(
                None
                if config.archive_memory_budget_mb is None
                else config.archive_memory_budget_mb * 1024**2
            ),
            max_archived_units=config.max_archived_units,
            archive_transform=self._archive_unit,
        )

    def close(self) -> None:
        if self._query_answer_scheduler is not None:
            self._query_answer_scheduler.close(wait=True)
        self.timeline_scheduler.close()
        self._matching_pool.shutdown(wait=True, cancel_futures=False)

    def start_query_answer_scheduler(self) -> DuplexScheduler:
        """Start the two-ingress, one-model time-division worker lazily."""
        if self._query_answer_scheduler is None:
            self._query_answer_scheduler = DuplexScheduler(
                write_media=self._write_media_event,
                begin_query=self._begin_query_turn,
                append_live_tail=self._queue_live_tail,
                generate_chunk=self._generate_turn_chunk,
                finish_query=self._finish_query_turn,
                abort_query=self._abort_query_turn,
                max_active_queries=self.config.max_active_queries,
            )
            self._query_answer_scheduler.start()
        return self._query_answer_scheduler

    def submit_media_write(self, write: MediaWrite) -> Future[IngestResult]:
        """Submit one media write without waiting for a complete answer turn."""
        return self.start_query_answer_scheduler().submit_media(write)

    def submit_query_tail(self, write: MediaWrite) -> Future[None]:
        """Append already-committed media to active answer branches only."""
        if not isinstance(write, MediaWrite):
            raise TypeError("query tail must be a MediaWrite")
        return self.start_query_answer_scheduler().submit_query_tail(write)

    def wait_for_query_quiescence(self, timeout: float | None = None) -> None:
        """Wait until every currently runnable answer emitted one chunk."""
        self.start_query_answer_scheduler().wait_until_quiescent(timeout=timeout)

    def finish_query_input(self) -> None:
        """Declare that no further real or synthetic answer tails will arrive."""
        self.start_query_answer_scheduler().finish_input()

    def submit_duplex_query(
        self, event: TextQueryEvent, *, generation_options: dict[str, Any] | None = None
    ) -> QueryHandle:
        """Freeze memory now, then stream the answer on an isolated branch."""
        scheduled = self.submit_query(event)
        with self._state_lock:
            self._query_audio_views[scheduled.sequence_number] = tuple(
                self._audio_kv_blocks
            )
        request = QueryRequest(
            query_id=event.query_id,
            text=event.text,
            snapshot=scheduled,
            arrival_monotonic=event.monotonic_time,
            generation_options=dict(generation_options or {}),
        )
        return self.start_query_answer_scheduler().submit_query(request)

    def ingest_media(self, **kwargs: Any) -> IngestResult:
        """Media ingestion is supplied by the two-phase proactive runtime."""
        raise NotImplementedError("use the proactive prefill/generate runtime")

    def submit_query(self, event: TextQueryEvent) -> ScheduledQuery:
        """Queue a text question and freeze its concrete memory-unit references."""
        with self._state_lock:
            scheduled = self.timeline_scheduler.submit(event)
            eligible = tuple(
                (
                    _parse_event_unit_id(item)
                    for item in scheduled.snapshot.eligible_unit_ids
                )
            )
            self._query_memory_views[scheduled.sequence_number] = (
                self.memory.snapshot_for_query(eligible_unit_ids=eligible)
            )
            return scheduled

    def _write_media_event(self, payload: Any) -> IngestResult:
        if not isinstance(payload, MediaWrite):
            raise TypeError("media scheduler payload must be MediaWrite")
        return self.ingest_media(
            timestamp_seconds=payload.timestamp_seconds,
            frame=payload.frame,
            audio_waveform=payload.audio_waveform,
            monotonic_time=payload.monotonic_time,
        )

    def _begin_query_turn(self, request: QueryRequest) -> RuntimeQueryTurn:
        scheduled = request.snapshot
        if not isinstance(scheduled, ScheduledQuery):
            raise TypeError("query request snapshot must be ScheduledQuery")
        queued = self.timeline_scheduler.get_nowait()
        if queued.sequence_number != scheduled.sequence_number:
            raise RuntimeError("query event ordering diverged from its frozen snapshot")
        with self._state_lock:
            try:
                memory_view = self._query_memory_views.pop(scheduled.sequence_number)
            except KeyError as error:
                raise ValueError(
                    "query memory snapshot is no longer available"
                ) from error
            frozen_audio_blocks = self._query_audio_views.pop(
                scheduled.sequence_number, ()
            )
        selection: RetrievalSelection | None = None
        generation_question = _question_with_language(
            scheduled.query.text, self.config.output_language
        )
        with self._model_lock:
            if self.config.use_memory:
                query_tokens = self.adapter.embed_query(scheduled.query.text)
                selection = self.memory.select_from_view(query_tokens, memory_view)
            if selection is not None:
                query_units = self._formal_query_units(
                    selection=selection,
                    memory_view=memory_view,
                    audio_blocks=frozen_audio_blocks,
                )
                branch = self.adapter.create_query_branch(
                    question=generation_question, units=query_units
                )
            else:
                branch = self.adapter.create_query_branch(
                    question=generation_question, use_live_cache=True
                )
        return RuntimeQueryTurn(
            scheduled=scheduled,
            branch=branch,
            generation_options=dict(request.generation_options),
        )

    def _formal_query_units(
        self,
        *,
        selection: RetrievalSelection,
        memory_view: QueryMemoryView,
        audio_blocks: tuple[AudioKVBlock, ...],
    ) -> tuple[Any, ...]:
        """Add deduplicated audio neighbours to the selected historical units."""
        context_seconds = self.config.retrieval_audio_context_seconds
        if context_seconds <= 0:
            return tuple(selection.units)
        history_by_id = {int(unit.unit_id): unit for unit in memory_view.archived_units}
        anchors = tuple(
            (history_by_id[i] for i in selection.history_unit_ids if i in history_by_id)
        )
        if not anchors:
            return tuple(selection.units)
        audio_selection = select_audio_neighbours(
            anchor_units=anchors,
            full_units=selection.units,
            blocks=audio_blocks,
            context_seconds=context_seconds,
        )
        extra_units = as_assembly_units(audio_selection.added_blocks)
        return tuple(
            sorted(
                (*selection.units, *extra_units),
                key=lambda unit: (unit.timestamp_seconds, unit.unit_id),
            )
        )

    @staticmethod
    def _queue_live_tail(state: Any, payload: Any) -> None:
        if not isinstance(state, RuntimeQueryTurn) or not isinstance(
            payload, MediaWrite
        ):
            raise TypeError("live-tail callback received an invalid state or payload")
        state.pending_live_tail.append(payload)

    def _generate_turn_chunk(self, state: Any) -> GenerationChunk:
        """Append one pending media tail and generate one answer chunk."""
        if not isinstance(state, RuntimeQueryTurn):
            raise TypeError("generation state must be RuntimeQueryTurn")
        with self._model_lock:
            if state.pending_live_tail:
                media = state.pending_live_tail.pop(0)
                self.adapter.append_live_media_to_query(
                    state.branch,
                    frame_list=(
                        None
                        if media.frame is None
                        else (
                            list(media.frame)
                            if isinstance(media.frame, (list, tuple))
                            else [media.frame]
                        )
                    ),
                    audio_waveform=media.audio_waveform,
                )
            options = state.generation_options
            result = self.adapter.generate_query_chunk(
                state.branch,
                max_new_tokens=options.get(
                    "max_new_speak_tokens_per_chunk", self.config.max_new_tokens
                ),
                decode_mode=options.get("decode_mode", self.config.decode_mode),
                prompt_wav_path=options.get(
                    "prompt_wav_path", self.config.ref_audio_path
                ),
                temperature=options.get("temperature", 0.7),
                top_k=options.get("top_k", 100),
                top_p=options.get("top_p", 0.8),
                listen_prob_scale=options.get("listen_prob_scale", 1.0),
                listen_top_k=options.get("listen_top_k"),
                text_repetition_penalty=options.get("text_repetition_penalty", 1.05),
                text_repetition_window_size=options.get(
                    "text_repetition_window_size", 512
                ),
            )
        return GenerationChunk(
            text_delta=result.text,
            audio_waveform=result.audio,
            token_count=int(result.raw_result.get("n_tokens") or 0),
            turn_eos=result.end_of_turn,
            is_listen=result.is_listen,
            raw_result=dict(result.raw_result),
        )

    def _finish_query_turn(
        self, state: Any, chunks: tuple[GenerationChunk, ...], termination_reason: str
    ) -> dict[str, Any]:
        """Complete the answer and release its private decoder branch."""
        if not isinstance(state, RuntimeQueryTurn):
            raise TypeError("finished state must be RuntimeQueryTurn")
        record = {
            "query_id": state.scheduled.query.query_id,
            "text": "".join((chunk.text_delta for chunk in chunks)),
            "end_of_turn": bool(chunks and chunks[-1].turn_eos),
            "termination_reason": termination_reason,
            "chunks": [{"is_listen": chunk.is_listen} for chunk in chunks],
        }
        with self._model_lock:
            self.adapter.close_query_branch(state.branch)
        audio_chunks = tuple(
            (
                chunk.audio_waveform
                for chunk in chunks
                if chunk.audio_waveform is not None
            )
        )
        if audio_chunks:
            record["audio_waveform"] = _concatenate_audio(audio_chunks)
        return record

    def _abort_query_turn(self, state: Any, error: BaseException) -> None:
        if not isinstance(state, RuntimeQueryTurn):
            return
        with self._model_lock:
            self.adapter.close_query_branch(state.branch)

    def _to_memory_unit(
        self, encoded: EncodedDuplexUnit, decision: PCostDecision, has_audio: bool
    ) -> MemoryUnit:
        if encoded.unit_cache is None:
            raise RuntimeError("retrieval memory requires captured per-unit KV")
        return MemoryUnit(
            unit_id=encoded.unit_id,
            timestamp_seconds=encoded.timestamp_seconds,
            visual_embeddings=encoded.visual_embeddings,
            descriptor=None,
            kv_cache=encoded.unit_cache,
            kv_bytes=self.adapter.unit_kv_bytes(encoded),
            kv_source_start=encoded.cache_start,
            kv_source_end=encoded.cache_end,
            kv_capture_local_start=encoded.capture_local_start,
            kv_capture_local_end=encoded.capture_local_end,
            keep_after_hot_window=decision.keep_after_hot_window,
            has_audio=has_audio,
            pcost_role=decision.role,
            reason_codes=decision.reasons,
        )

    def _archive_unit(self, unit: MemoryUnit) -> MemoryUnit:
        device = (
            self.config.device if self.config.kv_archive_device == "cuda" else "cpu"
        )
        cache = self.adapter.move_unit_cache(
            unit.kv_cache, device, pin_cpu=device == "cpu"
        )
        visual = unit.visual_embeddings
        descriptor = unit.descriptor
        if visual is not None:
            visual = visual.to(device=device)
            if device == "cpu" and hasattr(visual, "pin_memory"):
                visual = visual.pin_memory()
        if descriptor is not None:
            descriptor = descriptor.to(device=device)
        return replace(
            unit, kv_cache=cache, visual_embeddings=visual, descriptor=descriptor
        )

    def _retain_audio_block(self, encoded: EncodedDuplexUnit) -> None:
        """Retain one audio-only cache slice independently of visual PCost."""
        if (
            encoded.audio_cache is None
            or encoded.audio_cache_start is None
            or encoded.audio_cache_end is None
            or (encoded.audio_capture_local_start is None)
            or (encoded.audio_capture_local_end is None)
            or (encoded.audio_token_count <= 0)
        ):
            raise RuntimeError(
                "audio context requested but no audio KV span was captured"
            )
        device = (
            self.config.device if self.config.kv_archive_device == "cuda" else "cpu"
        )
        cache = self.adapter.move_unit_cache(
            encoded.audio_cache, device, pin_cpu=device == "cpu"
        )
        block = AudioKVBlock(
            source_unit_id=encoded.unit_id,
            timestamp_seconds=encoded.timestamp_seconds,
            interval_start_seconds=max(
                0.0, encoded.timestamp_seconds - self.config.chunk_seconds
            ),
            interval_end_seconds=encoded.timestamp_seconds,
            kv_cache=cache,
            kv_bytes=self.adapter.kv_cache_bytes(cache),
            token_count=encoded.audio_token_count,
            kv_source_start=encoded.audio_cache_start,
            kv_source_end=encoded.audio_cache_end,
            kv_capture_local_start=encoded.audio_capture_local_start,
            kv_capture_local_end=encoded.audio_capture_local_end,
        )
        minimum_time = encoded.timestamp_seconds - self.config.archive_retention_seconds
        with self._state_lock:
            self._audio_kv_blocks.append(block)
            self._audio_kv_blocks = [
                item
                for item in self._audio_kv_blocks
                if item.timestamp_seconds > minimum_time
            ]


def _to_rgb_array(frame: Any) -> Any:
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("frame conversion requires NumPy") from error
    value = np.asarray(frame.convert("RGB") if hasattr(frame, "convert") else frame)
    if value.dtype != np.uint8 or value.ndim != 3 or value.shape[-1] != 3:
        raise ValueError("video frame must convert to HxWx3 uint8 RGB")
    return np.ascontiguousarray(value)


def _question_with_language(question: str, language: str) -> str:
    if language == "auto":
        return question
    if language == "zh":
        return f"请使用中文自然语言回答。\n{question}"
    if language == "en":
        return f"Answer in natural English.\n{question}"
    raise ValueError(f"unsupported output language: {language}")


def _concatenate_audio(chunks: tuple[Any, ...]) -> Any:
    try:
        import numpy as np
    except ImportError as error:
        raise RuntimeError("joining answer audio requires NumPy") from error
    values = []
    for chunk in chunks:
        if hasattr(chunk, "detach"):
            chunk = chunk.detach().float().cpu().numpy()
        values.append(np.asarray(chunk, dtype=np.float32).reshape(-1))
    return np.concatenate(values) if values else np.empty((0,), dtype=np.float32)


def _event_unit_id(unit_id: int) -> str:
    return f"unit-{unit_id}"


def _parse_event_unit_id(value: str) -> int:
    if not value.startswith("unit-"):
        raise ValueError(f"invalid runtime unit id: {value}")
    return int(value[5:])
