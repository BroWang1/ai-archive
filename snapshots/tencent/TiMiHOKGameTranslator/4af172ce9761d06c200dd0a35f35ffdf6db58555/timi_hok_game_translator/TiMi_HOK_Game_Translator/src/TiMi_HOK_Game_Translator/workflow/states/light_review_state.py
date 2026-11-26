"""``light_review`` 状态——正式一审前的轻量审校。

与一审/二审共享平台契约，仅以 ``review_stage="light"`` 区分。
"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import ReviewStage
from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase
from ._review_state_helpers import run_review_stage

logger = logging.getLogger(__name__)


class LightReviewState(WorkflowStateBase):
    """轻度审校：在人工审校看到文件前先做一轮快速 QA。

    若 profile 未配置 ``light`` 阶段（即 ``profile.reviews["light"].platform``
    为空或 ``"none"``）将直接跳过。
    """

    name = StateEnum.LIGHT_REVIEW.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("LightReviewState: already completed — skipping.")
            return None

        profile = ctx.language_profile
        if profile is not None:
            review_cfg = profile.review(ReviewStage.LIGHT.value)
            if not review_cfg.platform or review_cfg.platform == "none":
                logger.info(
                    "LightReviewState: profile has no light-review platform — skipping.",
                )
                self._mark_completed(ctx)
                return None

        run_review_stage(
            ctx,
            review_stage=ReviewStage.LIGHT.value,
            resume_key_prefix="light_review",
        )
        self._mark_completed(ctx)
        return None


__all__ = ["LightReviewState"]
