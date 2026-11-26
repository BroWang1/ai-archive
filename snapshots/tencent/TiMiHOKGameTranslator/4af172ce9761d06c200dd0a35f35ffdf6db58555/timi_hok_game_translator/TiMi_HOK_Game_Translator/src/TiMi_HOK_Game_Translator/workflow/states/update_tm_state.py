"""``update_tm`` 状态——向**一审平台**的默认 TM 库回灌历史已审译文。

**运行时机**：在 ``first_review`` 状态**之前**执行。流程：

1. 根据 :attr:`LanguageProfile.reviews` 的 ``first`` 阶段配置构造一审平台
   adapter（Phrase / Crowdin / ...）；
2. 扫描 ``<workspace>/batches/<lang>_*/first_review/*_approved.xlsx``
   汇总历史已审 ``(source, target)`` 对；
3. 产出 ``<workspace>/tm/<lang>_first_tm.xlsx`` 两列 TM 文件；
4. 调 ``platform.upload_tm(file, target_locale=...)`` 完成"先清后传"：
   先 ``clear_tm_segments`` 清空项目默认 TM，再 ``import`` 当前文件。

**失败处理**：全程 try/except —— TM 回灌失败只记告警 + 不阻塞主流程
（审校员仍能在平台 UI 做审校，只是看不到 TM 参考而已）。

**可选扩展**：目标 adapter **未实现** ``upload_tm`` 时跳过并记告警日志；
这意味着自定义平台不需要支持 TM，只需实现 `` TranslationPlatform`` 抽象方法。

**跳过条件**：
    * reviews.first.platform == "none" / 未配置 → 跳过；
    * batches 下无任何历史已审文件 → 跳过（没数据可灌）；
    * platform adapter 没有 ``upload_tm`` 方法 → 跳过并告警。
"""

from __future__ import annotations

import logging
from typing import Optional

from ...commons import PlatformType, ReviewStage, WorkflowState as StateEnum
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)


class UpdateTmState(WorkflowStateBase):
    """向一审平台的默认 TM 库回灌历史已审译文。"""

    name = StateEnum.UPDATE_TM.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("UpdateTmState: already completed — skipping.")
            return None

        _run_tm_upload(
            ctx=ctx,
            review_stage=ReviewStage.FIRST.value,
            state_label="UpdateTmState",
        )
        self._mark_completed(ctx)
        return None


def _run_tm_upload(
    *,
    ctx: WorkflowContext,
    review_stage: str,
    state_label: str,
) -> None:
    """共享的 TM 回灌主流程，供一审/二审两个 state 复用。

    全程不抛异常——任何环节失败都转为 warning 日志，让主流程继续。
    """
    from pathlib import Path
    from ...platforms.factory import build_review_tool
    from ...utils.tm_file_builder import build_tm_file_for_stage

    profile = ctx.language_profile
    if profile is None:
        logger.info("%s: no language profile bound, skip.", state_label)
        return

    review_cfg = profile.review(review_stage)
    if (review_cfg.platform or PlatformType.NONE.value) == PlatformType.NONE.value:
        logger.info(
            "%s: reviews.%s.platform is 'none', skip TM upload.",
            state_label, review_stage,
        )
        return

    target_locale = profile.target_locale or ctx.config.target_locale
    source_locale = profile.source_locale or ctx.config.source_locale or "zh-CN"
    if not target_locale:
        logger.warning("%s: target_locale is empty, skip.", state_label)
        return

    workspace = Path(ctx.workspace)

    # 1) 聚合历史已审文件 → TM xlsx
    tm_file = build_tm_file_for_stage(
        workspace=workspace,
        target_locale=target_locale,
        source_locale=source_locale,
        review_stage=review_stage,
    )
    if tm_file is None:
        logger.info(
            "%s: no historical approved entries found for %s/%s, skip "
            "(this is normal for first run).",
            state_label, target_locale, review_stage,
        )
        return

    # 2) 构造 adapter；复用 build_review_tool 工厂，自动走 Phrase / Crowdin 等
    try:
        platform = build_review_tool(
            profile,
            review_stage,
            global_platform=ctx.config.platform,
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "%s: failed to build review tool for stage=%s: %s",
            state_label, review_stage, exc,
        )
        return

    # 3) 平台没实现 TM 能力 → 跳过
    if not hasattr(platform, "upload_tm"):
        logger.warning(
            "%s: platform=%s does not implement upload_tm, skip "
            "(TM pre-fill is optional).",
            state_label, getattr(platform, "platform_name", "?"),
        )
        return

    # 4) 上传。upload_tm 内部已 try/except + 返回 bool，这里只记结果日志。
    try:
        ok = platform.upload_tm(
            str(tm_file),
            target_locale=target_locale,
        )
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 双保险
        logger.warning(
            "%s: upload_tm raised unexpectedly (continuing): %s",
            state_label, exc,
        )
        return

    if ok:
        logger.info(
            "%s: TM upload succeeded (platform=%s, file=%s).",
            state_label, platform.platform_name, tm_file,
        )
    else:
        logger.warning(
            "%s: TM upload returned False (platform=%s, file=%s); "
            "pipeline continues.",
            state_label, platform.platform_name, tm_file,
        )


__all__ = ["UpdateTmState", "_run_tm_upload"]
