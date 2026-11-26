"""翻译/审校平台抽象层。

“平台”指 Crowdin、Phrase（Memsource）等第三方服务，它们在外部管理项目、任务与
翻译者工作流。本框架仅通过 :class:`TranslationPlatform` 接口与它们交互，
将厂商 SDK 隔离在主包外。

参考发行包提供 :class:`NoopPlatform`，供 ``platform.type = "none"`` 使用；
真实集成位于本子包（``phrase_platform.py`` 、 ``crowdin_platform.py`` …），
通过 ``@register_platform("<name>")`` 启用。

同一份 :class:`~TiMi_HOK_Game_Translator.config.LanguageProfile` 可为不同审校阶段配置
不同平台（参见 :class:`~TiMi_HOK_Game_Translator.commons.ReviewStage`）。因此所有需区分
阶段的方法都接受命名参数 ``review_stage``，使工作流无歧义地指定“轮询一审任务”。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Sequence, Tuple

from ..commons import ReviewStage


class TaskStatus(str, Enum):
    """远端平台上一个翻译任务的粗粒度状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass
class TaskInfo:
    """平台返回的单个任务信息。

    字段：
        task_id: 平台侧的任务 ID。
        status: 粗粒度审校状态；平台自定义状态可放入 :attr:`extra`。
        source_locale / target_locale: BCP-47 标签。
        project_id: 平台侧项目 ID。
        review_stage: 本任务归属的审校阶段（对应
            :class:`~TiMi_HOK_Game_Translator.commons.ReviewStage.value`）。
        percent_completed: 0..100 的进度（平台不提供时为 0）。
        extra: 平台自定义字段（``jobUid`` / ``workflow_step`` / ``translator`` …）。
    """

    task_id: str
    status: TaskStatus = TaskStatus.UNKNOWN
    source_locale: str = ""
    target_locale: str = ""
    project_id: str = ""
    review_stage: str = ReviewStage.FIRST.value
    percent_completed: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UploadResult:
    """将源文件上传到平台后的返回信息。"""

    file_id: str
    revision: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SplitResult:
    """:meth:`TranslationPlatform.split_approved_data` 的返回结果。

    字段：
        approved_path: 已写入已批准译文的本地文件。
        pending_path: 已写入仍然待审校条目的本地文件，空串代表“全部批准”。
        should_continue: 便捷标志，存在已批准译文时为 True；下游状态据此
            判断是否跳过 merge / publish。
        is_complete: 当前审校轮是否已完全完成（无残留条目）；
            与 ``complete`` 字段的语义对齐。
        extra: 平台自定义字段。
    """

    approved_path: str = ""
    pending_path: str = ""
    should_continue: bool = False
    is_complete: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)


