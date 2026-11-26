"""``last_second_review`` 状态——处理上一日二审遗留的尾巴 task。

骨架与 :class:`~.last_first_review_state.LastFirstReviewState` 相同，
但目标 slot 是 :attr:`ReviewStage.SECOND`。若 profile 未配置二审平台
（``platform == "none"``），本 state 直接跳过。

**与一审的关键差异**：

* **approved 条目** → ``last_second_review.carry_over_entries``
  → 由 :class:`LastMergeDataState` 合入 ``ctx.entries``。
  （语义上已过二审，应该跳过今日 first/second。当前简化实现是
  合入 ``ctx.entries`` 走完整工作流——见 :class:`LastMergeDataState`
  的 docstring）。
* **pending 条目** → ``last_second_review.pending_rollover_entries``
  → 由 ``second_review`` 阶段在开始工作前把它们 prepend 到
  ``ctx.entries`` → **跳过今日 first_review**，直接进入 second_review。
  核心语义：二审的 pending 本来就已经过了 first，不应该回头重走
  first_review。

**消除孤儿 task 的理由**：若在当日把 pending 立即建新尾巴 task 并写
``last_tasks.json[second_review]``，该 slot 会被当日 ``second_review`` 阶
段覆盖 → **前者成为平台孤儿**。因此本 state 不调 ``tail_store.put``，
整个 run 中只有 ``second_review`` 的 roll-over 会写一次 slot。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...commons import ReviewStage
from ...commons import WorkflowState as StateEnum
from ...platforms.factory import build_review_tool
from ...sources import XlsxSource
from .._tail_tasks import TailTaskStore
from ..state import WorkflowContext, WorkflowStateBase
from ._review_state_helpers import _notify, _resolve_lang  # noqa: PLC2701

logger = logging.getLogger(__name__)

_STAGE = ReviewStage.SECOND.value

#: 二审遗留 approved 条目在 state_payload 中的落位——交给
#: :class:`LastMergeDataState` 合入 ctx.entries。
_SECOND_CARRY_OVER_KEY = "last_second_review.carry_over_entries"

#: 二审遗留 **pending** 条目回流通道。
#:
#: pending 条目解包装成 Entry 存到 state_payload，由今日
#: ``second_review`` 阶段在开工前 prepend 到 ``ctx.entries``，跳过
#: ``first_review`` 直接参与二审。slot 在本 run 内只被
#: ``second_review`` 的 roll-over 写一次，没有覆盖，没有孤儿。
_SECOND_PENDING_ROLLOVER_KEY = "last_second_review.pending_rollover_entries"


class LastSecondReviewState(WorkflowStateBase):
    """接回上一日二审遗留的尾巴 task 并继续按条目拆分。"""

    name = StateEnum.LAST_SECOND_REVIEW.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("LastSecondReviewState: already completed — skipping.")
            return None

        profile = ctx.language_profile
        if profile is not None:
            review_cfg = profile.review(_STAGE)
            if not review_cfg.platform or review_cfg.platform == "none":
                logger.info(
                    "LastSecondReviewState: no second-review platform configured — skipping.",
                )
                self._mark_completed(ctx)
                return None

        tail_store = TailTaskStore(
            Path(ctx.workspace),
            lang=_resolve_lang(ctx),
        )
        record = tail_store.get(_STAGE)
        if not record:
            logger.info(
                "LastSecondReviewState: no tail task in last_tasks.json[%s] — skipping.",
                _STAGE,
            )
            self._mark_completed(ctx)
            return None

        task_id = str(record.get("task_id") or "")
        if not task_id:
            logger.warning(
                "LastSecondReviewState: last_tasks.json[%s] has no task_id — clearing slot.",
                _STAGE,
            )
            tail_store.clear(_STAGE)
            self._mark_completed(ctx)
            return None

        logger.info(
            "LastSecondReviewState: processing tail task_id=%s (batch=%s, pending=%s)",
            task_id, record.get("batch_name", ""), record.get("pending_count", ""),
        )

        platform = build_review_tool(
            profile,
            _STAGE,
            global_platform=ctx.config.platform,
        )
        target_locale = (  # pylint: disable=unused-variable
            (profile.target_locale if profile else "")
            or ctx.config.target_locale
            or record.get("target_locale", "")
        )
        batch_name = str(record.get("batch_name") or f"last_{_STAGE}_{task_id}")

        # 命名约定（2026-10-09 对齐 second_review state 的中文命名）：
        #   目录：workspace/batches/<batch>/second_review/
        #   文件：<batch>_第二轮审核_approved.xlsx / _pending.xlsx
        from ...platforms._batch import stage_dir, stage_file_stem  # noqa: WPS433
        last_dir = stage_dir(Path(ctx.workspace), batch_name, _STAGE)
        stem = stage_file_stem(batch_name, _STAGE)
        approved_xlsx = last_dir / f"{stem}_approved.xlsx"
        pending_xlsx = last_dir / f"{stem}_pending.xlsx"

        split = platform.split_approved_data(
            task_id,
            save_approved_path=str(approved_xlsx),
            save_pending_path=str(pending_xlsx),
            review_stage=_STAGE,
        )
        approved_keys: List[str] = list(split.extra.get("approved_keys", []) or [])
        pending_keys: List[str] = list(split.extra.get("pending_keys", []) or [])
        logger.info(
            "LastSecondReviewState: tail split → approved=%d, pending=%d, is_complete=%s",
            len(approved_keys), len(pending_keys), split.is_complete,
        )

        # approved → 落到 state_payload，由 last_merge_data 合入 ctx.entries
        if approved_keys and approved_xlsx.exists():
            try:
                carried = XlsxSource(encoding="utf-8").load(str(approved_xlsx))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "LastSecondReviewState: failed to read %s (%s); carry-over will be empty.",
                    approved_xlsx, exc,
                )
                carried = []
            payload = ctx.state_payload.setdefault(_SECOND_CARRY_OVER_KEY, [])
            payload.extend(_entry_to_dict(e) for e in carried)
            logger.info(
                "LastSecondReviewState: carried %d approved entries forward (total=%d).",
                len(carried), len(payload),
            )

        # pending → 解包装成 Entry 存到 state_payload 的**二审专用回流通道**
        #    → 由今日 second_review 在开工前 prepend 到 ctx.entries → 跳过
        #    first_review 直接走二审。
        #
        #    2026-10-09 方案 ①-🅱 核心修复：不再当日建新 tail task，彻底
        #    消除"本 state 和 second_review 都 put slot、后者覆盖前者→孤儿"
        #    的 bug。见 _SECOND_PENDING_ROLLOVER_KEY 的注释。
        if pending_keys and pending_xlsx.exists():
            try:
                rolled = XlsxSource(encoding="utf-8").load(str(pending_xlsx))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "LastSecondReviewState: failed to read pending xlsx %s (%s); "
                    "pending roll-over will be empty — THIS LOSES %d ENTRIES, investigate ASAP.",
                    pending_xlsx, exc, len(pending_keys),
                )
                rolled = []
            payload = ctx.state_payload.setdefault(_SECOND_PENDING_ROLLOVER_KEY, [])
            payload.extend(_entry_to_dict(e) for e in rolled)
            logger.info(
                "LastSecondReviewState: rolled over %d pending entries into "
                "state_payload[%s] (will be prepended to ctx.entries by second_review, "
                "bypassing first_review).",
                len(rolled), _SECOND_PENDING_ROLLOVER_KEY,
            )

        # 无论 pending 是否存在：都要清理旧 task + 旧 file + 清空 slot。
        # approved 已通过 state_payload[_SECOND_CARRY_OVER_KEY] 回流；
        # pending 已通过 state_payload[_SECOND_PENDING_ROLLOVER_KEY] 回流。
        # 旧 Crowdin task 和 file 的全部内容都已安全备份，可以放心删除。
        tail_store.clear(_STAGE)
        try:
            platform.delete_task(task_id, review_stage=_STAGE)
            logger.info(
                "LastSecondReviewState: deleted old tail task_id=%s on platform=%s "
                "(approved=%d carried over, pending=%d rolled over for direct second_review).",
                task_id, platform.platform_name,
                len(approved_keys), len(pending_keys),
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "LastSecondReviewState: delete_task(%s) failed (continuing — "
                "content already backed up to state_payload): %s",
                task_id, exc,
            )
        old_file_id = str(record.get("file_id") or "")
        if old_file_id:
            try:
                platform.delete_file(old_file_id, review_stage=_STAGE)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "LastSecondReviewState: delete_file(%s) failed (continuing): %s",
                    old_file_id, exc,
                )

        _notify(
            ctx,
            _STAGE,
            f"📝 【{ctx.config.project_code}】昨日二审续审任务已处理\n"
            f"任务 ID：{task_id}\n"
            f"✅ 已通过：{len(approved_keys)} 条\n"
            f"⏭️ 滚入下轮：{len(pending_keys)} 条",
        )
        self._mark_completed(ctx)
        return None


def _entry_to_dict(entry: Any) -> Dict[str, Any]:
    """把 :class:`Entry` 序列化成 JSON 安全的 dict。"""
    return {
        "key": entry.key,
        "source_text": entry.source_text,
        "target_text": entry.target_text,
        "context": entry.context,
        "comment": entry.comment,
        "metadata": dict(entry.metadata or {}),
    }


__all__ = ["LastSecondReviewState"]
