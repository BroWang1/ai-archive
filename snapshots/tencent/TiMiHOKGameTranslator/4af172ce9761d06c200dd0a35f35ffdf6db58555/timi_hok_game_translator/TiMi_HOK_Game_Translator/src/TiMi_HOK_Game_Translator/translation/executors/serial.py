"""翻译策略的串行（单线程）执行引擎。

逐个处理去重后的条目。顺序确定、无线程池开销——
当输入量小或 LLM 后端非线程安全时优选。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from ..base import BaseTranslationStrategy, Entry

logger = logging.getLogger(__name__)


def run_serial(
    strategy: BaseTranslationStrategy,
    entries: Sequence[Entry],
    *,
    source_locale: str,
    target_locale: str,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> Tuple[List[Entry], List[Entry], Dict[str, str]]:
    """按串行方式执行 ``strategy``。

    契约与
    :func:`TiMi_HOK_Game_Translator.translation.executors.concurrent.run_concurrent` 一致。
    """

    translated: List[Entry] = []
    untranslated: List[Entry] = []
    errors: Dict[str, str] = {}
    total = len(entries)

    for idx, entry in enumerate(entries, start=1):
        text = entry.source_text or ""
        if not strategy.filter(text, entry=entry):
            untranslated.append(entry)
            errors.setdefault(entry.key, "filtered out")
            _maybe_report(strategy, idx, total, progress_callback)
            continue

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
            untranslated.append(entry)
            errors[entry.key] = f"{type(exc).__name__}: {exc}"
            _maybe_report(strategy, idx, total, progress_callback)
            continue

        if not target:
            untranslated.append(entry)
            errors.setdefault(entry.key, "empty target_text")
            _maybe_report(strategy, idx, total, progress_callback)
            continue

        entry.target_text = target
        if english is not None:
            entry.metadata.setdefault("english_side", english)
        translated.append(entry)
        _maybe_report(strategy, idx, total, progress_callback)

    return translated, untranslated, errors


def _maybe_report(
    strategy: BaseTranslationStrategy,
    done: int,
    total: int,
    callback: Optional[Callable[[int, int], None]],
) -> None:
    """在进度边界处记录 INFO 日志并回调 ``callback``。"""
    interval = max(1, strategy.progress_log_interval)
    if done % interval == 0 or done == total:
        percent = (done / total * 100) if total else 100.0
        logger.info(
            "[%s] progress %d/%d (%.1f%%)",
            strategy.display_name, done, total, percent,
        )
        if callback is not None:
            try:
                callback(done, total)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 进度回调失败不致命
                logger.debug("progress_callback failed: %s", exc)
