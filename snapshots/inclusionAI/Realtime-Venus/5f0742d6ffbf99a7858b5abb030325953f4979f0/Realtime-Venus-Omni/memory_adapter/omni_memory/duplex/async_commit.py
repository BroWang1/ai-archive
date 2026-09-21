# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Bounded, ordered background commits for Duplex visual Memory."""

from __future__ import annotations
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from threading import RLock
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


class OrderedAsyncCommitQueue(Generic[T]):
    """Run commits in submission order without blocking the media fast path.

    A bounded queue prevents an under-provisioned PCost worker from retaining an
    unbounded number of captured K/V tensors.  When the bound is reached, only
    the oldest commit is joined; normal media units otherwise return without a
    per-unit ``Future.result()`` call.
    """

    def __init__(self, *, max_pending: int, thread_name: str) -> None:
        if isinstance(max_pending, bool) or not isinstance(max_pending, int):
            raise TypeError("max_pending must be an integer")
        if max_pending <= 0:
            raise ValueError("max_pending must be positive")
        if not isinstance(thread_name, str) or not thread_name.strip():
            raise ValueError("thread_name must be a non-empty string")
        self.max_pending = max_pending
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=thread_name
        )
        self._pending: deque[Future[T]] = deque()
        self._tail: Future[T] | None = None
        self._failure: BaseException | None = None
        self._closed = False
        self._lock = RLock()

    @property
    def pending_count(self) -> int:
        """Return the number of submitted commits not yet harvested."""
        with self._lock:
            self._harvest_completed()
            self._raise_failure()
            return len(self._pending)

    def submit(self, operation: Callable[[], T]) -> Future[T]:
        """Submit one operation, applying bounded backpressure if necessary."""
        if not callable(operation):
            raise TypeError("operation must be callable")
        with self._lock:
            if self._closed:
                raise RuntimeError("asynchronous commit queue is closed")
            self._harvest_completed()
            self._raise_failure()
            while len(self._pending) >= self.max_pending:
                self._resolve_oldest()
                self._harvest_completed()
                self._raise_failure()
            predecessor = self._tail
            future = self._executor.submit(
                _run_after_predecessor, predecessor, operation
            )
            self._pending.append(future)
            self._tail = future
            return future

    def poll(self) -> None:
        """Surface completed failures without waiting for unfinished commits."""
        with self._lock:
            self._harvest_completed()
            self._raise_failure()

    def drain(self) -> None:
        """Wait for every submitted commit and surface the first failure."""
        with self._lock:
            while self._pending:
                self._resolve_oldest()
            self._raise_failure()

    def close(self) -> None:
        """Drain and release the worker, preserving any commit failure."""
        error: BaseException | None = None
        with self._lock:
            if self._closed:
                self._raise_failure()
                return
            self._closed = True
            try:
                while self._pending:
                    self._resolve_oldest()
                self._raise_failure()
            except BaseException as caught:
                error = caught
        self._executor.shutdown(wait=True, cancel_futures=False)
        if error is not None:
            raise error

    def _harvest_completed(self) -> None:
        while self._pending and self._pending[0].done():
            self._resolve_oldest()

    def _resolve_oldest(self) -> None:
        future = self._pending.popleft()
        try:
            future.result()
        except BaseException as error:
            if self._failure is None:
                self._failure = error

    def _raise_failure(self) -> None:
        if self._failure is not None:
            raise RuntimeError(
                "asynchronous visual Memory commit failed"
            ) from self._failure


def _run_after_predecessor(
    predecessor: Future[T] | None, operation: Callable[[], T]
) -> T:
    """Preserve temporal order and stop successors after a failed commit."""
    if predecessor is not None:
        predecessor.result()
    return operation()


__all__ = ["OrderedAsyncCommitQueue"]
