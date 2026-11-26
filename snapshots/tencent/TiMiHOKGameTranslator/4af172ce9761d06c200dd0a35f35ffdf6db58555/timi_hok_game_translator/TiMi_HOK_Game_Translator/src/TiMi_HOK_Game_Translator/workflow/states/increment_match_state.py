"""``increment_match`` 状态——按阈值触发增量 TM 命中。

当当日增量汉字（或更广义的“源语言字符”）总量超过配置阈值时，
多跑一轮预翻译 TM 匹配，提高命中率后再调用 LLM。

默认实现**仅统计**增量大小；阈值来自
``profile.strategy_config["increment_match_threshold"]``（默认 0，表示禁用）。
真正的 TM sweep 通过子类实现。
"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)


class IncrementMatchState(WorkflowStateBase):
    """测量增量输入并（可选）触发 TM sweep。"""

    name = StateEnum.INCREMENT_MATCH.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("IncrementMatchState: already completed — skipping.")
            return None

        profile = ctx.language_profile
        threshold = 0
        if profile is not None:
            threshold = int(profile.strategy_config.get("increment_match_threshold", 0) or 0)

        total_source_chars = sum(len(e.source_text or "") for e in ctx.entries)
        triggered = threshold > 0 and total_source_chars >= threshold

        ctx.state_payload["increment_match.total_source_chars"] = total_source_chars
        ctx.state_payload["increment_match.threshold"] = threshold
        ctx.state_payload["increment_match.triggered"] = triggered

        if triggered:
            logger.info(
                "IncrementMatchState: threshold %d exceeded (chars=%d) — "
                "subclass to plug in an incremental TM sweep.",
                threshold, total_source_chars,
            )
        else:
            logger.info(
                "IncrementMatchState: below threshold (chars=%d, threshold=%d) — skipping sweep.",
                total_source_chars, threshold,
            )

        self._mark_completed(ctx)
        return None


__all__ = ["IncrementMatchState"]
