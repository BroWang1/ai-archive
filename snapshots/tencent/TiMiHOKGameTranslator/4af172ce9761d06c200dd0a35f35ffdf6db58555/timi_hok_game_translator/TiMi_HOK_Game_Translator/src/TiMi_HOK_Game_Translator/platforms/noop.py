"""空实现的平台适配器。

当 :data:`config.platform.type` 为 ``"none"`` 时默认选用。所有操作要么返回循环内存记录，
要么将源文件拷贝到本地，保证工作流无网络依赖即可运行。
"""

from __future__ import annotations

import itertools
import shutil
from pathlib import Path
from typing import Sequence

from ..commons import ReviewStage
from .base import (
    SplitResult,
    TaskInfo,
    TaskStatus,
    TranslationPlatform,
    UploadResult,
)


class NoopPlatform(TranslationPlatform):
    """:class:`TranslationPlatform` 的空实现。

    支持全部审校阶段（``supports_stages`` 保持为空）。所有操作均即时
    返回确定性的内存记录，便于在完全无外部服务的情形下运行工作流。
    """

    platform_name = "none"

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._counter = itertools.count(start=1)
        self._files: dict = {}
        self._tasks: dict = {}

    # ------------------------------------------------------------------
    def upload_source(self, file_path: str, *, remote_path: str = "") -> UploadResult:
        file_id = f"noop-{next(self._counter)}"
        self._files[file_id] = file_path
        return UploadResult(file_id=file_id, revision="1", extra={"remote_path": remote_path})

    def download_translations(
        self,
        file_id: str,
        target_locale: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        source = self._files.get(file_id)
        if not source:
            raise KeyError(f"Unknown file_id in NoopPlatform: {file_id}")
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        return str(dest)

    def create_task(
        self,
        file_ids: Sequence[str],
        target_locale: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
        title: str = "",
        description: str = "",
    ) -> TaskInfo:
        task_id = f"noop-task-{next(self._counter)}"
        info = TaskInfo(
            task_id=task_id,
            status=TaskStatus.APPROVED,  # 无需审校——总是直接“完成”。
            target_locale=target_locale,
            project_id=self.project_id,
            review_stage=review_stage,
            percent_completed=100.0,
            extra={
                "file_ids": list(file_ids),
                "title": title,
                "description": description,
            },
        )
        self._tasks[task_id] = info
        return info

    def get_task_status(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> TaskInfo:
        info = self._tasks.get(task_id)
        if info is None:
            return TaskInfo(
                task_id=task_id,
                status=TaskStatus.UNKNOWN,
                review_stage=review_stage,
            )
        return info

    def import_approved(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        # 无实际内容导入，仅创建一个空占位文件。
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text("", encoding="utf-8")
        return str(dest)

    def export_review_report(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        dest = Path(dest_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(
            f"NoopPlatform review report for {task_id} (stage={review_stage})\n",
            encoding="utf-8",
        )
        return str(dest)

    # ------------------------------------------------------------------
    # 扩展 API——重写以保证已批准/待处理拆分一致。
    # ------------------------------------------------------------------
    def split_approved_data(
        self,
        task_id: str,
        *,
        save_approved_path: str,
        save_pending_path: str = "",
        review_stage: str = ReviewStage.FIRST.value,
    ) -> SplitResult:
        self.import_approved(task_id, save_approved_path, review_stage=review_stage)
        if save_pending_path:
            Path(save_pending_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_pending_path).write_text("", encoding="utf-8")
        return SplitResult(
            approved_path=save_approved_path,
            pending_path=save_pending_path,
            should_continue=True,
            is_complete=True,
        )

    def delete_task(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> None:
        self._tasks.pop(task_id, None)


__all__ = ["NoopPlatform"]
