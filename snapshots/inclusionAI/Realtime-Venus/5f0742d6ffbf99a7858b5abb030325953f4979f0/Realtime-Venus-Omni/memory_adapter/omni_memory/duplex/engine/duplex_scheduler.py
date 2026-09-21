# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Single-model time-division scheduler for media writes and speak turns.

The scheduler exposes two producer chains while deliberately keeping exactly
one model-execution worker.  Media writes and query generation therefore never
mutate the remote-code decoder concurrently; they are interleaved at one
generated chunk per scheduling quantum.
"""

from __future__ import annotations
import queue
import threading
import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class QueryRequest:
    """A text query plus the immutable memory snapshot captured on arrival."""

    query_id: str
    text: str
    snapshot: Any
    arrival_monotonic: float
    generation_options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GenerationChunk:
    """One bounded duplex generation quantum."""

    text_delta: str = ""
    audio_waveform: Any | None = None
    token_count: int = 0
    turn_eos: bool = False
    is_listen: bool = False
    raw_result: dict[str, Any] | None = None


@dataclass(frozen=True)
class QueryResult:
    """Completed query turn with its answer chunks."""

    query_id: str
    text: str
    chunks: tuple[GenerationChunk, ...]
    snapshot: Any
    termination_reason: str
    value: Any | None = None


class QueryHandle:
    """Thread-safe streaming and final-result view of one submitted query."""

    _END = object()

    def __init__(self, request: QueryRequest) -> None:
        self.request = request
        self._chunks: queue.Queue[GenerationChunk | object] = queue.Queue()
        self._future: Future[QueryResult] = Future()

    def next_chunk(self, timeout: float | None = None) -> GenerationChunk:
        """Return the next chunk, raising ``StopIteration`` after completion."""
        item = self._chunks.get(timeout=timeout)
        if item is self._END:
            self._chunks.put(self._END)
            raise StopIteration
        assert isinstance(item, GenerationChunk)
        return item

    def result(self, timeout: float | None = None) -> QueryResult:
        return self._future.result(timeout=timeout)

    def done(self) -> bool:
        return self._future.done()

    def _publish(self, chunk: GenerationChunk) -> None:
        self._chunks.put(chunk)

    def _finish(self, result: QueryResult) -> None:
        self._future.set_result(result)
        self._chunks.put(self._END)

    def _fail(self, error: BaseException) -> None:
        self._future.set_exception(error)
        self._chunks.put(self._END)


@dataclass
class _ActiveTurn:
    request: QueryRequest
    handle: QueryHandle
    state: Any
    chunks: list[GenerationChunk]
    ready: bool = True
    tail_credits: int = 0


@dataclass(frozen=True)
class _MediaEnvelope:
    payload: Any
    future: Future[Any]


@dataclass(frozen=True)
class _QueryTailEnvelope:
    """Media already committed by the live branch, for answer branches only."""

    payload: Any
    future: Future[None]


@dataclass(frozen=True)
class _QueryEnvelope:
    request: QueryRequest
    handle: QueryHandle


@dataclass(frozen=True)
class _FinishInputEnvelope:
    future: Future[None]


@dataclass(frozen=True)
class _QuiescentEnvelope:
    future: Future[None]


@dataclass
class _WaitingTurn:
    envelope: _QueryEnvelope
    live_tail: list[Any]


class DuplexScheduler:
    """Interleave two ingress chains on one stateful model worker.

    ``write_media`` and ``begin_query`` may execute expensive model work.
    ``append_live_tail`` should normally only record the new media payload on
    the per-query state; contextual prefill can then occur inside
    ``generate_chunk`` immediately before that branch's next generation step.
    """

    def __init__(
        self,
        *,
        write_media: Callable[[Any], Any],
        begin_query: Callable[[QueryRequest], Any],
        append_live_tail: Callable[[Any, Any], None],
        generate_chunk: Callable[[Any], GenerationChunk],
        finish_query: (
            Callable[[Any, tuple[GenerationChunk, ...], str], Any] | None
        ) = None,
        abort_query: Callable[[Any, BaseException], None] | None = None,
        max_active_queries: int = 4,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_active_queries <= 0:
            raise ValueError("max_active_queries must be positive")
        self._write_media = write_media
        self._begin_query = begin_query
        self._append_live_tail = append_live_tail
        self._generate_chunk = generate_chunk
        self._finish_query = finish_query
        self._abort_query = abort_query
        self._max_active = max_active_queries
        self._clock = clock
        self._ingress: queue.Queue[
            _MediaEnvelope
            | _QueryTailEnvelope
            | _QueryEnvelope
            | _FinishInputEnvelope
            | _QuiescentEnvelope
            | object
        ] = queue.Queue()
        self._active: list[_ActiveTurn] = []
        self._waiting: list[_WaitingTurn] = []
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._closing = False
        self._closed = False
        self._busy = False
        self._input_finished = False
        self._quiescent_waiters: list[Future[None]] = []
        self._stop = object()

    def start(self) -> None:
        with self._condition:
            if self._closed:
                raise RuntimeError("duplex scheduler is closed")
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="realtime-venus-omni-duplex-model-worker"
            )
            self._thread.start()

    def submit_media(self, payload: Any) -> Future[Any]:
        self._ensure_accepting()
        if self._input_finished:
            raise RuntimeError("cannot submit media after finish_input")
        future: Future[Any] = Future()
        self._ingress.put(_MediaEnvelope(payload, future))
        self._notify()
        return future

    def submit_query(self, request: QueryRequest) -> QueryHandle:
        self._ensure_accepting()
        if self._input_finished:
            raise RuntimeError("cannot submit a query after finish_input")
        if not request.query_id.strip() or not request.text.strip():
            raise ValueError("query_id and text must be non-empty")
        handle = QueryHandle(request)
        self._ingress.put(_QueryEnvelope(request, handle))
        self._notify()
        return handle

    def submit_query_tail(self, payload: Any) -> Future[None]:
        """Wake answer branches after media has been written to the live branch.

        This path skips write_media and schedules pending answers using the
        provided media unit. It also accepts post-EOF silence without adding
        that silence to the live context or long-term memory.
        """
        self._ensure_accepting()
        if self._input_finished:
            raise RuntimeError("cannot submit a query tail after finish_input")
        future: Future[None] = Future()
        self._ingress.put(_QueryTailEnvelope(payload, future))
        self._notify()
        return future

    def finish_input(self) -> None:
        """Declare that no more media/query events will arrive.

        Duplex generation requires a new prefill after every non-terminal
        chunk because Realtime-Venus-Omni consumes ``pending_logits``.  Any branch still
        waiting for live input is therefore closed explicitly at end-of-input.
        """
        with self._condition:
            if self._input_finished:
                return
            if self._closing or self._closed:
                return
            self._input_finished = True
        self.start()
        future: Future[None] = Future()
        self._ingress.put(_FinishInputEnvelope(future))
        self._notify()
        future.result()

    def wait_until_idle(self, timeout: float | None = None) -> None:
        """Wait until ingress, waiting queries and active turns are empty."""
        deadline = None if timeout is None else self._clock() + timeout
        with self._condition:
            while (
                self._busy or not self._ingress.empty() or self._active or self._waiting
            ):
                remaining = None if deadline is None else deadline - self._clock()
                if remaining is not None and remaining <= 0:
                    raise TimeoutError("duplex scheduler did not become idle")
                self._condition.wait(remaining)

    def wait_until_quiescent(self, timeout: float | None = None) -> None:
        """Wait until all currently runnable work has consumed one quantum.

        Active turns that require a future media prefill are intentionally
        allowed to remain.  Replay orchestration uses this boundary after the
        final scheduled question to decide whether every submitted answer has
        reached ``turn_eos`` or another media unit is still required.
        """
        self._ensure_accepting()
        future: Future[None] = Future()
        self._ingress.put(_QuiescentEnvelope(future))
        self._notify()
        future.result(timeout=timeout)

    def close(self, *, wait: bool = True) -> None:
        with self._condition:
            if self._closed:
                return
        if wait:
            self.finish_input()
            self.wait_until_idle()
        with self._condition:
            self._closing = True
        self._ingress.put(self._stop)
        thread = self._thread
        if thread is not None:
            thread.join()
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _ensure_accepting(self) -> None:
        with self._condition:
            if self._closing or self._closed:
                raise RuntimeError("duplex scheduler is closing or closed")
        self.start()

    def _run(self) -> None:
        while True:
            event = self._next_event()
            if event is self._stop:
                return
            if event is not None:
                self._set_busy(True)
                try:
                    self._process_event(event)
                finally:
                    self._set_busy(False)
            self._start_waiting_queries()
            if any((turn.ready for turn in self._active)):
                self._set_busy(True)
                try:
                    self._run_one_quantum()
                finally:
                    self._set_busy(False)
            self._resolve_quiescent_waiters()
            self._notify()

    def _next_event(
        self,
    ) -> (
        _MediaEnvelope
        | _QueryTailEnvelope
        | _QueryEnvelope
        | _FinishInputEnvelope
        | _QuiescentEnvelope
        | object
        | None
    ):
        try:
            return self._ingress.get_nowait()
        except queue.Empty:
            if any((turn.ready for turn in self._active)) or (
                self._waiting and len(self._active) < self._max_active
            ):
                return None
            return self._ingress.get()

    def _process_event(self, event: object) -> None:
        if isinstance(event, _MediaEnvelope):
            try:
                value = self._write_media(event.payload)
                for turn in tuple(self._active):
                    self._append_live_tail(turn.state, event.payload)
                    turn.tail_credits += 1
                    turn.ready = True
                for waiting in self._waiting:
                    waiting.live_tail.append(event.payload)
                event.future.set_result(value)
            except BaseException as error:
                event.future.set_exception(error)
            return
        if isinstance(event, _QueryTailEnvelope):
            try:
                for turn in tuple(self._active):
                    self._append_live_tail(turn.state, event.payload)
                    turn.tail_credits += 1
                    turn.ready = True
                for waiting in self._waiting:
                    waiting.live_tail.append(event.payload)
                event.future.set_result(None)
            except BaseException as error:
                event.future.set_exception(error)
            return
        if isinstance(event, _QueryEnvelope):
            self._waiting.append(_WaitingTurn(event, []))
            return
        if isinstance(event, _FinishInputEnvelope):
            for turn in tuple(self._active):
                if not turn.ready:
                    self._active.remove(turn)
                    self._complete_turn(turn, "input_ended_after_chunk")
            event.future.set_result(None)
            return
        if isinstance(event, _QuiescentEnvelope):
            self._quiescent_waiters.append(event.future)
            return
        raise RuntimeError(f"unknown duplex scheduler event: {type(event)!r}")

    def _resolve_quiescent_waiters(self) -> None:
        runnable_waiting = bool(self._waiting) and len(self._active) < self._max_active
        if any((turn.ready for turn in self._active)) or runnable_waiting:
            return
        (waiters, self._quiescent_waiters) = (self._quiescent_waiters, [])
        for future in waiters:
            if not future.done():
                future.set_result(None)

    def _start_waiting_queries(self) -> None:
        started_turns: list[_ActiveTurn] = []
        while (
            self._waiting and len(self._active) + len(started_turns) < self._max_active
        ):
            waiting = self._waiting.pop(0)
            envelope = waiting.envelope
            state: Any | None = None
            try:
                state = self._begin_query(envelope.request)
                for payload in waiting.live_tail:
                    self._append_live_tail(state, payload)
            except BaseException as error:
                if state is not None and self._abort_query is not None:
                    try:
                        self._abort_query(state, error)
                    except BaseException:
                        pass
                envelope.handle._fail(error)
                continue
            started_turns.append(
                _ActiveTurn(
                    request=envelope.request,
                    handle=envelope.handle,
                    state=state,
                    chunks=[],
                    tail_credits=len(waiting.live_tail),
                )
            )
        if started_turns:
            self._active[0:0] = started_turns

    def _run_one_quantum(self) -> None:
        ready_index = next(
            (index for (index, candidate) in enumerate(self._active) if candidate.ready)
        )
        turn = self._active.pop(ready_index)
        try:
            chunk = self._generate_chunk(turn.state)
            if not isinstance(chunk, GenerationChunk):
                raise TypeError("generate_chunk must return GenerationChunk")
            turn.chunks.append(chunk)
            turn.handle._publish(chunk)
            if turn.tail_credits:
                turn.tail_credits -= 1
            if chunk.turn_eos:
                self._complete_turn(turn, "turn_eos")
            elif self._input_finished:
                self._complete_turn(turn, "input_ended_after_chunk")
            else:
                turn.ready = turn.tail_credits > 0
                self._active.append(turn)
        except BaseException as error:
            if self._abort_query is not None:
                try:
                    self._abort_query(turn.state, error)
                except BaseException:
                    pass
            turn.handle._fail(error)

    def _complete_turn(self, turn: _ActiveTurn, reason: str) -> None:
        chunks = tuple(turn.chunks)
        try:
            value = (
                None
                if self._finish_query is None
                else self._finish_query(turn.state, chunks, reason)
            )
            result = QueryResult(
                query_id=turn.request.query_id,
                text="".join((chunk.text_delta for chunk in chunks)),
                chunks=chunks,
                snapshot=turn.request.snapshot,
                termination_reason=reason,
                value=value,
            )
            turn.handle._finish(result)
        except BaseException as error:
            if self._abort_query is not None:
                try:
                    self._abort_query(turn.state, error)
                except BaseException:
                    pass
            turn.handle._fail(error)

    def _set_busy(self, value: bool) -> None:
        with self._condition:
            self._busy = value
            self._condition.notify_all()

    def _notify(self) -> None:
        with self._condition:
            self._condition.notify_all()


__all__ = [
    "DuplexScheduler",
    "GenerationChunk",
    "QueryHandle",
    "QueryRequest",
    "QueryResult",
]
