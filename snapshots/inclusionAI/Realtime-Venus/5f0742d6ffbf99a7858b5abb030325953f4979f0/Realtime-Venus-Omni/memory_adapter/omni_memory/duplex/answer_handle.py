# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Stable nonblocking answer handle shared by Memory and Duplex."""

from __future__ import annotations
import threading
from typing import Any, Mapping
from .._engine_schema import Answer


class DuplexAnswerHandle:
    """Convert an internal chunked query handle into the public Answer schema."""

    def __init__(
        self, *, raw_handle: Any, query_id: str, event_time: float, memory_used: bool
    ) -> None:
        self._raw_handle = raw_handle
        self._query_id = query_id
        self._event_time = event_time
        self._memory_used = memory_used
        self._lock = threading.Lock()
        self._answer: Answer | None = None

    def done(self) -> bool:
        """Return whether the model has finished the full answer turn."""
        return bool(self._raw_handle.done())

    def next_chunk(self, timeout: float | None = None) -> Any:
        """Expose one generated chunk for services that stream partial output."""
        return self._raw_handle.next_chunk(timeout=timeout)

    def result(self, timeout: float | None = None) -> Answer:
        """Wait for ``turn_eos`` (or explicit input closure) and return one answer."""
        with self._lock:
            if self._answer is not None:
                return self._answer
            raw_result = self._raw_handle.result(timeout=timeout)
            record = _result_record(raw_result, self._query_id)
            answer = _answer_from_record(
                record,
                query_id=self._query_id,
                event_time=self._event_time,
                memory_used=self._memory_used,
            )
            self._answer = answer
            return answer


def _result_record(raw_result: Any, query_id: str) -> dict[str, Any]:
    if isinstance(raw_result, Mapping):
        return dict(raw_result)
    value = getattr(raw_result, "value", None)
    if not isinstance(value, Mapping):
        raise RuntimeError(
            f"Duplex query {query_id!r} completed without a result mapping"
        )
    return dict(value)


def _answer_from_record(
    record: Mapping[str, Any], *, query_id: str, event_time: float, memory_used: bool
) -> Answer:
    end_of_turn = record.get("end_of_turn")
    if not isinstance(end_of_turn, bool):
        raise RuntimeError(
            f"Duplex query {query_id!r} result requires boolean end_of_turn"
        )
    termination_reason = record.get("termination_reason")
    if not isinstance(termination_reason, str) or not termination_reason:
        raise RuntimeError(
            f"Duplex query {query_id!r} result requires termination_reason"
        )
    chunks = record.get("chunks")
    is_listen: bool | None = None
    if isinstance(chunks, (list, tuple)) and chunks:
        final = chunks[-1]
        if isinstance(final, Mapping) and isinstance(final.get("is_listen"), bool):
            is_listen = bool(final["is_listen"])
    return Answer(
        query_id=query_id,
        text=str(record.get("text") or ""),
        mode="duplex",
        memory_used=memory_used,
        answer_type="explicit_question",
        timestamp_seconds=event_time,
        is_listen=is_listen,
        end_of_turn=end_of_turn,
        termination_reason=termination_reason,
        audio_waveform=record.get("audio_waveform"),
        raw=dict(record),
    )


__all__ = ["DuplexAnswerHandle"]
