"""翻译策略的并发（线程池）执行引擎。

使用 :class:`concurrent.futures.ThreadPoolExecutor`：典型 LLM / HTTP 后端为 I/O 密集，
GIL 不是矶颈。最后会按原始顺序重新排序，保证确定性。
"""

from __future__ import annotations

import concurrent.futures as _futures
import logging
import threading
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from ..base import BaseTranslationStrategy, Entry

logger = logging.getLogger(__name__)


def run_concurrent(
    strategy: BaseTranslationStrategy,
    entries: Sequence[Entry],
    *,
    source_locale: str,
    target_locale: str,
    max_workers: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[List[Entry], List[Entry], Dict[str, str]]:
    """以并发方式执行 ``strategy``。

    返回值契约（与串行执行器完全一致）：

    * ``translated``——``target_text`` 非空的条目，按输入顺序排列；
    * ``untranslated``——被过滤或报错的条目；
    * ``errors``——以 ``entry.key`` 为键的错误描述（过滤与报错都会在此出现）。
    """

    total = len(entries)
    translated: List[Tuple[int, Entry]] = []
    untranslated: List[Tuple[int, Entry]] = []
    errors: Dict[str, str] = {}
    done_counter = {"n": 0}
    counter_lock = threading.Lock()

    def _worker(idx: int, entry: Entry) -> None:
        text = entry.source_text or ""
        if not strategy.filter(text, entry=entry):
            with strategy._lock:  # noqa: SLF001 — 与策略内部状态协作
                untranslated.append((idx, entry))
                errors.setdefault(entry.key, "filtered out")
            _bump(idx, entry)
            return

        try:
            target, english = strategy.translate(
                text,
                entry=entry,
                source_locale=source_locale,
                target_locale=target_locale,
                context=entry.context,
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 统一收集到 errors
            logger.warning(
                "[%s] translate() raised for key=%s: %s",
                strategy.display_name, entry.key, exc,
            )
            with strategy._lock:  # noqa: SLF001
                untranslated.append((idx, entry))
                errors[entry.key] = f"{type(exc).__name__}: {exc}"
            _bump(idx, entry)
            return

        if not target:
            with strategy._lock:  # noqa: SLF001
                untranslated.append((idx, entry))
                errors.setdefault(entry.key, "empty target_text")
            _bump(idx, entry)
            return

        entry.target_text = target
        if english is not None:
            entry.metadata.setdefault("english_side", english)
        with strategy._lock:  # noqa: SLF001
            translated.append((idx, entry))
        _bump(idx, entry)

    def _bump(idx: int, entry: Entry) -> None:  # noqa: ARG001
        with counter_lock:
            done_counter["n"] += 1
            done = done_counter["n"]
        interval = max(1, strategy.progress_log_interval)
        if done % interval == 0 or done == total:
            percent = (done / total * 100) if total else 100.0
            logger.info(
                "[%s] progress %d/%d (%.1f%%)",
                strategy.display_name, done, total, percent,
            )
            if progress_callback is not None:
                try:
                    progress_callback(done, total)
                except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                    logger.debug("progress_callback failed: %s", exc)

    workers = max(1, min(max_workers, total))
    with _futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_worker, i, e) for i, e in enumerate(entries)]
        # 等待所有 future；个体失败已在 _worker 内捕获，无需在此检查异常。
        for fut in _futures.as_completed(futures):
            _ = fut.result()  # 仅在 _worker 自身报错时重新抛出

    # 回复原始输入顺序，保证下游日志确定。
    translated.sort(key=lambda pair: pair[0])
    untranslated.sort(key=lambda pair: pair[0])
    return (
        [e for _, e in translated],
        [e for _, e in untranslated],
        errors,
    )
