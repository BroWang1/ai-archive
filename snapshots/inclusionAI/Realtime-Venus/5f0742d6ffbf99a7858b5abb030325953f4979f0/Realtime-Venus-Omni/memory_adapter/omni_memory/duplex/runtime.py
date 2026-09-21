# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Proactive Duplex flow with generation-time Memory commit."""

from __future__ import annotations
import math
import threading
import time
from pathlib import Path
from typing import Any
from ..config import DuplexMemoryConfig
from .._engine_schema import Answer
from .answer_handle import DuplexAnswerHandle
from .output_arbiter import ProactiveOutputArbiter


class MemoryDuplexRuntime:
    """Add long-term memory to the Duplex prefill and generation interface."""

    def __init__(
        self,
        *,
        model: Any,
        config: DuplexMemoryConfig,
        generate_audio: bool,
        adapter: Any | None = None,
        auto_prepare: bool = False,
        ref_audio: Any | None = None,
        prompt_wav_path: str | Path | None = None,
    ) -> None:
        self.model = model
        self.config = config
        self.generate_audio = generate_audio
        self._ref_audio = ref_audio
        self._prompt_wav_path = prompt_wav_path
        self._prepared = False
        self._closed = False
        self._failed_media_transaction = False
        self._current_media_time_seconds = 0.0
        self._pending_media_time_seconds: float | None = None
        self._pending_text_only = False
        self._pending_text_query: str | None = None
        self._injected_engine = False
        self._answer_handles: list[DuplexAnswerHandle] = []
        self._implicit_answer_handles: list[DuplexAnswerHandle] = []
        self._implicit_query_counter = 0
        self._implicit_answer_tail_count = 0
        self._answer_handles_lock = threading.Lock()
        self._output_arbiter = ProactiveOutputArbiter(config.proactive_output_policy)
        if adapter is not None and all(
            (
                callable(getattr(adapter, name, None))
                for name in (
                    "begin_media_prefill",
                    "process_main_stream_step",
                    "submit_duplex_query",
                )
            )
        ):
            self.engine = adapter
            self.adapter = getattr(adapter, "adapter", None)
            self.official = getattr(adapter, "official", None)
            self._injected_engine = True
        else:
            from .proactive_adapter import DuplexMemoryAdapter
            from .proactive_runtime import ProactiveOnlineMemoryRuntime

            if adapter is None:
                as_duplex = getattr(model, "as_duplex", None)
                if not callable(as_duplex):
                    raise RuntimeError("Memory Duplex requires model.as_duplex()")
                self.official = as_duplex(generate_audio=generate_audio)
                self.adapter = DuplexMemoryAdapter(self.official)
            elif isinstance(adapter, DuplexMemoryAdapter):
                self.adapter = adapter
                self.official = adapter.duplex
            else:
                raise TypeError(
                    "duplex_adapter must be a DuplexMemoryAdapter or an injected two-phase runtime engine"
                )
            self.engine = ProactiveOnlineMemoryRuntime(
                config=_engine_config(
                    config, generate_audio, device=str(self.adapter.device)
                ),
                adapter=self.adapter,
                answer_audio_dir=None,
                async_commit_max_pending=config.pcost_max_pending_commits,
            )
        if auto_prepare:
            self.prepare(
                prefix_system_prompt=config.system_prompt,
                ref_audio=ref_audio,
                prompt_wav_path=prompt_wav_path,
            )

    def prepare(
        self,
        *,
        prefix_system_prompt: str | None = None,
        ref_audio: Any | None = None,
        prompt_wav_path: str | Path | None = None,
        context_previous_marker: str = "\n\nprevious: ",
        **kwargs: Any,
    ) -> Any:
        self._ensure_open()
        if self._prepared:
            raise RuntimeError("Duplex runtime is already prepared")
        prompt = prefix_system_prompt or self.config.system_prompt
        result: Any = None
        if self._injected_engine:
            prepare = getattr(self.engine, "prepare", None)
            if callable(prepare):
                result = prepare(
                    prefix_system_prompt=prompt,
                    ref_audio=ref_audio,
                    prompt_wav_path=prompt_wav_path,
                    context_previous_marker=context_previous_marker,
                    **kwargs,
                )
        else:
            result = self.adapter.prepare(
                system_prompt=prompt,
                ref_audio=self._ref_audio if ref_audio is None else ref_audio,
                prompt_wav_path=(
                    self._prompt_wav_path
                    if prompt_wav_path is None
                    else prompt_wav_path
                ),
                context_previous_marker=context_previous_marker,
                **kwargs,
            )
        self._prepared = True
        self._failed_media_transaction = False
        self._current_media_time_seconds = 0.0
        self._pending_media_time_seconds = None
        self._pending_text_only = False
        self._pending_text_query = None
        self._implicit_query_counter = 0
        self._implicit_answer_tail_count = 0
        with self._answer_handles_lock:
            self._answer_handles.clear()
            self._implicit_answer_handles.clear()
        self._output_arbiter.reset()
        return result

    def streaming_prefill(
        self,
        *,
        audio_waveform: Any | None = None,
        frame_list: list[Any] | tuple[Any, ...] | None = None,
        text_list: list[Any] | tuple[Any, ...] | None = None,
        max_slice_nums: Any = 1,
        batch_vision_feed: bool = False,
    ) -> dict[str, Any]:
        """Prefill media, routing a non-empty ``text_list`` to Memory."""
        self._ensure_prepared()
        if self._has_pending_prefill():
            raise RuntimeError(
                "call streaming_generate() before the next streaming_prefill()"
            )
        frames = tuple(frame_list or ())
        question = _memory_question_from_text_list(text_list)
        if question is not None and self._implicit_answer_handles:
            raise RuntimeError(
                "finish the active Memory answer before submitting another text_list question"
            )
        has_audio = _has_audio_samples(audio_waveform)
        has_media = bool(frames) or has_audio
        self._pending_text_query = question
        if question is not None and (not has_media):
            self._pending_text_only = True
            return _empty_official_prefill_result(success=True)
        timestamp = self._current_media_time_seconds + self.config.chunk_seconds
        try:
            result = self.engine.begin_media_prefill(
                timestamp_seconds=timestamp,
                frame_list=frames,
                audio_waveform=audio_waveform,
                text_list=None if question is not None else text_list,
                monotonic_time=time.monotonic(),
                max_slice_nums=max_slice_nums,
                batch_vision_feed=batch_vision_feed,
            )
        except BaseException:
            self._pending_text_query = None
            self._failed_media_transaction = True
            raise
        self._pending_media_time_seconds = timestamp
        return dict(result)

    def streaming_generate(self, **kwargs: Any) -> dict[str, Any]:
        """Generate a chunk from the live stream or a memory answer branch."""
        self._ensure_prepared()
        kwargs.setdefault("max_new_speak_tokens_per_chunk", self.config.max_new_tokens)
        timestamp = self._pending_media_time_seconds
        text_only = self._pending_text_only
        if timestamp is None and (not text_only):
            if self._implicit_answer_handles:
                return self._continue_implicit_answer_after_media_end()
            raise RuntimeError(
                "streaming_generate() requires a preceding streaming_prefill()"
            )
        question = self._pending_text_query
        explicit_answer_active = self._has_active_answers()
        try:
            if text_only:
                result = None
            else:
                result = self.engine.process_main_stream_step(**kwargs)
                assert timestamp is not None
                self._current_media_time_seconds = timestamp
                if question is not None or self._implicit_answer_handles:
                    self._output_arbiter.apply(result, explicit_answer_active=True)
            if question is not None:
                self._submit_implicit_question(text=question, generation_options=kwargs)
            if self._implicit_answer_handles:
                return self._next_implicit_result()
            if result is None:
                raise RuntimeError("text question did not create a Memory answer")
            visible = self._output_arbiter.apply(
                result, explicit_answer_active=explicit_answer_active
            )
            visible.pop("output_suppressed", None)
            visible.pop("suppression_reason", None)
            return visible
        except BaseException:
            self._failed_media_transaction = True
            raise
        finally:
            self._pending_media_time_seconds = None
            self._pending_text_only = False
            self._pending_text_query = None

    def ask(self, *, text: str, query_id: str = "query") -> Answer:
        """Blocking convenience API for callers with a concurrent media producer."""
        return self.submit_question(text=text, query_id=query_id).result()

    def submit_question(
        self, *, text: str, query_id: str = "query"
    ) -> DuplexAnswerHandle:
        """Submit a boundary-aligned question without blocking live media input."""
        self._ensure_prepared()
        self._ensure_healthy()
        if self._has_pending_prefill():
            raise RuntimeError(
                "finish streaming_generate() before asking a Memory question"
            )
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string")
        if not isinstance(query_id, str) or not query_id.strip():
            raise ValueError("query_id must be a non-empty string")
        return self._submit_question(
            text=text, query_id=query_id, generation_options=None
        )

    def _submit_question(
        self, *, text: str, query_id: str, generation_options: dict[str, Any] | None
    ) -> DuplexAnswerHandle:
        """Freeze a boundary snapshot and create one isolated answer branch."""
        self.wait_for_memory_updates()
        event_time = self._current_media_time_seconds
        event = _text_query_event(
            query_id=query_id,
            text=text,
            event_time=event_time,
            monotonic_time=time.monotonic(),
        )
        if generation_options is None:
            raw_handle = self.engine.submit_duplex_query(event)
        else:
            raw_handle = self.engine.submit_duplex_query(
                event, generation_options=dict(generation_options)
            )
        handle = DuplexAnswerHandle(
            raw_handle=raw_handle,
            query_id=query_id,
            event_time=event_time,
            memory_used=True,
        )
        with self._answer_handles_lock:
            self._answer_handles.append(handle)
        return handle

    def _submit_implicit_question(
        self, *, text: str, generation_options: dict[str, Any]
    ) -> None:
        """Submit a question through text_list."""
        self._implicit_query_counter += 1
        self._implicit_answer_tail_count = 0
        handle = self._submit_question(
            text=text,
            query_id=f"text-list-{self._implicit_query_counter:06d}",
            generation_options=generation_options,
        )
        with self._answer_handles_lock:
            self._implicit_answer_handles.append(handle)

    def _next_implicit_result(self) -> dict[str, Any]:
        """Return the next memory answer chunk in the Duplex result format."""
        with self._answer_handles_lock:
            handle = self._implicit_answer_handles[0]
        chunk = handle.next_chunk(timeout=self.config.answer_step_timeout_seconds)
        result = _official_result_from_memory_chunk(
            chunk, current_time=self._current_media_time_seconds
        )
        if chunk.turn_eos:
            handle.result(timeout=self.config.answer_step_timeout_seconds)
            with self._answer_handles_lock:
                if (
                    self._implicit_answer_handles
                    and self._implicit_answer_handles[0] is handle
                ):
                    self._implicit_answer_handles.pop(0)
        return result

    def _continue_implicit_answer_after_media_end(self) -> dict[str, Any]:
        """Advance an unfinished Memory answer without archiving fake media."""
        if self._implicit_answer_tail_count >= self.config.max_answer_tail_chunks:
            raise RuntimeError(
                f"Memory answer did not reach end_of_turn after {self.config.max_answer_tail_chunks} EOF answer-tail chunks"
            )
        next_tail_count = self._implicit_answer_tail_count + 1
        silence = _silence_audio_chunk(
            chunk_seconds=self.config.chunk_seconds,
            sample_rate=self.config.audio_sample_rate,
        )
        timestamp = (
            self._current_media_time_seconds
            + next_tail_count * self.config.chunk_seconds
        )
        self.publish_question_tail(
            audio_waveform=silence, frame=None, timestamp_seconds=timestamp
        )
        self._implicit_answer_tail_count = next_tail_count
        return self._next_implicit_result()

    def publish_question_tail(
        self,
        *,
        audio_waveform: Any,
        frame: Any | None = None,
        timestamp_seconds: float | None = None,
    ) -> None:
        """Continue active answers without committing another live media unit."""
        self._ensure_prepared()
        self._ensure_healthy()
        if self._pending_media_time_seconds is not None:
            raise RuntimeError("finish streaming_generate() before an answer tail")
        from .media import MediaWrite

        timestamp = _answer_tail_timestamp(
            current_media_time=self._current_media_time_seconds,
            chunk_seconds=self.config.chunk_seconds,
            value=timestamp_seconds,
        )
        self.engine.submit_query_tail(
            MediaWrite(
                timestamp_seconds=timestamp,
                frame=frame,
                audio_waveform=audio_waveform,
                monotonic_time=time.monotonic(),
            )
        ).result()

    def wait_for_questions(self, timeout: float | None = None) -> None:
        """Wait until every answer branch is complete or needs another tail."""
        self._ensure_prepared()
        self._ensure_healthy()
        self.engine.wait_for_query_quiescence(timeout=timeout)

    def finish_questions(self) -> None:
        """Close any branch that remains incomplete after the configured drain."""
        self._ensure_prepared()
        self.engine.finish_query_input()

    def reset_memory(self) -> None:
        """Reset all live, archive and pending state."""
        self._ensure_open()
        close = getattr(self.engine, "close", None)
        if callable(close):
            close()
        if self._injected_engine:
            reset = getattr(self.engine, "reset_memory", None)
            if not callable(reset):
                raise RuntimeError("injected Duplex runtime cannot reset memory")
            reset()
        else:
            from .proactive_runtime import ProactiveOnlineMemoryRuntime

            self.engine = ProactiveOnlineMemoryRuntime(
                config=_engine_config(
                    self.config, self.generate_audio, device=str(self.adapter.device)
                ),
                adapter=self.adapter,
                answer_audio_dir=None,
                async_commit_max_pending=self.config.pcost_max_pending_commits,
            )
        self._prepared = False
        self._failed_media_transaction = False
        self._pending_media_time_seconds = None
        self._pending_text_only = False
        self._pending_text_query = None
        self._current_media_time_seconds = 0.0
        self._implicit_query_counter = 0
        self._implicit_answer_tail_count = 0
        with self._answer_handles_lock:
            self._answer_handles.clear()
            self._implicit_answer_handles.clear()
        self._output_arbiter.reset()

    def close_query(self, branch: Any) -> None:
        closer = getattr(self.adapter, "close_query_branch", None)
        if not callable(closer):
            raise RuntimeError("Duplex adapter does not expose close_query_branch()")
        closer(branch)

    def close(self) -> None:
        """Close the engine, clear local state, and propagate cleanup errors."""
        if self._closed:
            return
        try:
            close = getattr(self.engine, "close", None)
            if callable(close):
                close()
        finally:
            self._closed = True
            self._prepared = False
            self._pending_media_time_seconds = None
            self._pending_text_only = False
            self._pending_text_query = None
            with self._answer_handles_lock:
                self._answer_handles.clear()
                self._implicit_answer_handles.clear()
            self._output_arbiter.reset()

    def wait_for_memory_updates(self) -> None:
        """Make every completed media unit visible before freezing a question."""
        wait = getattr(self.engine, "wait_for_memory_updates", None)
        if not callable(wait):
            return
        try:
            wait()
        except BaseException:
            self._failed_media_transaction = True
            raise

    def _has_active_answers(self) -> bool:
        """Return whether an explicit branch owns the visible output channel."""
        with self._answer_handles_lock:
            self._answer_handles = [
                handle for handle in self._answer_handles if not handle.done()
            ]
            return bool(self._answer_handles)

    def _has_pending_prefill(self) -> bool:
        return self._pending_media_time_seconds is not None or self._pending_text_only

    def __enter__(self) -> "MemoryDuplexRuntime":
        self._ensure_open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __getattr__(self, name: str) -> Any:
        official = self.__dict__.get("official")
        if official is not None:
            return getattr(official, name)
        raise AttributeError(name)

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("Duplex runtime is closed")

    def _ensure_prepared(self) -> None:
        self._ensure_open()
        if not self._prepared:
            raise RuntimeError("call prepare() before Duplex prefill or generation")
        self._ensure_healthy()

    def _ensure_healthy(self) -> None:
        if self._failed_media_transaction:
            raise RuntimeError(
                "Duplex media transaction failed; call reset_memory() before reuse"
            )


