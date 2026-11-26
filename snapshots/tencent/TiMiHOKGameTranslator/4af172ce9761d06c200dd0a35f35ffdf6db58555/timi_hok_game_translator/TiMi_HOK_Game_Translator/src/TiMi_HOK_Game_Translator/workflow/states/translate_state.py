"""``translate`` 状态——运行当前语种的翻译策略。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from ...commons import WorkflowState as StateEnum
from ...translation import get_translation_strategy
from ...utils import (
    collapse_by_source,
    filter_against_pending,
    load_pending_source_pairs,
    save_incr_snapshot,
)
from .._tail_tasks import TailTaskStore
from ..state import WorkflowContext, WorkflowStateBase
from ._review_state_helpers import _resolve_lang  # noqa: PLC2701 — 共享 helper

logger = logging.getLogger(__name__)


#: state_payload 中记录"今日 incr 完整快照"路径的 key，供 review 阶段扩散时读。
_SNAPSHOT_PATH_KEY = "translate.incr_snapshot_path"
#: state_payload 中记录"因 (key,source) 命中昨日 pending 而被屏蔽的 key 列表"。
_SHADOWED_BY_PENDING_KEY = "translate.shadowed_by_pending_keys"
#: state_payload 中记录"因 key 已存在于全量表而被剔除"的 key 列表。
#: ``merge_data`` 会消费它，从磁盘上的 incr 文件物理删除对应条目——
#: 避免下次 run 的 pull_vcs 又把它们捞回来陷入"每天过滤一次"的脏循环。
_SHADOWED_BY_FULL_TABLE_KEY = "translate.shadowed_by_full_table_keys"


class TranslateState(WorkflowStateBase):
    """就地翻译 :attr:`WorkflowContext.entries` 中的每一条。

    在调用策略翻译前做**三项前置清洗**——对齐生产场景的数据一致性要求：
    滤掉 ``need_approve_summary_path`` 中 Origin 已存在的条目，
    并 ``drop_duplicates(subset=["Origin"])`` 按源语文本折叠：

    0. 若已标完成则跳过（断点续跑，译文从 state_data 还原）；
    1. **保存今日 incr 的完整快照**到
       ``workspace/batches/<batch>/translate/incr_snapshot.xlsx``——含**所有**
       entries（包括同 source 的兄弟行），供后续 review 阶段扩散时回捞；
    2. **按 (key, source) 对昨日 pending 做一致性过滤**：
       * 完全一致 → 屏蔽今日版本（避免 Crowdin 侧出现同 (key,source) 双 task）；
       * 同 key 不同 source → 保留今日版本并 WARN（source 已更新，重译）；
    3. **按 source_text 折叠**：同 source 多条只留第一条作代表走 LLM/审核，
       兄弟暂存在快照里，审完后由 ``_review_state_helpers`` 扩散回 ctx.entries；
    4. 为当前语种构造 :class:`BaseTranslationStrategy` 跑翻译；
    5. 把译文回写 ``ctx.entries``、持久化到 state_data；
    6. 标为已完成。
    """

    name = StateEnum.TRANSLATE.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            # 断点续跑：跳过 LLM 调用，但从 state_data 恢复译文到内存
            # ``ctx.entries``。``ctx.entries`` 本身不持久化，因此必须回填
            # 下游 review / merge_data / push_vcs 才能拿到翻译结果。
            stored = ctx.state_data.get("translate.translations") or {}
            if stored and ctx.entries:
                hits = 0
                for entry in ctx.entries:
                    tgt = stored.get(entry.key, "")
                    if tgt and not entry.target_text:
                        entry.target_text = tgt
                        hits += 1
                logger.info(
                    "TranslateState: already completed — restored %d/%d translations from state.",
                    hits, len(ctx.entries),
                )
                return None
            # ``translate`` 被标为完成，但 state_data 里没有译文表。
            # 常见于：早期版本 state 文件遗留、或上次运行在 translate 之后
            # 的下游状态崩溃但 translate 的持久化段还没落盘。此时若直接
            # 跳过，下游会拿到 target_text 全空的 entries，Crowdin 会
            # 判定"所有串都已翻译"并返回 409 "no untranslated words"。
            # 更稳妖的做法是**降级为冷启动**：重跑 LLM。
            logger.warning(
                "TranslateState: marked completed but translations cache is empty — "
                "falling back to a full re-translation to avoid downstream data loss.",
            )

        # --------------------------------------------------------------
        # 1-3) 前置清洗：快照 + 过滤昨日 pending + 按 source 折叠。
        # --------------------------------------------------------------
        self._prepare_entries(ctx)

        # --------------------------------------------------------------
        # 4) 构造策略并翻译（只翻译代表，兄弟在快照里备着）。
        # --------------------------------------------------------------
        profile = ctx.language_profile
        language_id = profile.id if profile else ctx.config.target_locale or "unknown"
        target_locale = (
            (profile.target_locale if profile else "")
            or ctx.config.target_locale
        )
        source_locale = (
            (profile.source_locale if profile else "")
            or ctx.config.source_locale
        )
        strategy_config = dict(profile.strategy_config) if profile else {}

        strategy = get_translation_strategy(
            language_id,
            llm=ctx.llm,
            strategy_config=strategy_config,
            source_locale=source_locale,
            target_locale=target_locale,
        )

        # sources.Entry 转为 translation.Entry，交给策略层翻译，
        # 结果再写回工作流的条目列表。
        translation_entries = _to_translation_entries(ctx.entries)
        result = strategy.process(
            translation_entries,
            source_locale=source_locale,
            target_locale=target_locale,
        )

        _apply_translations(ctx.entries, result.translated)

        # 把译文表持久化到 state_data，供"断点续跑跳过时"回填 ctx.entries。
        # 只保存非空译文，避免干扰尚未翻译的条目。
        ctx.state_data["translate.translations"] = {
            e.key: e.target_text for e in ctx.entries if e.target_text
        }

        # 将统计与失败映射写入 state_data，便于断点续跑与面板取用。
        ctx.state_data["translate.stats"] = dict(result.stats)
        ctx.state_data["translate.errors"] = dict(result.errors)
        ctx.state_payload["translate.success"] = result.stats.get("success", 0)
        ctx.state_payload["translate.failed"] = result.stats.get("failed", 0)

        logger.info(
            "TranslateState: %d translated, %d failed (language=%s)",
            result.stats.get("success", 0),
            result.stats.get("failed", 0),
            language_id,
        )
        self._mark_completed(ctx)
        return None

    # ------------------------------------------------------------------
    def _prepare_entries(self, ctx: WorkflowContext) -> None:
        """三步前置清洗：快照 → 过滤 pending → 折叠同 source。

        在 LLM 调用之前执行，确保翻译量 = 唯一 source 代表数（和 Crowdin
        审员工作量对等）。
        """
        if not ctx.entries:
            # 空列表直接返回：没有新增数据，review state 本来就会 skipped，
            # 快照和 pending-filter 都没必要跑。
            logger.info("TranslateState: no entries from pull_vcs — skipping pre-cleanup.")
            return

        workspace = Path(ctx.workspace)
        batch_name = ctx.state_payload.get("review.batch_name") or ctx.state_data.get(
            "translate.batch_name"
        ) or self._fallback_batch_name(ctx)
        # 把 batch_name 固化到 state_payload，review 阶段也会读同一个（它内部
        # 自己会 _resolve_batch_name，命中 state_payload 后不会再新建批次）。
        ctx.state_payload.setdefault("review.batch_name", batch_name)

        snapshot_dir = workspace / "batches" / batch_name / "translate"
        snapshot_path = snapshot_dir / "incr_snapshot.xlsx"

        # Step 1：保存今日 incr 完整快照（含兄弟）。
        save_incr_snapshot(ctx.entries, snapshot_path)
        ctx.state_payload[_SNAPSHOT_PATH_KEY] = str(snapshot_path)

        # Step 2：按 (key, source) 过滤昨日 pending。
        pending_pairs = load_pending_source_pairs(
            TailTaskStore.path_for(workspace, _resolve_lang(ctx)),
            stages=("first", "second"),
        )
        if pending_pairs:
            kept, dropped = filter_against_pending(ctx.entries, pending_pairs)
            if dropped:
                ctx.state_payload[_SHADOWED_BY_PENDING_KEY] = [e.key for e in dropped]
            ctx.entries = kept

        # Step 2.5：按 key 过滤全量表——命中则剔除今日版本。
        # 【语义】全量表的 Key 唯一性原则：同一个 key 只应保留一条已审译文。
        # 今日 incr 里凡 key 已存在于 full 的，都视为"重复提交 / 回填历史
        # 条目"——直接跳过翻译+审核。被剔除的 key 记录到 state_payload，
        # 由 merge_data 消费（从磁盘的 incr 文件物理删除），避免下次 run
        # 的 pull_vcs 又把它们捞回来形成脏循环。
        self._filter_against_full_table(ctx)

        # Step 3：按 source_text 折叠（第一条作代表）。
        representatives, collapsed = collapse_by_source(ctx.entries)
        if collapsed:
            logger.info(
                "TranslateState: collapsed %d sibling entries into representatives; "
                "they will be broadcast back after review from %s.",
                collapsed, snapshot_path.name,
            )
        ctx.entries = representatives

    # ------------------------------------------------------------------
    def _filter_against_full_table(self, ctx: WorkflowContext) -> None:
        """按 ``entry.key`` 和全量表做去重：命中则从 ctx.entries 剔除。

        被剔除的 keys 存到 :data:`_SHADOWED_BY_FULL_TABLE_KEY` 供 merge_data
        消费（从磁盘 incr 物理删除）。

        **全量表路径优先级**：
        1. ``profile.extra.full_table_path``
        2. ``profile.strategy_config.full_table_path``
        3. 从 ``pull_vcs.source_path`` 用 :func:`infer_full_table_path` 推断

        **边界**：
        * ctx.entries 为空 → 直接返回；
        * 全量表路径解析不到 / 文件不存在 → 返回空集合 → 本步为 no-op
          （首日 bootstrap 场景兼容）。

        **格式无关**：直接用 ``ctx.source`` 读全量表——支持 dtxml/json/
        xliff/xlsx/csv/yaml 等所有已注册格式。
        """
        if not ctx.entries:
            return

        from ...utils.table_merger import (  # noqa: WPS433
            infer_full_table_path,
            load_full_table_keys,
        )

        # 1) 解析 full_path
        profile = ctx.language_profile
        full_path = ""
        if profile is not None:
            for key in ("full_table_path",):
                candidate = (
                    profile.extra.get(key)
                    or profile.strategy_config.get(key)
                )
                if candidate:
                    full_path = str(candidate)
                    break
        if not full_path:
            incr_path = str(ctx.state_payload.get("pull_vcs.source_path") or "")
            if incr_path:
                full_path = infer_full_table_path(incr_path)

        if not full_path:
            logger.info(
                "TranslateState: cannot resolve full_table_path — skip full-table dedup."
            )
            return

        # 2) 读 full 表 key 集合——用 ctx.source（格式无关）。
        full_keys = load_full_table_keys(ctx.source, full_path)
        if not full_keys:
            logger.info(
                "TranslateState: full table %s has 0 keys (or missing) — skip full-table dedup.",
                full_path,
            )
            return

        # 3) 过滤 ctx.entries
        kept: list = []
        dropped_keys: list = []
        for entry in ctx.entries:
            if entry.key in full_keys:
                dropped_keys.append(entry.key)
            else:
                kept.append(entry)

        if dropped_keys:
            ctx.state_payload[_SHADOWED_BY_FULL_TABLE_KEY] = dropped_keys
            ctx.entries = kept
            logger.info(
                "TranslateState: filtered against full table: %d → %d "
                "(dropped %d whose key already lives in %s). merge_data "
                "will physically remove them from the incremental file.",
                len(kept) + len(dropped_keys), len(kept),
                len(dropped_keys), Path(full_path).name,
            )
        else:
            logger.info(
                "TranslateState: full-table dedup checked %d entries against %d full keys; "
                "no overlap.",
                len(ctx.entries), len(full_keys),
            )

    # ------------------------------------------------------------------
    @staticmethod
    def _fallback_batch_name(ctx: WorkflowContext) -> str:
        """生成兜底的批次名（当 state_payload / state_data 里都没有时）。

        用 target_locale + 当前 datetime 戳记，和 _review_state_helpers
        里 ``build_batch_name`` 的格式一致（``<locale>_<YYYYmmddHHMMSS>``）。
        """
        from ...platforms._batch import build_batch_name  # noqa: WPS433 — 局部避免循环

        profile = ctx.language_profile
        target_locale = (
            (profile.target_locale if profile else "")
            or ctx.config.target_locale
            or "unknown"
        )
        return build_batch_name(target_locale=target_locale)


def _to_translation_entries(source_entries):
    """将 :class:`sources.Entry` 转为翻译层的 :class:`translation.Entry`。"""
    from ...translation.base import Entry as TranslationEntry

    result = []
    for e in source_entries:
        result.append(
            TranslationEntry(
                key=e.key,
                source_text=e.source_text,
                target_text=e.target_text,
                context=e.context,
                comment=e.comment,
                en_terms=list(getattr(e, "en_terms", []) or []),
                terms=list(getattr(e, "terms", []) or []),
                metadata=dict(e.metadata) if e.metadata else {},
            )
        )
    return result


def _apply_translations(source_entries, translated_entries) -> None:
    """将 translation.Entry 中的 target_text 回写到 sources.Entry。

    按 ``key`` 匹配，``key`` 在单个源文件内保证唯一。
    同时把 ``metadata["english_side"]`` 两步翻译的英文中间结果一并带回，
    供 :class:`XlsxSource.dump` 写入 ``EnglishSide`` 列（排查痕迹）。
    """
    by_key = {e.key: e for e in translated_entries}
    for entry in source_entries:
        translated = by_key.get(entry.key)
        if translated is None:
            continue
        if translated.target_text:
            entry.target_text = translated.target_text
        # 把英文中间结果搬回 sources.Entry 的 metadata，让 xlsx dump 时
        # EnglishSide 列能拿到值。缺省/空值不覆盖已有值。
        english_side = (translated.metadata or {}).get("english_side") if translated.metadata else None
        if english_side:
            if not getattr(entry, "metadata", None):
                entry.metadata = {}
            entry.metadata["english_side"] = english_side


__all__ = ["TranslateState"]
