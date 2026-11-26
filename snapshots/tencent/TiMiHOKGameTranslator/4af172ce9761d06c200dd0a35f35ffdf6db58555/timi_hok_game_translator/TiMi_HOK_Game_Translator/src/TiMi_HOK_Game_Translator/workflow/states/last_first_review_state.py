"""``last_first_review`` 状态——处理上一日一审遗留的尾巴 task。

"尾巴 task" 指上一日 ``first_review`` 轮询到 stop_time 仍未审完 → 由
:mod:`_review_state_helpers` 立即新建的"装载 pending 条目"的平台任务。
它的 task_id 存在**跨批次持久化**的
:class:`~.._tail_tasks.TailTaskStore`（``workspace/last_tasks.json``）里。

本 state 在当天 run 的最前面被调度（``pull_vcs`` 之前）。它的职责是：

1. 读 ``last_tasks.json`` → 若 ``first_review`` slot 为空，直接跳过；
2. 若有 ``task_id`` → 调 ``split_approved_data`` 继续按条目拆：
   * **approved 条目** → 累积到 ``ctx.state_payload["last_review.carry_over_entries"]``，
     由后续 :class:`LastMergeDataState` 合入 ``ctx.entries`` 和今日新增一起走流程；
   * **pending 条目** → 回流到 ``ctx.state_payload["last_review.pending_rollover_entries"]``
     → 由后续 :class:`LastMergeDataState` prepend 到 ``ctx.entries``
     → 和今日新增条目**合并进同一个大 first_review task**；
3. 清理旧尾巴 task + file（内容已安全备份到 state_payload），清空 slot。

**为什么本 state 不自己建新尾巴 task**：若在当日 run 内把 pending 条目立即
新建尾巴 task，并写回 ``last_tasks.json[first_review]`` slot，会被当日
``first_review`` 阶段的 ``_create_tail_task`` 覆盖 → **前者成为平台孤儿 task+file**
（既不被 last_tasks.json 追踪、也不被回收）。因此本 state 不调 ``tail_store.put``，
整个 run 中只有 ``first_review`` 的 roll-over 会写一次 slot。

**不丢数据保证**：pending 条目在 ``delete_task`` 前就已经被解包装成
``Entry`` 存到了 ``state_payload``；即使平台端 delete 失败，内存
 payload 也会被 runner 持久化到 ``project_run_data.json``，下次 run 可
从 ``last_merge_data`` 恢复。
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
from ._review_state_helpers import _notify, _resolve_lang  # noqa: PLC2701 — 内部共享辅助

logger = logging.getLogger(__name__)

#: 一审遗留在 state_payload 里累积的 approved 条目 key
_CARRY_OVER_KEY = "last_review.carry_over_entries"

#: 一审遗留 **pending** 条目回流通道。
#:
#: 本通道的设计暂身：若在当日 run 内把 pending 条目立即新建尾巴
#: task，并把 task_id 写回 ``last_tasks.json[first_review]`` —— 该 slot
#: 在同一次 run 内会被 ``first_review`` 阶段的 ``_create_tail_task`` 覆盖，
#: 导致旧 pending 的平台 task+file 成为**孤儿**。
#: 现方案：pending 条目从 pending_xlsx 读回 Entry → prepend 到 ctx.entries →
#: 跟今日新增条目**合并成一个大 task** 上传。slot 在本 state 不再被 put，
#: 整个 run 中只会被 ``first_review`` 的 roll-over 写一次 —— 杜绝孤儿。
_PENDING_ROLLOVER_KEY = "last_review.pending_rollover_entries"

#: 当前阶段枚举值。
_STAGE = ReviewStage.FIRST.value


class LastFirstReviewState(WorkflowStateBase):
    """接回上一日一审遗留的尾巴 task 并继续按条目拆分。"""

    name = StateEnum.LAST_FIRST_REVIEW.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("LastFirstReviewState: already completed — skipping.")
            return None

        tail_store = TailTaskStore(
            Path(ctx.workspace),
            lang=_resolve_lang(ctx),
        )
        record = tail_store.get(_STAGE)
        if not record:
            logger.info(
                "LastFirstReviewState: no tail task in last_tasks.json[%s] — skipping.",
                _STAGE,
            )
            self._mark_completed(ctx)
            return None

        task_id = str(record.get("task_id") or "")
        if not task_id:
            logger.warning(
                "LastFirstReviewState: last_tasks.json[%s] has no task_id — clearing slot.",
                _STAGE,
            )
            tail_store.clear(_STAGE)
            self._mark_completed(ctx)
            return None

        logger.info(
            "LastFirstReviewState: processing tail task_id=%s (batch=%s, pending=%s)",
            task_id, record.get("batch_name", ""), record.get("pending_count", ""),
        )

        profile = ctx.language_profile
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
        batch_name = str(record.get("batch_name") or "")
        if not batch_name:
            # 极端情况：旧记录缺字段。回退到 "last_<stage>_<task_id>"。
            batch_name = f"last_{_STAGE}_{task_id}"

        # 1. split_approved_data —— 按条目拆分
        # 命名约定（2026-10-09 对齐 first_review state 的中文命名）：
        #   目录：workspace/batches/<batch>/first_review/   （和 Day-1 同一目录，便于审员追溯批次）
        #   文件：<batch>_第一轮审核_approved.xlsx / _pending.xlsx
        # 这样 Day-N 的 roll-over 文件和 Day-1 原始文件在同一目录、同一前缀，
        # 只是 _pending.xlsx 的时间戳后缀会递增（由 _roll_over_tail 处理）。
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
            "LastFirstReviewState: tail split → approved=%d, pending=%d, is_complete=%s",
            len(approved_keys), len(pending_keys), split.is_complete,
        )

        # 2. 已审部分 → 读 approved xlsx → 作为"遗留结转条目"存入 state_payload，
        #    让 LastMergeDataState 稍后合入 ctx.entries。
        if approved_keys and approved_xlsx.exists():
            try:
                carried = XlsxSource(encoding="utf-8").load(str(approved_xlsx))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "LastFirstReviewState: failed to read %s (%s); carry-over will be empty.",
                    approved_xlsx, exc,
                )
                carried = []
            payload = ctx.state_payload.setdefault(_CARRY_OVER_KEY, [])
            payload.extend(_entry_to_dict(e) for e in carried)
            logger.info(
                "LastFirstReviewState: carried %d approved entries forward (total carry-over=%d).",
                len(carried), len(payload),
            )

        # 3. pending 非空 → 把条目回流到 state_payload（由 last_merge_data
        #    合入 ctx.entries 的头部），**不再在当日建新尾巴 task**。
        #    这是 2026-10-09 方案 ①-🅱 的核心修复：
        #    * 旧实现在同一次 run 内 last_first_review + first_review 都会
        #      ``tail_store.put(first_review, ...)``，后者覆盖前者 → 前者
        #      的 Crowdin task+file 成为孤儿（见 _PENDING_ROLLOVER_KEY 的
        #      注释）。
        #    * 新实现：pending 回流 ctx.entries → 和今日新增一起被 first_review
        #      大 task 承载 → run 内 slot 只被 first_review 的 roll-over 写
        #      一次 → 杜绝孤儿。
        if pending_keys and pending_xlsx.exists():
            try:
                rolled = XlsxSource(encoding="utf-8").load(str(pending_xlsx))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "LastFirstReviewState: failed to read pending xlsx %s (%s); "
                    "pending roll-over will be empty — THIS LOSES %d ENTRIES, investigate ASAP.",
                    pending_xlsx, exc, len(pending_keys),
                )
                rolled = []
            payload = ctx.state_payload.setdefault(_PENDING_ROLLOVER_KEY, [])
            payload.extend(_entry_to_dict(e) for e in rolled)
            logger.info(
                "LastFirstReviewState: rolled over %d pending entries into "
                "state_payload[%s] (will be merged into ctx.entries by last_merge_data).",
                len(rolled), _PENDING_ROLLOVER_KEY,
            )

        # 4. 无论 pending 是否存在：现在都要**清理旧 task + 旧 file + 清空 slot**。
        #    * approved 已通过 state_payload[_CARRY_OVER_KEY] 回流；
        #    * pending 已通过 state_payload[_PENDING_ROLLOVER_KEY] 回流；
        #    → 旧 Crowdin task 和 file 的全部内容都已安全备份到内存+payload，
        #      可以放心删除。slot 清空后，first_review 阶段的 roll-over
        #      才是本 run 唯一的 slot 写入者。
        tail_store.clear(_STAGE)
        try:
            platform.delete_task(task_id, review_stage=_STAGE)
            logger.info(
                "LastFirstReviewState: deleted old tail task_id=%s on platform=%s "
                "(approved=%d carried over, pending=%d rolled into ctx.entries).",
                task_id, platform.platform_name,
                len(approved_keys), len(pending_keys),
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "LastFirstReviewState: delete_task(%s) failed (continuing — "
                "content already backed up to state_payload): %s",
                task_id, exc,
            )
        old_file_id = str(record.get("file_id") or "")
        if old_file_id:
            try:
                platform.delete_file(old_file_id, review_stage=_STAGE)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "LastFirstReviewState: delete_file(%s) failed (continuing): %s",
                    old_file_id, exc,
                )

        _notify(
            ctx,
            _STAGE,
            f"📝 【{ctx.config.project_code}】昨日一审续审任务已处理\n"
            f"任务 ID：{task_id}\n"
            f"✅ 已通过：{len(approved_keys)} 条\n"
            f"⏭️ 滚入下轮：{len(pending_keys)} 条",
        )
        self._mark_completed(ctx)
        return None


def _entry_to_dict(entry: Any) -> Dict[str, Any]:
    """把 :class:`Entry` 序列化成 JSON 安全的 dict（供 state_payload 落盘）。

    state_payload 要能被 StatesManager 序列化到 ``workflow_state.json``，
    因此不能直接存 Entry dataclass 对象。
    """
    return {
        "key": entry.key,
        "source_text": entry.source_text,
        "target_text": entry.target_text,
        "context": entry.context,
        "comment": entry.comment,
        "metadata": dict(entry.metadata or {}),
    }


__all__ = ["LastFirstReviewState"]