def _engine_config(
    config: DuplexMemoryConfig, generate_audio: bool, *, device: str
) -> Any:
    """Map public fields using the attached adapter's actual inference device."""
    from .engine.config import ONLINE_MODE, RuntimeConfig

    values = RuntimeConfig().to_dict()
    values.update(
        {
            "inference_mode": ONLINE_MODE,
            "use_memory": True,
            "device": device,
            "generate_audio": generate_audio,
            "system_prompt": config.system_prompt,
            "max_new_tokens": config.max_new_tokens,
            "decode_mode": config.decode_mode,
            "chunk_seconds": config.chunk_seconds,
            "online_context_seconds": config.online_context_seconds,
            "retrieval_recent_seconds": config.recent_seconds,
            "candidate_pool_size": config.candidate_pool_size,
            "history_top_k": config.history_top_k,
            "retrieval_score_batch_size": config.retrieval_score_batch_size,
            "archive_retention_seconds": config.archive_retention_seconds,
            "archive_memory_budget_mb": config.archive_memory_budget_mb,
            "kv_archive_device": config.archive_device,
            "max_archived_units": config.max_archived_units,
            "retrieval_audio_context_seconds": config.audio_context_seconds,
            "max_pending_queries": config.max_pending_queries,
            "max_active_queries": config.max_active_queries,
            "pcost_enabled": config.pcost_enabled,
            "pcost_i_threshold": config.pcost_i_threshold,
            "pcost_skip_threshold": config.pcost_skip_threshold,
            "pcost_residual_p99_guard": config.pcost_residual_guard,
            "pcost_changed_block_fraction_guard": config.pcost_changed_fraction_guard,
            "pcost_max_consecutive_drops": config.pcost_max_consecutive_drops,
            "pcost_resize_width": config.pcost_resize_width,
            "pcost_resize_height": config.pcost_resize_height,
            "pcost_block_size": config.pcost_block_size,
            "pcost_search_radius_ratio": config.pcost_search_radius_ratio,
            "pcost_search_radius_min": config.pcost_search_radius_min,
            "pcost_search_radius_max": config.pcost_search_radius_max,
            "pcost_motion_penalty_weight": config.pcost_motion_penalty_weight,
            "pcost_changed_block_residual_threshold": config.pcost_changed_block_residual_threshold,
            "pcost_residual_quantile": config.pcost_residual_quantile,
            "pcost_max_p_frames_per_gop": config.pcost_max_p_frames_per_gop,
        }
    )
    return RuntimeConfig.from_mapping(values)