class TranslationPlatform(abc.ABC):
    """所有平台适配器需实现的接口。

    适配器作者通常需重写：

    * :meth:`upload_source` / :meth:`create_task`——上传文件并创建审校任务；
    * :meth:`get_task_status` / :meth:`get_task_percent`——轮询任务状态；
    * :meth:`download_translations` / :meth:`import_approved`——拉取已批准译文；
    * :meth:`split_approved_data`——拆分已批准与待审校译文；
    * :meth:`delete_task` / :meth:`get_project_name`——后处理辅助。
    """

    #: 人可读名称（与配置中的 ``platform.type`` 以及 ``@register_platform`` 的 key 一致）。
    platform_name: str = ""

    #: 本适配器可服务的 :class:`~TiMi_HOK_Game_Translator.commons.ReviewStage` 集合；
    #: 空元组代表“支持任意阶段”。
    supports_stages: Tuple[str, ...] = ()

    def __init__(
        self,
        *,
        api_base: str = "",
        api_token: str = "",
        project_id: str = "",
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.api_base = api_base
        self.api_token = api_token
        self.project_id = project_id
        self.extra: Dict[str, Any] = dict(extra or {})

    # ------------------------------------------------------------------
    # 自省辅助
    # ------------------------------------------------------------------
    def supports(self, review_stage: str) -> bool:
        """当本适配器能服务 ``review_stage`` 时返回 True。

        默认实现：:attr:`supports_stages` 为空时总是 True，否则判断是否包含。
        子类可重写以实现更细粒度的判定。
        """
        if not self.supports_stages:
            return True
        return review_stage in self.supports_stages

    # ------------------------------------------------------------------
    # 抽象 API
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def upload_source(self, file_path: str, *, remote_path: str = "") -> UploadResult:
        """上传 ``file_path``，返回平台上的文件记录。"""

    @abc.abstractmethod
    def download_translations(
        self,
        file_id: str,
        target_locale: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        """下载 ``file_id`` 对应 ``target_locale`` 的译文到 ``dest_path``，返回写入的本地路径。"""

    @abc.abstractmethod
    def create_task(
        self,
        file_ids: Sequence[str],
        target_locale: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
        title: str = "",
        description: str = "",
    ) -> TaskInfo:
        """创建一个覆盖指定文件集与语种的审校任务。"""

    @abc.abstractmethod
    def get_task_status(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> TaskInfo:
        """返回 ``task_id`` 当前状态。"""

    @abc.abstractmethod
    def import_approved(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        """将 ``task_id`` 的已批准译文写入 ``dest_path``，返回写入的本地路径。"""

    @abc.abstractmethod
    def export_review_report(
        self,
        task_id: str,
        dest_path: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> str:
        """导出 ``task_id`` 的人可读审校报告。"""

    # ------------------------------------------------------------------
    # 扩展 API（已提供默认实现，简单适配器不必重写）
    # ------------------------------------------------------------------
    def get_task_percent(
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> float:
        """返回 ``task_id`` 的 0..100 完成度。

        默认实现多调一次 :meth:`get_task_status`；如果平台提供更便宜的接口，
        子类可重写。
        """
        info = self.get_task_status(task_id, review_stage=review_stage)
        return info.percent_completed

    def split_approved_data(
        self,
        task_id: str,
        *,
        save_approved_path: str,
        save_pending_path: str = "",
        review_stage: str = ReviewStage.FIRST.value,
    ) -> SplitResult:
        """拉取 ``task_id`` 并拆分为已批准/待审校两份本地文件。

        默认实现：仅调用 :meth:`import_approved` 拿到已批准部分，pending_path 为空。
        当平台能提供更细粒度的数据（Crowdin 的 ``ApprovalStatus`` 列、
        Phrase 的 ``segmentStatus`` 字段）时，子类应重写。
        """
        approved = self.import_approved(
            task_id, save_approved_path, review_stage=review_stage,
        )
        return SplitResult(
            approved_path=approved,
            pending_path="",
            should_continue=bool(approved),
            is_complete=True,
        )

    def delete_task(  # noqa: B027 — 默认空实现即为预期行为
        self,
        task_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> None:
        """删除 ``task_id`` 及其关联的远端文件。

        默认为空实现；当平台提供清理接口且你需要在工作流末尾调用时重写。
        """

    def delete_file(  # noqa: B027 — 默认空实现即为预期行为
        self,
        file_id: str,
        *,
        review_stage: str = ReviewStage.FIRST.value,
    ) -> None:
        """删除平台侧 ``file_id`` 对应的文件（上传过的 xlsx / xml 等）。

        与 :meth:`delete_task` 配对使用，用于防止平台项目目录被已完成/
        已拆分的历史文件无限堆积。默认空实现——仅在平台提供 DELETE
        ``/projects/{pid}/files/{file_id}`` 之类接口时重写。

        调用方应**在删除 task 之后**再删 file，顺序颠倒可能触发平台
        "文件被 task 引用无法删除"的 409 响应。
        """

    def get_project_name(self, project_id: str = "") -> str:
        """返回 ``project_id`` 对应的人可读名称。

        默认直接返回 ``project_id``。适配器如需调用 REST 回填名称，可重写。
        """
        return project_id or self.project_id


__all__ = [
    "SplitResult",
    "TaskInfo",
    "TaskStatus",
    "TranslationPlatform",
    "UploadResult",
]
