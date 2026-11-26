"""``update_grn_tm`` 状态——向**二审平台**的默认 TM 库回灌历史已审译文。

与 :class:`~TiMi_HOK_Game_Translator.workflow.states.update_tm_state.UpdateTmState`
的唯一差别是 ``review_stage``：

    * ``update_tm`` → ``first_review`` 阶段的 TM（通常走 Phrase）；
    * ``update_grn_tm`` → ``second_review`` 阶段的 TM（通常走 Crowdin）。

两者**互不交叉**：一审平台的 TM 只写一审已审数据，二审平台的 TM 只写二审
已审数据，避免轮次污染。

**运行时机**：在 ``second_review`` 状态**之前**执行。
"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import ReviewStage, WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase
from .update_tm_state import _run_tm_upload

logger = logging.getLogger(__name__)


class UpdateGrnTmState(WorkflowStateBase):
    """向二审平台的默认 TM 库回灌历史已审译文（二审 = GRN）。"""

    name = StateEnum.UPDATE_GRN_TM.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("UpdateGrnTmState: already completed — skipping.")
            return None

        _run_tm_upload(
            ctx=ctx,
            review_stage=ReviewStage.SECOND.value,
            state_label="UpdateGrnTmState",
        )
        self._mark_completed(ctx)
        return None


__all__ = ["UpdateGrnTmState"]