def _text_query_event(**kwargs: Any) -> Any:
    from .engine.events import TextQueryEvent

    return TextQueryEvent(**kwargs)


def _memory_question_from_text_list(
    text_list: list[Any] | tuple[Any, ...] | None,
) -> str | None:
    """Concatenate text entries and route non-empty questions."""
    if text_list is None or len(text_list) == 0:
        return None
    text = "".join(text_list)
    return text if text.strip() else None


def _has_audio_samples(audio_waveform: Any | None) -> bool:
    if audio_waveform is None:
        return False
    return len(audio_waveform) > 0


def _empty_official_prefill_result(*, success: bool) -> dict[str, Any]:
    """Build a text-only prefill result with the expected fields."""
    return {
        "success": success,
        "reason": "",
        "cost_vision_process": 0.0,
        "cost_vision_embed": 0.0,
        "cost_vision_feed": 0.0,
        "cost_audio_process": 0.0,
        "cost_audio_embed": 0.0,
        "cost_audio_feed": 0.0,
        "cost_all": 0.0,
    }


def _official_result_from_memory_chunk(
    chunk: Any, *, current_time: float
) -> dict[str, Any]:
    """Convert a memory answer chunk to the Duplex result format."""
    raw = dict(getattr(chunk, "raw_result", None) or {})
    visible_time: int | float
    if float(current_time).is_integer():
        visible_time = int(current_time)
    else:
        visible_time = float(current_time)
    return {
        "is_listen": bool(raw.get("is_listen", chunk.is_listen)),
        "text": str(raw.get("text", chunk.text_delta) or ""),
        "audio_waveform": raw.get("audio_waveform", chunk.audio_waveform),
        "end_of_turn": bool(raw.get("end_of_turn", chunk.turn_eos)),
        "current_time": visible_time,
        "cost_llm": raw.get("cost_llm", 0.0),
        "cost_tts_prep": raw.get("cost_tts_prep", 0.0),
        "cost_tts": raw.get("cost_tts", 0.0),
        "cost_token2wav": raw.get("cost_token2wav", 0.0),
        "cost_all": raw.get("cost_all", 0.0),
        "n_tokens": raw.get("n_tokens", chunk.token_count),
        "n_tts_tokens": raw.get("n_tts_tokens", 0),
    }


def _answer_tail_timestamp(
    *, current_media_time: float, chunk_seconds: float, value: float | None
) -> float:
    timestamp = current_media_time + chunk_seconds if value is None else value
    if (
        isinstance(timestamp, bool)
        or not isinstance(timestamp, (int, float))
        or (not math.isfinite(float(timestamp)))
        or (float(timestamp) < current_media_time)
    ):
        raise ValueError(
            "answer-tail timestamp must be finite and not precede live media"
        )
    return float(timestamp)


def _silence_audio_chunk(*, chunk_seconds: float, sample_rate: int) -> Any:
    """Create one float32 silence chunk for an internal answer-only tail."""
    import numpy as np

    samples_per_chunk = int(round(chunk_seconds * sample_rate))
    if samples_per_chunk <= 0:
        raise ValueError("answer-tail silence must contain at least one sample")
    return np.zeros(samples_per_chunk, dtype=np.float32)
