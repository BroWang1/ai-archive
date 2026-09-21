# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Thread-safe event scheduling with immutable, leak-free memory snapshots."""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import math
from queue import Empty, Full
from threading import Condition, RLock
import time
from typing import Any, Deque


def _validate_seconds(value: float, name: str) -> float:
    """Return a finite, non-negative floating-point timestamp."""
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a floating-point timestamp, not bool")
    try:
        timestamp = float(value)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{name} must be a real-valued timestamp") from exc
    if not math.isfinite(timestamp) or timestamp < 0.0:
        raise ValueError(f"{name} must be finite and non-negative, got {value!r}")
    return timestamp


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    if not value.strip():
        raise ValueError(f"{name} must not be empty")
    return value


class UnitState(str, Enum):
    """Lifecycle state of a media unit in the online memory."""

    HOT_PROTECTED = "hot_protected"
    ARCHIVED = "archived"
    REVOKED = "revoked"

    @property
    def eligible(self) -> bool:
        """Whether queries may retrieve a unit in this state."""
        return self is not UnitState.REVOKED


@dataclass(frozen=True)
class MediaEvent:
    """One media unit observed on both the media and monotonic clocks.

    ``event_time`` locates the unit on the video/audio timeline, while
    ``monotonic_time`` records when the process observed it.  Snapshotting
    checks both clocks so preloaded or late-arriving events cannot leak into
    an earlier query.
    """

    unit_id: str
    event_time: float
    monotonic_time: float
    frame: Any | None = field(default=None, compare=False, repr=False)
    audio: Any | None = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "unit_id", _validate_identifier(self.unit_id, "unit_id")
        )
        object.__setattr__(
            self, "event_time", _validate_seconds(self.event_time, "event_time")
        )
        object.__setattr__(
            self,
            "monotonic_time",
            _validate_seconds(self.monotonic_time, "monotonic_time"),
        )


@dataclass(frozen=True)
class TextQueryEvent:
    """A text query arriving at a precise media and monotonic time."""

    query_id: str
    text: str
    event_time: float
    monotonic_time: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "query_id", _validate_identifier(self.query_id, "query_id")
        )
        if not isinstance(self.text, str):
            raise TypeError("text must be a string")
        if not self.text.strip():
            raise ValueError("text must not be empty")
        object.__setattr__(
            self, "event_time", _validate_seconds(self.event_time, "event_time")
        )
        object.__setattr__(
            self,
            "monotonic_time",
            _validate_seconds(self.monotonic_time, "monotonic_time"),
        )


@dataclass(frozen=True)
class MemorySnapshot:
    """Immutable media eligibility view frozen for exactly one query."""

    query_id: str
    media_revision: int
    max_timestamp: float | None
    eligible_unit_ids: tuple[str, ...]
    query_event_time: float
    created_monotonic_time: float


@dataclass(frozen=True)
class ScheduledQuery:
    """A FIFO queue item containing a query and its frozen memory view."""

    sequence_number: int
    query: TextQueryEvent
    snapshot: MemorySnapshot


@dataclass(frozen=True)
class _StateRevision:
    revision: int
    monotonic_time: float
    state: UnitState


@dataclass()
class _UnitRecord:
    event: MediaEvent
    published_revision: int
    state_history: list[_StateRevision]


