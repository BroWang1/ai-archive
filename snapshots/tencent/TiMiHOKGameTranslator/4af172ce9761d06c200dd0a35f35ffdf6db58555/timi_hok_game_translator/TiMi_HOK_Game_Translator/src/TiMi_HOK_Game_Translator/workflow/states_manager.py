"""工作流状态完成记录器。

**不**驱动执行（驱动交给 :class:`~.runner.WorkflowRunner`），仅记录本次运行中
已完成的状态，并落盘以支持进程重启后断点续跑。

文件结构::

    {
      "status": { "pull_vcs": true, "translate": false, ... },
      "metadata": {
        "created_at": "2026-04-01T12:34:56.789012",
        "updated_at": "2026-04-01T12:35:00.000000",
        "version": "1.0"
      }
    }

并发性：内部 ``RLock`` 保护变更方法，后台调度器可在运行时任意时刻
调用 :meth:`get_progress`。
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class StatesManager:
    """``state_name → bool`` 的持久化映射（是否已完成）。

    参数：
        state_file_path: 存放状态的 JSON 文件路径（绝对或相对 workspace）。
        auto_save: ``True``（默认）时每次变更均立即写盘；为 ``False`` 时
            需使用上下文管理器 API 批量写盘。
    """

    _METADATA_VERSION = "1.0"

    def __init__(
        self,
        state_file_path: str | os.PathLike[str],
        *,
        auto_save: bool = True,
    ) -> None:
        self._path = Path(state_file_path)
        self._auto_save = auto_save
        self._lock = threading.RLock()
        self._status: Dict[str, bool] = {}
        self._metadata: Dict[str, Any] = {}

    # ------------------------------------------------------------------
    # 对外 API
    # ------------------------------------------------------------------
    @property
    def path(self) -> Path:
        return self._path

    def initialize(
        self,
        initial_status: Dict[str, bool],
        *,
        force: bool = False,
    ) -> None:
        """以 ``initial_status`` 初始化状态。

        参数：
            initial_status: ``state_name → False`` 映射，会被拷贝保存。
            force: ``True`` 时覆盖已存在的状态文件；默认 ``False``
                则保留已有文件，以便断点续跑。
        """
        with self._lock:
            if not force and self._path.exists():
                logger.info(
                    "StatesManager: resuming from existing state file %s",
                    self._path,
                )
                self.load()
                return

            self._status = dict(initial_status)
            self._metadata = {
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
                "version": self._METADATA_VERSION,
            }
            self._save()

    def load(self) -> Dict[str, bool]:
        """从磁盘重新加载状态；返回副本。"""
        with self._lock:
            if not self._path.exists():
                logger.debug("StatesManager: %s does not exist", self._path)
                return {}
            try:
                data = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning(
                    "StatesManager: failed to load %s: %s", self._path, exc,
                )
                return {}
            self._status = dict(data.get("status") or {})
            self._metadata = dict(data.get("metadata") or {})
            return dict(self._status)

    def save(self) -> None:
        """强制写盘，忽略 :attr:`_auto_save` 设置。"""
        with self._lock:
            self._save()

    def update_status(
        self,
        state_name: str,
        value: bool,
        *,
        save: Optional[bool] = None,
    ) -> None:
        """将 ``state_name`` 置为 ``value``，并选择是否写盘。"""
        with self._lock:
            previous = self._status.get(state_name)
            self._status[state_name] = value
            if previous != value:
                logger.info(
                    "StatesManager: %s %s → %s", state_name, previous, value,
                )
            if save if save is not None else self._auto_save:
                self._save()

    def update_multiple(
        self,
        updates: Dict[str, bool],
        *,
        save: Optional[bool] = None,
    ) -> None:
        with self._lock:
            for name, value in updates.items():
                self._status[name] = value
            if save if save is not None else self._auto_save:
                self._save()

    def mark_completed(self, state_name: str) -> None:
        """:func:`update_status` 的语义封装：标完成。"""
        self.update_status(state_name, True)

    def is_completed(self, state_name: str) -> bool:
        with self._lock:
            return self._status.get(state_name) is True

    def get_status(self, state_name: str) -> Optional[bool]:
        with self._lock:
            return self._status.get(state_name)

    def all_status(self) -> Dict[str, bool]:
        with self._lock:
            return dict(self._status)

    def reset(self, *, save: bool = True) -> None:
        with self._lock:
            for key in self._status:
                self._status[key] = False
            if save:
                self._save()

    def get_progress(self) -> Dict[str, Any]:
        """返回适合监控上报的进度快照。"""
        with self._lock:
            total = len(self._status)
            completed = sum(1 for v in self._status.values() if v)
            percent = round((completed / total * 100) if total else 0.0, 2)
            return {
                "total": total,
                "completed": completed,
                "remaining": total - completed,
                "progress_percent": percent,
                "updated_at": self._metadata.get("updated_at"),
            }

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------
    def __enter__(self) -> StatesManager:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401
        if not self._auto_save:
            self.save()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _save(self) -> None:
        self._metadata["updated_at"] = _now_iso()
        self._metadata.setdefault("created_at", self._metadata["updated_at"])
        self._metadata.setdefault("version", self._METADATA_VERSION)
        payload = {"status": dict(self._status), "metadata": dict(self._metadata)}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(self._path.suffix + ".tmp")
        try:
            tmp_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp_path, self._path)
        except OSError as exc:
            logger.warning(
                "StatesManager: failed to write %s: %s", self._path, exc,
            )
            if tmp_path.exists():
                try:  # noqa: SIM105
                    tmp_path.unlink()
                except OSError:
                    pass


def _now_iso() -> str:
    return datetime.now().isoformat()


__all__ = ["StatesManager"]
