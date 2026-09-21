# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Two-phase Duplex runtime with ordered asynchronous visual Memory commits."""

from __future__ import annotations
import time
from concurrent.futures import Future
from dataclasses import dataclass
from functools import partial
from typing import Any, Sequence
from .async_commit import OrderedAsyncCommitQueue
from .engine.events import MediaEvent, UnitState
from .engine.pcost import PCostDecision, PCostMetrics, match_rgb_pair
from .engine.pipeline import (
    IngestResult,
    OnlineMemoryRuntime,
    _event_unit_id,
    _to_rgb_array,
)
from .media import MediaWrite
from .proactive_adapter import DuplexMemoryAdapter, PendingDuplexMedia


@dataclass(frozen=True)
class PendingMediaTransaction:
    """One prefill awaiting its single generation call."""

    adapter_state: PendingDuplexMedia
    timestamp_seconds: float
    frame: Any | None
    audio_waveform: Any | None
    audio_present: bool
    rgb: Any | None
    matching: tuple[Future[Any], ...]
    observed_monotonic: float
    processing_started: float


class ProactiveOnlineMemoryRuntime(OnlineMemoryRuntime):
    """Generate once, then classify and commit visual Memory in the background."""

    adapter: DuplexMemoryAdapter

    def __init__(self, *, async_commit_max_pending: int = 8, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        if not isinstance(self.adapter, DuplexMemoryAdapter):
            raise TypeError("Duplex Memory processing requires DuplexMemoryAdapter")
        self._pending_media: PendingMediaTransaction | None = None
        self._failed_media_transaction = False
        self._async_commits = OrderedAsyncCommitQueue[IngestResult](
            max_pending=async_commit_max_pending, thread_name="visual-memory-commit"
        )

    @property
    def has_pending_media(self) -> bool:
        return self._pending_media is not None

    @property
    def pending_visual_commits(self) -> int:
        """Return the number of visual decisions not yet harvested."""
        return self._async_commits.pending_count

    def begin_media_prefill(
        self,
        *,
        timestamp_seconds: float,
        frame_list: Sequence[Any] | None,
        audio_waveform: Any | None,
        text_list: Sequence[Any] | None = None,
        monotonic_time: float | None = None,
        max_slice_nums: Any = 1,
        batch_vision_feed: bool = False,
    ) -> dict[str, Any]:
        """Run prefill and open exactly one media transaction."""
        if self._failed_media_transaction:
            raise RuntimeError("Duplex media transaction failed; reset the runtime")
        self._poll_async_commits()
        if self._pending_media is not None:
            raise RuntimeError(
                "call streaming_generate() before the next streaming_prefill()"
            )
        processing_started = time.monotonic()
        observed = processing_started if monotonic_time is None else monotonic_time
        frames = tuple(frame_list or ())
        rgbs = tuple((_to_rgb_array(frame) for frame in frames))
        matching: list[Future[Any]] = []
        reference = self._previous_rgb
        if self.config.use_memory and self.config.pcost_enabled:
            for rgb in rgbs:
                if reference is not None:
                    matching.append(
                        self._matching_pool.submit(
                            match_rgb_pair, rgb, reference, self._pcost_config
                        )
                    )
                reference = rgb
        rgb = rgbs[-1] if rgbs else None
        try:
            with self._model_lock:
                (adapter_state, result) = self.adapter.begin_media_prefill(
                    timestamp_seconds=timestamp_seconds,
                    frame_list=frames or None,
                    audio_waveform=audio_waveform,
                    text_list=text_list,
                    max_slice_nums=max_slice_nums,
                    batch_vision_feed=batch_vision_feed,
                    capture_memory_artifacts=self.config.use_memory,
                    capture_audio_artifacts=self.config.use_memory
                    and self.config.retrieval_audio_context_seconds > 0
                    and (audio_waveform is not None),
                )
        except BaseException:
            self._failed_media_transaction = True
            raise
        self._pending_media = PendingMediaTransaction(
            adapter_state=adapter_state,
            timestamp_seconds=float(timestamp_seconds),
            frame=frames or None,
            audio_waveform=audio_waveform,
            audio_present=audio_waveform is not None,
            rgb=rgb,
            matching=tuple(matching),
            observed_monotonic=float(observed),
            processing_started=processing_started,
        )
        if self.config.use_memory and rgb is not None:
            self._previous_rgb = rgb
        return result

    def ingest_media(self, **_: Any) -> IngestResult:
        """Reject the frozen one-step path, which would force a listen result."""
        raise RuntimeError(
            "media must use begin_media_prefill() followed by process_main_stream_step()"
        )

    def process_main_stream_step(self, **generate_kwargs: Any) -> dict[str, Any]:
        """Generate once, capture the unit, and schedule its Memory update."""
        if self._failed_media_transaction:
            raise RuntimeError("Duplex media transaction failed; reset the runtime")
        self._poll_async_commits()
        pending = self._pending_media
        if pending is None:
            raise RuntimeError(
                "streaming_generate() requires a preceding streaming_prefill()"
            )
        try:
            with self._model_lock:
                (encoded, generation) = self.adapter.generate_and_capture_media_unit(
                    pending.adapter_state, **generate_kwargs
                )
            (online_context_unit_ids, online_evicted_unit_ids) = (
                self._publish_encoded_fast_path(encoded, pending)
            )
            self._async_commits.submit(
                partial(
                    self._commit_visual_memory,
                    encoded,
                    pending,
                    online_context_unit_ids=online_context_unit_ids,
                    online_evicted_unit_ids=online_evicted_unit_ids,
                )
            )
            if self._query_answer_scheduler is not None:
                self.submit_query_tail(
                    MediaWrite(
                        timestamp_seconds=pending.timestamp_seconds,
                        frame=pending.frame,
                        audio_waveform=pending.audio_waveform,
                        monotonic_time=pending.observed_monotonic,
                    )
                ).result()
        except BaseException:
            self._failed_media_transaction = True
            raise
        finally:
            self._pending_media = None
        return generation

    def _publish_encoded_fast_path(
        self, encoded: Any, pending: PendingMediaTransaction
    ) -> tuple[tuple[int, ...], tuple[int, ...]]:
        """Publish clocks/audio/live-window state without waiting for visual PCost."""
        if (
            self.config.use_memory
            and self.config.retrieval_audio_context_seconds > 0
            and pending.audio_present
        ):
            self._retain_audio_block(encoded)
        with self._state_lock:
            self.timeline_scheduler.publish_media(
                MediaEvent(
                    unit_id=_event_unit_id(encoded.unit_id),
                    event_time=pending.timestamp_seconds,
                    monotonic_time=pending.observed_monotonic,
                )
            )
        with self._model_lock:
            online_evicted_unit_ids = self.adapter.enforce_online_context_window(
                latest_timestamp_seconds=pending.timestamp_seconds,
                window_seconds=self.config.online_context_seconds,
            )
            online_context_unit_ids = tuple(self.adapter.live_unit_ids)
        if not self.config.use_memory and online_evicted_unit_ids:
            with self._state_lock:
                for unit_id in online_evicted_unit_ids:
                    self.timeline_scheduler.set_unit_state(
                        _event_unit_id(unit_id),
                        UnitState.REVOKED,
                        monotonic_time=max(
                            pending.observed_monotonic, time.monotonic()
                        ),
                    )
        return (online_context_unit_ids, online_evicted_unit_ids)

    def _commit_visual_memory(
        self,
        encoded: Any,
        pending: PendingMediaTransaction,
        *,
        online_context_unit_ids: tuple[int, ...],
        online_evicted_unit_ids: tuple[int, ...],
    ) -> IngestResult:
        """Resolve PCost and mutate visual Memory on the ordered worker."""
        metrics = _aggregate_metrics(
            tuple((future.result() for future in pending.matching))
        )
        if not self.config.use_memory:
            decision = PCostDecision("I", True, ("memory_disabled",), None)
        elif not self.config.pcost_enabled or pending.rgb is None:
            decision = PCostDecision(
                "I", True, ("pcost_disabled_or_no_visual",), metrics
            )
        else:
            decision = self._pcost_gate.decide(metrics)
        memory_unit = (
            self._to_memory_unit(encoded, decision, pending.audio_present)
            if self.config.use_memory
            else None
        )
        with self._state_lock:
            if self.config.use_memory:
                if memory_unit is None:
                    raise RuntimeError("retrieval memory unit was not captured")
                removed = self.memory.add_unit(memory_unit)
                archive_evictions = self.memory.last_archive_evictions
                for unit_id in self.memory.last_archived_unit_ids:
                    self.timeline_scheduler.set_unit_state(
                        _event_unit_id(unit_id),
                        UnitState.ARCHIVED,
                        monotonic_time=max(
                            pending.observed_monotonic, time.monotonic()
                        ),
                    )
                for unit in removed:
                    self.timeline_scheduler.set_unit_state(
                        _event_unit_id(unit.unit_id),
                        UnitState.REVOKED,
                        monotonic_time=max(
                            pending.observed_monotonic, time.monotonic()
                        ),
                    )
            else:
                removed = ()
                archive_evictions = ()
        result = IngestResult(
            unit_id=encoded.unit_id,
            timestamp_seconds=encoded.timestamp_seconds,
            pcost_role=decision.role,
            keep_after_hot_window=decision.keep_after_hot_window,
            reason_codes=decision.reasons,
            kv_bytes=0 if memory_unit is None else memory_unit.kv_bytes,
            archived_kv_bytes=self.memory.archived_kv_bytes,
            archived_visual_bytes=self.memory.archived_visual_bytes,
            archived_total_bytes=self.memory.archived_total_bytes,
            evicted_payload_bytes=sum(
                (item.payload_bytes for item in archive_evictions)
            ),
            archive_evictions=archive_evictions,
            dropped_unit_ids=tuple((unit.unit_id for unit in removed)),
            online_context_unit_ids=online_context_unit_ids,
            online_evicted_unit_ids=online_evicted_unit_ids,
        )
        return result

    def wait_for_memory_updates(self) -> None:
        """Wait at an explicit consistency boundary, such as a question or EOF."""
        try:
            self._async_commits.drain()
        except BaseException:
            self._failed_media_transaction = True
            raise

    def _poll_async_commits(self) -> None:
        try:
            self._async_commits.poll()
        except BaseException:
            self._failed_media_transaction = True
            raise

    def ensure_media_complete(self) -> None:
        if self._pending_media is not None:
            raise RuntimeError(
                "a media prefill is still pending; call streaming_generate() first"
            )
        self.wait_for_memory_updates()

    def close(self) -> None:
        self._pending_media = None
        error: BaseException | None = None
        try:
            self._async_commits.close()
        except BaseException as caught:
            error = caught
        try:
            super().close()
        except BaseException as caught:
            if error is None:
                error = caught
        if error is not None:
            raise error


__all__ = ["PendingMediaTransaction", "ProactiveOnlineMemoryRuntime"]


def _aggregate_metrics(values: tuple[PCostMetrics | None, ...]) -> PCostMetrics | None:
    """Conservatively aggregate every adjacent visual pair in one media unit."""
    if not values or any((value is None for value in values)):
        return None
    metrics = tuple((value for value in values if value is not None))
    return PCostMetrics(
        pcost=max((item.pcost for item in metrics)),
        residual_mean=max((item.residual_mean for item in metrics)),
        residual_p99=max((item.residual_p99 for item in metrics)),
        changed_block_fraction=max((item.changed_block_fraction for item in metrics)),
        motion_mean=max((item.motion_mean for item in metrics)),
        block_count=sum((item.block_count for item in metrics)),
    )