class MemoryTimeline:
    """Versioned media-unit registry used to create immutable query snapshots."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._revision = 0
        self._units: dict[str, _UnitRecord] = {}

    @property
    def current_revision(self) -> int:
        """Return the latest mutation revision."""
        with self._lock:
            return self._revision

    def publish_media(
        self, event: MediaEvent, *, state: UnitState | str = UnitState.HOT_PROTECTED
    ) -> int:
        """Publish a new unit and return its assigned media revision."""
        if not isinstance(event, MediaEvent):
            raise TypeError("event must be a MediaEvent")
        try:
            unit_state = UnitState(state)
        except ValueError as exc:
            raise ValueError(f"unsupported unit state: {state!r}") from exc
        with self._lock:
            if event.unit_id in self._units:
                raise ValueError(f"media unit {event.unit_id!r} was already published")
            self._revision += 1
            state_revision = _StateRevision(
                revision=self._revision,
                monotonic_time=event.monotonic_time,
                state=unit_state,
            )
            self._units[event.unit_id] = _UnitRecord(
                event=event,
                published_revision=self._revision,
                state_history=[state_revision],
            )
            return self._revision

    def set_unit_state(
        self, unit_id: str, state: UnitState | str, *, monotonic_time: float
    ) -> int:
        """Transition a hot unit to archived/revoked, retaining state history."""
        unit_id = _validate_identifier(unit_id, "unit_id")
        transition_time = _validate_seconds(monotonic_time, "monotonic_time")
        try:
            unit_state = UnitState(state)
        except ValueError as exc:
            raise ValueError(f"unsupported unit state: {state!r}") from exc
        with self._lock:
            try:
                record = self._units[unit_id]
            except KeyError as exc:
                raise KeyError(f"unknown media unit: {unit_id!r}") from exc
            last_state = record.state_history[-1]
            if transition_time < last_state.monotonic_time:
                raise ValueError(
                    f"unit state transition monotonic_time must not move backwards: {transition_time} < {last_state.monotonic_time}"
                )
            if unit_state is last_state.state:
                return last_state.revision
            allowed_next = {
                UnitState.HOT_PROTECTED: {UnitState.ARCHIVED, UnitState.REVOKED},
                UnitState.ARCHIVED: {UnitState.REVOKED},
                UnitState.REVOKED: set(),
            }
            if unit_state not in allowed_next[last_state.state]:
                raise ValueError(
                    f"invalid unit state transition: {last_state.state.value} -> {unit_state.value}"
                )
            self._revision += 1
            record.state_history.append(
                _StateRevision(
                    revision=self._revision,
                    monotonic_time=transition_time,
                    state=unit_state,
                )
            )
            return self._revision

    def snapshot_for_query(self, query: TextQueryEvent) -> MemorySnapshot:
        """Freeze units visible on both clocks at the query's arrival point."""
        if not isinstance(query, TextQueryEvent):
            raise TypeError("query must be a TextQueryEvent")
        with self._lock:
            eligible: list[tuple[float, int, str]] = []
            max_timestamp: float | None = None
            visible_revision = 0
            for record in self._units.values():
                event = record.event
                if (
                    event.event_time > query.event_time
                    or event.monotonic_time > query.monotonic_time
                ):
                    continue
                visible_states = [
                    change
                    for change in record.state_history
                    if change.monotonic_time <= query.monotonic_time
                ]
                if not visible_states:
                    continue
                state_revision = visible_states[-1]
                visible_revision = max(visible_revision, state_revision.revision)
                max_timestamp = (
                    event.event_time
                    if max_timestamp is None
                    else max(max_timestamp, event.event_time)
                )
                if state_revision.state.eligible:
                    eligible.append(
                        (event.event_time, record.published_revision, event.unit_id)
                    )
            eligible.sort()
            return MemorySnapshot(
                query_id=query.query_id,
                media_revision=visible_revision,
                max_timestamp=max_timestamp,
                eligible_unit_ids=tuple((unit_id for (_, _, unit_id) in eligible)),
                query_event_time=query.event_time,
                created_monotonic_time=query.monotonic_time,
            )


class SchedulerClosedError(RuntimeError):
    """Raised when an operation cannot continue because the scheduler closed."""


