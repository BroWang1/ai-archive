"""定时调度服务 —— 基于 APScheduler。

每条 schedule 对应一个 cron 任务；触发时调用 :class:`RunnerService.start`。
schedule 列表持久化到 ``workspace/server_meta/schedules.json``。
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
except ImportError:  # pragma: no cover
    BackgroundScheduler = None  # type: ignore
    CronTrigger = None  # type: ignore

from .runner_service import RunnerService

logger = logging.getLogger(__name__)


@dataclass
class ScheduleEntry:
    id: str
    language: str
    cron: str
    enabled: bool = True
    fresh: bool = False
    description: str = ""


class SchedulerService:
    """封装 APScheduler，提供 CRUD + 持久化。"""

    def __init__(self, *, runner_service: RunnerService) -> None:
        self.runner = runner_service
        self._schedules: Dict[str, ScheduleEntry] = {}
        self._lock = threading.Lock()
        self._scheduler = BackgroundScheduler() if BackgroundScheduler else None
        self._schedules_file: Optional[Path] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._scheduler is not None and not self._scheduler.running:
            self._scheduler.start()

    def shutdown(self) -> None:
        if self._scheduler is not None and self._scheduler.running:
            self._scheduler.shutdown(wait=False)

    def restore_from_disk(self, path: Path) -> None:
        self._schedules_file = path
        if not path.exists():
            return
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return
        for item in data or []:
            try:
                entry = ScheduleEntry(**item)
            except TypeError:
                continue
            self._schedules[entry.id] = entry
            if entry.enabled:
                self._attach_job(entry)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def list(self) -> List[Dict[str, object]]:
        with self._lock:
            return [asdict(x) for x in self._schedules.values()]

    def upsert(self, entry: ScheduleEntry) -> ScheduleEntry:
        if self._scheduler is None:
            raise RuntimeError(
                "APScheduler 未安装。请执行：pip install apscheduler"
            )
        if CronTrigger is None:
            raise RuntimeError("CronTrigger 不可用")
        # 预校验 cron 表达式
        _parse_cron(entry.cron)

        with self._lock:
            self._schedules[entry.id] = entry
            self._detach_job(entry.id)
            if entry.enabled:
                self._attach_job(entry)
            self._persist()
        return entry

    def delete(self, schedule_id: str) -> bool:
        with self._lock:
            if schedule_id not in self._schedules:
                return False
            del self._schedules[schedule_id]
            self._detach_job(schedule_id)
            self._persist()
        return True

    def toggle(self, schedule_id: str, enabled: bool) -> Optional[ScheduleEntry]:
        with self._lock:
            entry = self._schedules.get(schedule_id)
            if not entry:
                return None
            entry.enabled = enabled
            self._detach_job(schedule_id)
            if enabled:
                self._attach_job(entry)
            self._persist()
            return entry

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _attach_job(self, entry: ScheduleEntry) -> None:
        if self._scheduler is None or CronTrigger is None:
            return
        trigger = _parse_cron(entry.cron)
        self._scheduler.add_job(
            self._fire,
            trigger=trigger,
            id=entry.id,
            replace_existing=True,
            kwargs={"schedule_id": entry.id},
            misfire_grace_time=600,
            coalesce=True,
        )

    def _detach_job(self, schedule_id: str) -> None:
        if self._scheduler is None:
            return
        try:
            self._scheduler.remove_job(schedule_id)
        except Exception:  # pylint: disable=broad-except  # pragma: no cover
            pass

    def _fire(self, schedule_id: str) -> None:
        with self._lock:
            entry = self._schedules.get(schedule_id)
        if not entry or not entry.enabled:
            return
        logger.info("Scheduled run fired: %s (language=%s)", schedule_id, entry.language)
        try:
            self.runner.start(language=entry.language, fresh=entry.fresh)
        except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover
            logger.exception("scheduled run failed to start: %s", exc)

    def _persist(self) -> None:
        if not self._schedules_file:
            return
        tmp = self._schedules_file.with_suffix(".tmp")
        payload = [asdict(x) for x in self._schedules.values()]
        try:
            self._schedules_file.parent.mkdir(parents=True, exist_ok=True)
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            tmp.replace(self._schedules_file)
        except OSError as exc:  # pragma: no cover
            logger.warning("Failed to persist schedules.json: %s", exc)


def _parse_cron(expr: str) -> "CronTrigger":
    """解析 ``分 时 日 月 周`` 5 字段 cron 表达式。"""
    if CronTrigger is None:
        raise RuntimeError("APScheduler 未安装")
    parts = (expr or "").split()
    if len(parts) != 5:
        raise ValueError(
            f"cron 表达式必须为 5 个字段（分 时 日 月 周），got: {expr!r}"
        )
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week,
    )
