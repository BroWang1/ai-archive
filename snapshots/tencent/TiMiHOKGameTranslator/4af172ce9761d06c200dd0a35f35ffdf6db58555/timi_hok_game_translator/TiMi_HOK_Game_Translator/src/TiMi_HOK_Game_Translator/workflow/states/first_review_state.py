"""``first_review`` 状态——一次式审校首轮。"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import ReviewStage
from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase
from ._review_state_helpers import run_review_stage

logger = logging.getLogger(__name__)


class FirstReviewState(WorkflowStateBase):
    """使用为 :class:`ReviewStage.FIRST` 配置的平台执行首轮审校。"""

    name = StateEnum.FIRST_REVIEW.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("FirstReviewState: already completed — skipping.")
            return None
        run_review_stage(
            ctx,
            review_stage=ReviewStage.FIRST.value,
            resume_key_prefix="first_review",
        )
        self._mark_completed(ctx)
        return None


__all__ = ["FirstReviewState"]
