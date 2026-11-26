"""``push_multi_vcs`` 状态——发布到额外的目标路径。

将同一份翻译结果发布到多个 VCS 路径/分支。每个目标由
:class:`~TiMi_HOK_Game_Translator.config.LanguageProfile` 上的
:class:`~TiMi_HOK_Game_Translator.config.PublishTarget` 描述。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ...commons import WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase
from .pull_vcs_state import resolve_source_path as _resolve

logger = logging.getLogger(__name__)


class PushMultiVcsState(WorkflowStateBase):
    """遍历 :attr:`LanguageProfile.multi_publish_targets` 逐个发布。

    每个目标的 ``source_path`` 作为 dump 目标。当 ``stages`` 非空时，
    仅当前 :attr:`Config.stage` 命中则执行。
    """

    name = StateEnum.PUSH_MULTI_VCS.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("PushMultiVcsState: already completed — skipping.")
            return None

        profile = ctx.language_profile
        if profile is None or not profile.multi_publish_targets:
            logger.info(
                "PushMultiVcsState: no multi-publish targets configured — skipping.",
            )
            self._mark_completed(ctx)
            return None

        stage = ctx.config.stage
        pushed = []
        for target in profile.multi_publish_targets:
            if target.stages and stage not in target.stages:
                logger.debug(
                    "PushMultiVcsState: target %r does not apply to stage %r",
                    target.name, stage,
                )
                continue
            if not target.source_path:
                logger.warning(
                    "PushMultiVcsState: target %r has empty source_path — skipping.",
                    target.name,
                )
                continue

            resolved = _resolve(ctx, target.source_path)
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            try:
                ctx.source.dump(ctx.entries, resolved)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                ctx.state_payload.setdefault("push_multi_vcs.errors", {})
                ctx.state_payload["push_multi_vcs.errors"][target.name] = repr(exc)
                logger.warning(
                    "PushMultiVcsState: dump failed for target %r: %s",
                    target.name, exc,
                )
                continue

            commit_msg = ctx.config.vcs.default_commit_message
            try:
                ctx.vcs.commit([resolved], message=commit_msg)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "PushMultiVcsState: commit failed for target %r: %s",
                    target.name, exc,
                )
                continue
            pushed.append(target.name)

        ctx.state_payload["push_multi_vcs.pushed"] = pushed
        logger.info(
            "PushMultiVcsState: published to %d target(s): %s",
            len(pushed), pushed,
        )
        self._mark_completed(ctx)
        return None


__all__ = ["PushMultiVcsState"]
