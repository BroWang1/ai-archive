"""``validate_data`` 状态——发布前的最后校验。"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)


class ValidateDataState(WorkflowStateBase):
    """验证已翻译条目是否满足基本质量门禁。

    内置实现执行三项检查：

    * 每个条目的 ``key`` 不为空；
    * 经 :class:`TranslateState` 处理的条目均应具备 ``target_text``（
      未命中仅汇总，不会抛异常）；
    * 对重复 key 报警。

    真实项目可能需要更丰富的检查（占位符一致、HTML 标签平衡、
    术语合规性），可继承并覆写 :meth:`execute` 添加。
    """

    name = StateEnum.VALIDATE_DATA.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("ValidateDataState: already completed — skipping.")
            return None

        missing_keys: list = []
        empty_target: list = []
        seen_keys: dict = {}
        duplicates: list = []

        for entry in ctx.entries:
            if not entry.key:
                missing_keys.append(entry.source_text[:40])
                continue
            if entry.key in seen_keys:
                duplicates.append(entry.key)
            seen_keys[entry.key] = True
            if not entry.target_text:
                empty_target.append(entry.key)

        ctx.state_payload["validate_data.missing_keys"] = missing_keys
        ctx.state_payload["validate_data.empty_target_keys"] = empty_target
        ctx.state_payload["validate_data.duplicate_keys"] = duplicates
        ctx.state_payload["validate_data.total"] = len(ctx.entries)

        if missing_keys or duplicates:
            logger.warning(
                "ValidateDataState: %d entries missing keys, %d duplicates.",
                len(missing_keys), len(duplicates),
            )
        if empty_target:
            logger.info(
                "ValidateDataState: %d entries still empty (untranslated).",
                len(empty_target),
            )
        logger.info("ValidateDataState: checked %d entries.", len(ctx.entries))

        self._mark_completed(ctx)
        return None


__all__ = ["ValidateDataState"]
