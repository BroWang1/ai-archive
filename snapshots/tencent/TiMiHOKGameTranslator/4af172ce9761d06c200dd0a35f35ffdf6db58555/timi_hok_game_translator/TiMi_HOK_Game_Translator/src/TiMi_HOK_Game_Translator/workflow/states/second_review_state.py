"""``second_review`` 状态——二次审校。"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import ReviewStage
from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase
from ._review_state_helpers import run_review_stage

logger = logging.getLogger(__name__)


class SecondReviewState(WorkflowStateBase):
    """使用为 :class:`ReviewStage.SECOND` 配置的平台执行二次审校。

    若语种不需要二审，只需从 :attr:`LanguageProfile.workflow` 中去掉本状态；
    本状态在 stage 配置缺失时会开缓跳过，不会硬性报错。
    """

    name = StateEnum.SECOND_REVIEW.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("SecondReviewState: already completed — skipping.")
            return None

        profile = ctx.language_profile
        if profile is not None:
            review_cfg = profile.review(ReviewStage.SECOND.value)
            if not review_cfg.platform or review_cfg.platform == "none":
                logger.info(
                    "SecondReviewState: profile has no second-review platform — skipping.",
                )
                self._mark_completed(ctx)
                return None

        run_review_stage(
            ctx,
            review_stage=ReviewStage.SECOND.value,
            resume_key_prefix="second_review",
        )
        self._mark_completed(ctx)
        return None


__all__ = ["SecondReviewState"]
