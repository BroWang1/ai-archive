"""``last_merge_data`` 状态——把昨日审完的遗留条目**精确地**分发到今日流水线的各个阶段。

**设计意图**：把一审遗留和二审遗留的 approved 条目精确路由到各自的
"下一个阶段"，而不是统一塞回工作流从头走一遍。

**执行时机**：**在 ``pull_vcs`` + ``translate`` 之后，``first_review`` 之前**。

**为什么要按来源精确路由（而不是全部塞回 ``ctx.entries``）**：

若把三类遗留条目**全部 prepend 到 ``ctx.entries``**——它们会无差别走完
``first_review → second_review → merge_data`` 的完整链。在 TM 100% 命中
的生产场景下尚可（Crowdin 秒 approved），但只要 deadline 过短或 TM 失
配，这些**本来已经审过的条目**会被当成"今日 first/second 的 pending"
再次ۭa进新 tail，造成**无止境的重复审核**。

**按条目来源精确路由**：

* **一审遗留 approved**（``last_review.carry_over_entries``）
  → **根据 profile 是否配置二审动态路由**：

    - 有二审（``reviews.second.platform`` 非空非 ``"none"`` 且 workflow
      包含 ``second_review``）→ 存到 ``last_review.second_only_entries``
      通道 → ``second_review_state`` 在开工前 prepend 到 ``ctx.entries``
      → **跳过 first_review**，走今日 second_review。
      语义：昨天已过一审，今天不该重走一审。

    - 无二审（"仅一审"编排）→ 存到 ``last_review.merge_only_entries``
      通道（和二审 approved 共用） → ``merge_data_state`` 在合入 full 表
      前 prepend 到 ``ctx.entries`` → **跳过所有审核**，直接合入 full 表。
      语义：昨天已过系统的最终审核阶段，今天不该重走任何审核。
      （修复 2026-10-13：旧实现无条件走 second_only 通道，仅一审时数据丢失。）

* **一审遗留 pending**（``last_review.pending_rollover_entries``）
  → **本 state 直接 prepend 到 ``ctx.entries``**
  → 和今日新增一起走 ``first_review``。
  语义：它们昨天没过一审，走一审天经地义。

* **二审遗留 approved**（``last_second_review.carry_over_entries``）
  → 存到 ``last_review.merge_only_entries`` 通道
  → ``merge_data_state`` 在合入 full 表前 prepend 到 ``ctx.entries``
  → **跳过 first_review 和 second_review**，直接合入 full 表。
  语义：昨天已过二审，今天不该重走任何审核。

* **二审遗留 pending**（``last_second_review.pending_rollover_entries``；
  由 :class:`LastSecondReviewState` 直接填充）→ **本 state 不处理**
  → ``second_review_state`` 开工前 prepend 到 ``ctx.entries``
  → **跳过 first_review**，直接走二审。
  语义：昨天已过一审但二审没审完，不该回头重走一审。

执行后清空 ``_FIRST_CARRY_OVER_KEY``、``_SECOND_CARRY_OVER_KEY``、
``_FIRST_PENDING_ROLLOVER_KEY`` 三个 slot，避免二次合入；
``_SECOND_PENDING_ROLLOVER_KEY`` / ``_SECOND_ONLY_ENTRIES`` /
``_MERGE_ONLY_ENTRIES`` 分别由对应的下游 state 自己清。
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from ...commons import ReviewStage
from ...commons import WorkflowState as StateEnum
from ...sources.base import Entry
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)

#: 一审遗留 **approved** 条目的来源通道（由 LastFirstReviewState 填充）。
_FIRST_CARRY_OVER_KEY = "last_review.carry_over_entries"

#: 二审遗留 **approved** 条目的来源通道（由 LastSecondReviewState 填充）。
_SECOND_CARRY_OVER_KEY = "last_second_review.carry_over_entries"

#: 一审遗留 **pending** 条目回流通道（由 LastFirstReviewState 填充）。
#: 本 state 消费 → 合入 ctx.entries → 走今日 first_review。
_FIRST_PENDING_ROLLOVER_KEY = "last_review.pending_rollover_entries"

#: "仅走今日 second_review"通道。
#:
#: 本 state 把一审遗留 approved（它们昨天过了一审）路由到这里 →
#: :class:`SecondReviewState` 在 ``run_review_stage`` 入口处 prepend 到
#: ctx.entries → 跳过 ``first_review``，直接进入二审。
_SECOND_ONLY_ENTRIES_KEY = "last_review.second_only_entries"

#: "直接合入 full 表"通道。
#:
#: 本 state 把二审遗留 approved（它们昨天已过二审）路由到这里 →
#: :class:`MergeDataState` 在合入 full 表前 prepend 到 ctx.entries →
#: 彻底跳过 ``first_review`` + ``second_review``。
_MERGE_ONLY_ENTRIES_KEY = "last_review.merge_only_entries"


class LastMergeDataState(WorkflowStateBase):
    """精确路由昨日遗留条目（根据 profile 审核链路自适应）：

    * 一审 approved：
        - profile 有二审 → 走今日 second_review（跳过一审）
        - profile 仅一审 → 直接合入 full 表（跳过所有审核）
    * 二审 approved → 直接合入 full 表
    * 一审 pending → 回今日 first_review 续审
    """

    name = StateEnum.LAST_MERGE_DATA.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("LastMergeDataState: already completed — skipping.")
            return None

        first_carry = _dict_list_to_entries(
            ctx.state_payload.get(_FIRST_CARRY_OVER_KEY, []) or []
        )
        second_carry = _dict_list_to_entries(
            ctx.state_payload.get(_SECOND_CARRY_OVER_KEY, []) or []
        )
        first_pending_rollover = _dict_list_to_entries(
            ctx.state_payload.get(_FIRST_PENDING_ROLLOVER_KEY, []) or []
        )

        if not first_carry and not second_carry and not first_pending_rollover:
            logger.info("LastMergeDataState: no carry-over entries — skipping.")
            self._mark_completed(ctx)
            return None

        # ------------------------------------------------------------
        # 【修复 2026-10-13】判断本语种 profile 是否配置了二审。
        #
        # 没有二审时（``reviews.second.platform`` 为空或 ``"none"``，或
        # workflow 中不含 ``second_review``），一审 approved 在语义上
        # 等价于"已过所有审核"——必须走和二审 approved 相同的 **直接
        # 合入 full 表**通道（``_MERGE_ONLY_ENTRIES_KEY``），由
        # :class:`MergeDataState` 消费。
        #
        # 否则（历史 bug）：一审 approved 会被路由到
        # ``_SECOND_ONLY_ENTRIES_KEY``，而该通道只在 ``SecondReviewState``
        # 里被消费——没有二审状态时，这批昨日 approved 条目将**永远被遗弃**
        # 在 state_payload 里，既不进 ctx.entries 也不进 full 表、更不被
        # commit 回 VCS，造成数据丢失。
        # ------------------------------------------------------------
        has_second_review = _profile_has_second_review(ctx)
        logger.info(
            "LastMergeDataState: profile has_second_review=%s — first-review "
            "approved carry-over will be routed to %s channel.",
            has_second_review,
            "_SECOND_ONLY_ENTRIES_KEY (→ today's second_review)"
            if has_second_review
            else "_MERGE_ONLY_ENTRIES_KEY (→ merge_data directly, skipping all reviews)",
        )

        # ------------------------------------------------------------
        # 【Rule 2b 精确版】对每条昨日遗留条目做 key 冲突判定：
        #
        #   * **key 不冲突** → 正常路由到对应通道。
        #   * **key 冲突 + source 相同** → **保留昨日版本**，把 ctx.entries
        #     里对应条目**替换**为昨日版本（它承载了审员的部分进度，不该
        #     被今日"又跑了一遍 LLM"的新版本覆盖）。今日版本在 ctx.entries
        #     中被原地替换；不再往通道推。
        #   * **key 冲突 + source 不同** → 丢弃昨日 + WARN。今日策划改了
        #     内容，昨日的译文已失效，必须让今日版本重走翻译/审核。
        #
        # 这是 2026-10-09 方案 ②+ 的修复：旧实现 "key 冲突一律丢弃昨日"
        # 丢数据，哪怕 source 相同、哪怕昨日已走到后半段审核。
        # ------------------------------------------------------------
        today_by_key = {e.key: e for e in ctx.entries}
        # today_entries_mutable 用于支持"原地替换"。list 共享内部对象，但
        # 若替换则需要重建；为了语义清晰，先做一次浅拷贝再操作。
        today_entries_mutable: List[Entry] = list(ctx.entries)
        # 由 key → 在 today_entries_mutable 中的索引，便于 O(1) 替换。
        today_index_by_key = {e.key: i for i, e in enumerate(today_entries_mutable)}

        # 跨所有通道的"全局已见"集合——避免同一个 key 既被替换又被路由。
        # 初始化为今日所有 key，后续路由的新 key 也累积进来。
        existing_keys: set = set(today_by_key)

        # —— 通道 1：一审 pending rollover → 走今日 first_review ——
        first_pending_prepend: List[Entry] = []
        first_pending_replaced = 0
        first_pending_dropped_diff = 0
        for src in first_pending_rollover:
            outcome = _rule2b_route(
                src=src,
                today_by_key=today_by_key,
                today_entries_mutable=today_entries_mutable,
                today_index_by_key=today_index_by_key,
                existing_keys=existing_keys,
            )
            if outcome == "new":
                first_pending_prepend.append(src)
                existing_keys.add(src.key)
            elif outcome == "replaced_in_today":
                first_pending_replaced += 1
            elif outcome == "dropped_diff_source":
                first_pending_dropped_diff += 1

        # —— 通道 2：一审 approved → 根据是否有二审动态选择目标通道 ——
        #
        # 有二审 → _SECOND_ONLY_ENTRIES_KEY（走今日 second_review，跳过 first_review）
        # 无二审 → _MERGE_ONLY_ENTRIES_KEY（直接合入 full 表，跳过所有审核）
        #
        # 【修复 2026-10-13】旧实现无条件写 _SECOND_ONLY_ENTRIES_KEY，在
        # "仅一审"编排下该通道没有消费者 → 数据丢失。
        first_approved_target: List[Entry] = []
        first_approved_replaced = 0
        first_approved_dropped_diff = 0
        for src in first_carry:
            outcome = _rule2b_route(
                src=src,
                today_by_key=today_by_key,
                today_entries_mutable=today_entries_mutable,
                today_index_by_key=today_index_by_key,
                existing_keys=existing_keys,
            )
            if outcome == "new":
                first_approved_target.append(src)
                existing_keys.add(src.key)
            elif outcome == "replaced_in_today":
                first_approved_replaced += 1
            elif outcome == "dropped_diff_source":
                first_approved_dropped_diff += 1

        # —— 通道 3：二审 approved → _MERGE_ONLY_ENTRIES_KEY → 直接合入 full 表 ——
        merge_only: List[Entry] = []
        merge_only_replaced = 0
        merge_only_dropped_diff = 0
        for src in second_carry:
            outcome = _rule2b_route(
                src=src,
                today_by_key=today_by_key,
                today_entries_mutable=today_entries_mutable,
                today_index_by_key=today_index_by_key,
                existing_keys=existing_keys,
            )
            if outcome == "new":
                merge_only.append(src)
                existing_keys.add(src.key)
            elif outcome == "replaced_in_today":
                merge_only_replaced += 1
            elif outcome == "dropped_diff_source":
                merge_only_dropped_diff += 1

        # ------------------------------------------------------------
        # 应用路由。
        # ------------------------------------------------------------
        before = len(ctx.entries)
        # Step A: 先把今日已被替换过的 ctx.entries 写回（可能保留了昨日
        # 版本的 target_text / metadata）。
        ctx.entries = today_entries_mutable

        # Step B: 再把三类"没撞 key"的昨日条目分别 prepend 或路由。
        if first_pending_prepend:
            ctx.entries = first_pending_prepend + list(ctx.entries)

        # 【修复 2026-10-13】一审 approved 的路由目标由 has_second_review 决定。
        if first_approved_target:
            target_key = (
                _SECOND_ONLY_ENTRIES_KEY if has_second_review else _MERGE_ONLY_ENTRIES_KEY
            )
            payload = ctx.state_payload.setdefault(target_key, [])
            payload.extend(_entry_to_dict(e) for e in first_approved_target)

        if merge_only:
            payload = ctx.state_payload.setdefault(_MERGE_ONLY_ENTRIES_KEY, [])
            payload.extend(_entry_to_dict(e) for e in merge_only)

        logger.info(
            "LastMergeDataState: routed carry-over → ctx.entries %d→%d. "
            "first_pending (go to first_review): new=%d, replaced=%d, dropped_diff_source=%d. "
            "first_approved (%s): new=%d, replaced=%d, dropped_diff_source=%d. "
            "merge_only (skip first & second → merge): new=%d, replaced=%d, dropped_diff_source=%d.",
            before, len(ctx.entries),
            len(first_pending_prepend), first_pending_replaced, first_pending_dropped_diff,
            "skip first → second_review" if has_second_review else "skip first & second → merge",
            len(first_approved_target), first_approved_replaced, first_approved_dropped_diff,
            len(merge_only), merge_only_replaced, merge_only_dropped_diff,
        )

        # 清空来源 slot，避免下次 run 再次合入。
        # 注意：**不清** _SECOND_PENDING_ROLLOVER_KEY —— 那是 LastSecondReviewState
        # 直接写、SecondReviewState 直接读的通道，不经本 state 中转。
        # **不清** _SECOND_ONLY_ENTRIES_KEY / _MERGE_ONLY_ENTRIES_KEY ——
        # 它们由各自的下游 state 消费后自清。
        ctx.state_payload.pop(_FIRST_CARRY_OVER_KEY, None)
        ctx.state_payload.pop(_SECOND_CARRY_OVER_KEY, None)
        ctx.state_payload.pop(_FIRST_PENDING_ROLLOVER_KEY, None)

        self._mark_completed(ctx)
        return None


def _rule2b_route(
    *,
    src: Entry,
    today_by_key: dict,
    today_entries_mutable: List[Entry],
    today_index_by_key: dict,
    existing_keys: set,
) -> str:
    """按 Rule 2b 判定昨日条目 ``src`` 的归宿。

    返回值：

    * ``"new"`` —— ``src`` 的 key 不冲突，调用方应把它路由到对应通道；
    * ``"replaced_in_today"`` —— key 冲突 + source 相同；本函数已经把
      ``today_entries_mutable`` 中对应条目替换为 ``src``（保留昨日的
      target_text 和审员进度），调用方不需要再路由；
    * ``"dropped_diff_source"`` —— key 冲突 + source 不同；本函数已打
      WARN，调用方应该直接丢弃 ``src``；
    * ``"dropped_cross_channel"`` —— key 和前一个通道刚插入的条目冲突，
      丢弃（防御性，正常场景下极少触发）。

    副作用：
      * 命中 ``"replaced_in_today"`` 时**原地**替换 ``today_entries_mutable``；
      * 其他情况**不**修改外部参数。``existing_keys`` 由调用方按 ``"new"``
        自行累加。
    """
    key = src.key
    if key not in existing_keys:
        return "new"

    # 优先级 1：和今日 ctx.entries 冲突 —— 做 source 比对决定保留谁。
    today_version = today_by_key.get(key)
    if today_version is not None:
        if today_version.source_text == src.source_text:
            # source 相同 —— 保留昨日版本（它有审员进度，优于今日新跑的 LLM）。
            idx = today_index_by_key[key]
            today_entries_mutable[idx] = src
            # today_by_key 也要同步更新，防止后续通道的"同 key"条目看到
            # 旧版本做出错误判定。
            today_by_key[key] = src
            return "replaced_in_today"
        else:
            # source 不同 —— 今日策划改了内容，昨日已完成的旧译文作废。
            logger.warning(
                "LastMergeDataState: dropping yesterday entry key=%r because "
                "today has the same key with a DIFFERENT source (today's "
                "version wins and will be re-translated/reviewed as a fresh "
                "entry).",
                key,
            )
            return "dropped_diff_source"

    # 优先级 2：没出现在今日 ctx.entries 里，但出现在前面某条通道的
    # new 列表中 —— 跨通道同 key 冲突（如一审 approved 和二审 approved
    # 同 key，正常业务不该发生）。保守丢弃。
    logger.warning(
        "LastMergeDataState: dropping yesterday entry key=%r because it "
        "collides with an earlier channel's entry in the same run.",
        key,
    )
    return "dropped_cross_channel"


def _profile_has_second_review(ctx: WorkflowContext) -> bool:
    """判断当前语种 profile 是否配置了二审（且 workflow 中包含 second_review 状态）。

    判定规则（任一不满足即视为"无二审"）：

    1. profile 的 ``reviews.second.platform`` 非空且 ``!= "none"``；
    2. profile 的 ``workflow`` 中显式包含 ``second_review`` 状态。

    这两点必须同时成立——仅配置平台不足：若 workflow 把 ``second_review``
    状态裁掉了，``_SECOND_ONLY_ENTRIES_KEY`` 通道仍然没人消费。
    """
    profile = ctx.language_profile
    if profile is None:
        return False

    try:
        review_cfg = profile.review(ReviewStage.SECOND.value)
    except Exception:  # pylint: disable=broad-except  # noqa: BLE001 — profile 不规范时保守认为"无二审"
        return False

    platform = (review_cfg.platform or "").strip()
    if not platform or platform == "none":
        return False

    workflow_states = tuple(getattr(profile, "workflow", ()) or ())
    if StateEnum.SECOND_REVIEW.value not in workflow_states:
        return False

    return True

def _entry_to_dict(entry: Entry) -> dict:  # noqa: E302
    """把 :class:`Entry` 序列化成 state_payload 可持久化的 dict。"""
    return {
        "key": entry.key,
        "source_text": entry.source_text,
        "target_text": entry.target_text,
        "context": entry.context,
        "comment": entry.comment,
        "metadata": dict(entry.metadata or {}),
    }


def _dict_list_to_entries(items: Any) -> List[Entry]:
    """把 state_payload 里的 dict 列表反序列化为 :class:`Entry` 列表。"""
    result: List[Entry] = []
    if not isinstance(items, list):
        return result
    for raw in items:
        if not isinstance(raw, dict):
            continue
        try:
            result.append(
                Entry(
                    key=str(raw.get("key", "")),
                    source_text=str(raw.get("source_text", "") or ""),
                    target_text=str(raw.get("target_text", "") or ""),
                    context=str(raw.get("context", "") or ""),
                    comment=str(raw.get("comment", "") or ""),
                    metadata=dict(raw.get("metadata") or {}),
                )
            )
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning("LastMergeDataState: skip malformed carry-over item: %s", exc)
    return result


__all__ = ["LastMergeDataState"]
