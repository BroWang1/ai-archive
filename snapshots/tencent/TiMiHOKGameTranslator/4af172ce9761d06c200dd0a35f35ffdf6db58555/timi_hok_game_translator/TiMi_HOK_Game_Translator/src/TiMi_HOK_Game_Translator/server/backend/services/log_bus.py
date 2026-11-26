"""日志总线：子进程 stdout → 环形缓冲 + WebSocket 实时推送。

架构：
    [子进程 stdout 行] ──push──▶ [per-run 内存 ring + 落盘文件]
                                        │
                                        └─broadcast─▶ 所有订阅的 WebSocket

设计要点：
    * 单例实例由 ``app.state.log_bus`` 持有，所有子进程 / 路由共享；
    * ``publish`` 必须是**线程安全**（子进程读取线程调用），
      但 WebSocket 回写走 ``asyncio``，故采用"把消息塞到 asyncio.Queue"
      的做法：主事件循环在 ``register_subscriber`` 阶段注入。
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from typing import Deque, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class LogLine:
    """一行日志。"""

    run_id: str
    ts: float
    stream: str   # "stdout" | "stderr" | "meta"
    line: str


class LogBus:
    """全局日志总线。"""

    def __init__(self, max_buffer: int = 5000) -> None:
        self._max_buffer = max_buffer
        self._buffers: Dict[str, Deque[LogLine]] = defaultdict(lambda: deque(maxlen=max_buffer))
        self._subscribers: Dict[str, Set[asyncio.Queue]] = defaultdict(set)
        self._global_subscribers: Set[asyncio.Queue] = set()
        self._lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """由 FastAPI 事件循环启动时注入。"""
        self._loop = loop

    # ------------------------------------------------------------------
    # 发布
    # ------------------------------------------------------------------
    def publish(self, run_id: str, line: str, *, stream: str = "stdout") -> None:
        """线程安全：子进程读取线程调用。"""
        entry = LogLine(run_id=run_id, ts=time.time(), stream=stream, line=line.rstrip("\r\n"))
        with self._lock:
            self._buffers[run_id].append(entry)
            targets: List[asyncio.Queue] = list(self._subscribers.get(run_id, ()))
            targets.extend(self._global_subscribers)
            loop = self._loop

        if loop is None or not targets:
            return

        payload = _to_json(entry)
        for queue in targets:
            # call_soon_threadsafe 避免跨线程 await
            loop.call_soon_threadsafe(_safe_put, queue, payload)

    # ------------------------------------------------------------------
    # 订阅 / 读取
    # ------------------------------------------------------------------
    async def subscribe(self, run_id: Optional[str] = None) -> asyncio.Queue:
        """注册订阅者，返回一个 ``asyncio.Queue``，消息已经是 JSON 字符串。"""
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        with self._lock:
            if run_id is None:
                self._global_subscribers.add(queue)
            else:
                self._subscribers[run_id].add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue, run_id: Optional[str] = None) -> None:
        with self._lock:
            if run_id is None:
                self._global_subscribers.discard(queue)
            else:
                self._subscribers.get(run_id, set()).discard(queue)

    def tail(self, run_id: str, limit: int = 500) -> List[Dict[str, object]]:
        """抓取最近 ``limit`` 行。"""
        with self._lock:
            buf = list(self._buffers.get(run_id, ()))
        if limit and len(buf) > limit:
            buf = buf[-limit:]
        return [asdict(x) for x in buf]

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._buffers.pop(run_id, None)


# -----------------------------------------------------------------------------
# 辅助
# -----------------------------------------------------------------------------
def _to_json(entry: LogLine) -> str:
    return json.dumps(asdict(entry), ensure_ascii=False)


def _safe_put(queue: asyncio.Queue, payload: str) -> None:
    """asyncio Queue.put_nowait 的宽容版本——队列满了直接丢最老的。"""
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        try:
            queue.get_nowait()
        except Exception:  # pylint: disable=broad-except
            return
        try:
            queue.put_nowait(payload)
        except Exception:  # pylint: disable=broad-except
            return
