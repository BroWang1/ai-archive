"""跨批次持久化的"尾巴任务"存储。

**背景**

:mod:`_review_state_helpers` 在一个审校阶段轮询到 ``stop_time`` 仍未
100% approved 时，会把**未 approved 的那部分条目**单独上传成一个新
的 Crowdin task（"尾巴 task"），其 ``task_id`` 需要**跨批次**存活，
以便下一天 run 时在 ``last_first_review`` / ``last_second_review`` 状态
里把它接回继续处理。

本模块就是这个跨批次 ``task_id`` 的落盘位置：

.. code-block:: text

    workspace/
    ├── last_tasks.json              ← 本模块的唯一落盘文件（跨批次不归档）
    ├── workflow_state.json          ← 当前批次的 state（归档走）
    ├── project_run_data.json        ← 当前批次的 state_data（归档走）
    └── batches/<batch>/...

落盘结构::

    {
        "first_review": {
            "task_id": "38428",
            "file_id": "40886",
            "batch_name": "vi_20261008204338",
            "upload_path": "...xlsx",   # 原始尾巴 xlsx 的本地路径
            "created_at": "2026-10-08T20:43:43+08:00",
            "pending_count": 10
        },
        "second_review": { ... }   # 可选，二审遗留走同样结构
    }

**为什么单独一份文件而不是复用 state_data？**

:class:`AutoSaveDict`（``project_run_data.json``）在当天 run 结束时会被
:class:`WorkflowRunner` 的"归档"逻辑移动到批次目录，无法被下一天 run
直接读到。``last_tasks.json`` **不参与归档**，是跨批次持久化的
"单一真相源"。

**只保留"最新一条"**

每个 stage 的 slot 永远只持有**最新的尾巴 task_id**。老的尾巴
如果没审完就滚进更新的尾巴 → 更新的尾巴继续覆盖本 slot。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

#: 落盘文件名；位于 ``workspace/`` 根下。
TAIL_TASKS_FILENAME = "last_tasks.json"


class TailTaskStore:
    """``workspace/<lang>/last_tasks.json`` 的轻量读写器（按语种隔离）。

    线程不安全——框架单进程串行使用，不加锁。所有写都是**全文件覆盖**，
    读失败时回退为空 dict（而非抛错），避免因为初次运行文件不存在就挂掉。

    **按语种分区**（2026-10-09 方案 2）：
      * ``lang`` 非空 → 落盘位置 ``workspace/<lang>/last_tasks.json``
        （避免多语种并发时 ``first`` / ``second`` 槽被不同语种相互覆盖）；
      * ``lang`` 为空 → 向后兼容，落盘到 ``workspace/last_tasks.json``。
        调用方若不传 ``lang``，等同于旧行为——方便单语种 / 旧测试复用。
    """

    def __init__(self, workspace: Path, lang: str = "") -> None:
        self.workspace: Path = Path(workspace)
        self.lang: str = (lang or "").strip()
        self.path: Path = self.path_for(self.workspace, self.lang)

    @classmethod
    def path_for(cls, workspace: Path, lang: str = "") -> Path:
        """返回按 ``lang`` 分区后的 ``last_tasks.json`` 绝对路径。

        供 ``translate_state`` / ``sibling_broadcast`` 等**只读**调用方拼路径
        用——它们不需要构造完整 ``TailTaskStore`` 实例，只要一个 ``Path``。
        与 ``__init__`` 的分区规则严格一致，二者改一处另一处自动跟随。
        """
        workspace = Path(workspace)
        lang = (lang or "").strip()
        if lang:
            return workspace / lang / TAIL_TASKS_FILENAME
        return workspace / TAIL_TASKS_FILENAME

    # ------------------------------------------------------------------
    def load_all(self) -> Dict[str, Any]:
        """返回整个 ``last_tasks.json`` 的 dict 视图（不存在时返回空 dict）。"""
        if not self.path.exists():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("TailTaskStore: failed to read %s: %s", self.path, exc)
            return {}
        if not raw.strip():
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("TailTaskStore: malformed %s: %s — treating as empty.",
                           self.path, exc)
            return {}
        return data if isinstance(data, dict) else {}

    def get(self, review_stage: str) -> Optional[Dict[str, Any]]:
        """按阶段取出一条尾巴记录；不存在返回 ``None``。"""
        data = self.load_all()
        record = data.get(review_stage)
        return record if isinstance(record, dict) and record else None

    def put(self, review_stage: str, record: Dict[str, Any]) -> None:
        """插入/覆盖指定阶段的尾巴记录；立即落盘。"""
        data = self.load_all()
        data[review_stage] = dict(record)
        self._save(data)

    def clear(self, review_stage: str) -> None:
        """移除指定阶段的尾巴记录；立即落盘。若不存在则是幂等 no-op。"""
        data = self.load_all()
        if review_stage in data:
            del data[review_stage]
            self._save(data)

    # ------------------------------------------------------------------
    def _save(self, data: Dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            import os as _os
            _os.replace(tmp, self.path)
        except OSError as exc:
            logger.warning("TailTaskStore: failed to write %s: %s", self.path, exc)


__all__ = ["TailTaskStore", "TAIL_TASKS_FILENAME"]