class QueryScheduler:
    """Thread-safe FIFO query scheduler that snapshots memory during submission.

    Closing stops all future publication/submission.  Already queued work remains
    drainable in FIFO order; once drained, ``get`` raises
    :class:`SchedulerClosedError`.  A blocked consumer is woken by ``close``.
    """

    def __init__(
        self,
        timeline: MemoryTimeline | None = None,
        *,
        max_pending_queries: int | None = None,
    ) -> None:
        if max_pending_queries is not None:
            if (
                isinstance(max_pending_queries, bool)
                or not isinstance(max_pending_queries, int)
                or max_pending_queries <= 0
            ):
                raise ValueError(
                    "max_pending_queries must be a positive integer or None"
                )
        self._timeline = timeline if timeline is not None else MemoryTimeline()
        self._max_pending_queries = max_pending_queries
        self._condition = Condition(RLock())
        self._queue: Deque[ScheduledQuery] = deque()
        self._seen_query_ids: set[str] = set()
        self._next_sequence = 0
        self._closed = False

    @property
    def timeline(self) -> MemoryTimeline:
        """Expose the versioned timeline for read-only inspection/snapshotting."""
        return self._timeline

    @property
    def closed(self) -> bool:
        with self._condition:
            return self._closed

    @property
    def max_pending_queries(self) -> int | None:
        """Maximum queued queries, or ``None`` for an unbounded FIFO."""
        return self._max_pending_queries

    def publish_media(
        self, event: MediaEvent, *, state: UnitState | str = UnitState.HOT_PROTECTED
    ) -> int:
        """Atomically reject publication after close and publish otherwise."""
        with self._condition:
            self._raise_if_closed("publish media")
            return self._timeline.publish_media(event, state=state)

    def set_unit_state(
        self, unit_id: str, state: UnitState | str, *, monotonic_time: float
    ) -> int:
        """Update memory eligibility unless the scheduler has closed."""
        with self._condition:
            self._raise_if_closed("change unit state")
            return self._timeline.set_unit_state(
                unit_id, state, monotonic_time=monotonic_time
            )

    def submit(self, query: TextQueryEvent) -> ScheduledQuery:
        """Freeze the current memory view and append a query to the FIFO."""
        if not isinstance(query, TextQueryEvent):
            raise TypeError("query must be a TextQueryEvent")
        with self._condition:
            self._raise_if_closed("submit query")
            if query.query_id in self._seen_query_ids:
                raise ValueError(f"query_id {query.query_id!r} was already submitted")
            if self.full():
                raise Full(
                    f"query scheduler reached max_pending_queries={self._max_pending_queries}"
                )
            snapshot = self._timeline.snapshot_for_query(query)
            scheduled = ScheduledQuery(
                sequence_number=self._next_sequence, query=query, snapshot=snapshot
            )
            self._next_sequence += 1
            self._seen_query_ids.add(query.query_id)
            self._queue.append(scheduled)
            self._condition.notify()
            return scheduled

    def put(self, query: TextQueryEvent) -> ScheduledQuery:
        """Queue-compatible alias for non-blocking :meth:`submit`."""
        return self.submit(query)

    def get(self, timeout: float | None = None) -> ScheduledQuery:
        """Return the next query, waiting up to ``timeout`` seconds if needed."""
        if timeout is not None:
            timeout = _validate_seconds(timeout, "timeout")
        with self._condition:
            deadline = None if timeout is None else time.monotonic() + timeout
            while not self._queue:
                if self._closed:
                    raise SchedulerClosedError("query scheduler is closed and drained")
                if deadline is None:
                    self._condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise Empty
                self._condition.wait(remaining)
            return self._queue.popleft()

    def get_nowait(self) -> ScheduledQuery:
        """Return the next query immediately or raise ``queue.Empty``."""
        return self.get(timeout=0.0)

    def qsize(self) -> int:
        """Return a thread-safe snapshot of the pending query count."""
        with self._condition:
            return len(self._queue)

    def empty(self) -> bool:
        """Return whether no query is currently queued."""
        return self.qsize() == 0

    def full(self) -> bool:
        """Return whether the configured pending-query capacity is exhausted."""
        with self._condition:
            return (
                self._max_pending_queries is not None
                and len(self._queue) >= self._max_pending_queries
            )

    def close(self) -> None:
        """Stop producers, retain pending work, and wake blocked consumers."""
        with self._condition:
            if self._closed:
                return
            self._closed = True
            self._condition.notify_all()

    def _raise_if_closed(self, operation: str) -> None:
        if self._closed:
            raise SchedulerClosedError(f"cannot {operation}: query scheduler is closed")


__all__ = [
    "MediaEvent",
    "MemorySnapshot",
    "MemoryTimeline",
    "QueryScheduler",
    "ScheduledQuery",
    "SchedulerClosedError",
    "TextQueryEvent",
    "UnitState",
]
