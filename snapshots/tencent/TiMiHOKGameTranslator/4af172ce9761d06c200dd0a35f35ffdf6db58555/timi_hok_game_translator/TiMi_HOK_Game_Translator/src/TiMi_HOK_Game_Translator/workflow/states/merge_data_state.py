"""``merge_data`` 状态——通用的"把已翻译条目从增量表迁移到全量表"实现。

**本 state 与格式无关**：通过 :class:`~TiMi_HOK_Game_Translator.sources.base.LocalizationSource`
协议读写文件，适用于已注册的任何 source 格式（dtxml / json / xliff / xlsx /
csv / yaml / xml 等）。增量/全量二元模型要求"增量表和全量表格式一致"，
文件名默认用 ``99.incr.<ext>`` ↔ ``98.full.<ext>`` 的命名约定自动推断。

实际合并算法在 :mod:`TiMi_HOK_Game_Translator.utils.table_merger` 中以纯函数形式提供。
本模块只负责从 :class:`WorkflowContext` 收集参数并调用它，再把结果写回
上下文供下游 state 使用。

**导表时间窗口**：
    支持在语种 profile 中通过 ``merge_start_time`` 字段（``"HH:MM"``
    格式，本地时区）配置"导表目标启动时间"。设置后，本 state 在真正
    合表前会阻塞等待到该时刻；下游 ``push_vcs`` 紧接着跑，等价于
    "合表 + commit 压到指定窗口"。为空则立即执行。

**向后兼容**：
    老 profile 若在 ``workflow`` 中写了 ``dtxml_merge``——通过
    :mod:`dtxml_merge_state` 的别名注册继续生效，内部直接复用本 state 的实现。
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...commons import WorkflowState as StateEnum
from ...utils.table_merger import (
    delete_entries_from_incremental,
    infer_full_table_path,
    merge_incremental_into_full,
    split_translated,
)
from ..state import WorkflowContext, WorkflowStateBase

logger = logging.getLogger(__name__)

#: 允许在语种 profile 中覆盖全量表路径的 key（``profile.extra`` 与
#: ``profile.strategy_config`` 都查）。为空时按文件名自动推断。
_FULL_PATH_KEYS = ("full_table_path",)

#: 等待目标时间时每轮唤醒的最大 sleep 秒数，用于定期打进度日志。
_WAIT_HEARTBEAT_SECONDS = 60


class MergeDataState(WorkflowStateBase):
    """把本轮已翻译条目从增量表迁移到全量表（格式无关的通用实现）。

    上游依赖：
        - ``translate``：在 ``ctx.entries`` 上填好 ``target_text``；
        - ``validate_data``（可选）：清洗非法条目。
    下游影响：
        - 替换 ``ctx.entries`` 为未翻译子集 → ``push_vcs`` 自然把
          精简后的增量表 commit 回 VCS；
        - 通过 ``ctx.state_payload["merge_data.full_path"]`` 把全量表
          绝对路径告知后续状态，供需要时一并提交；
        - 为兼容老代码，也会把同样的值写入
          ``ctx.state_payload["dtxml_merge.full_path"]``（push_vcs 读的 key）。
    """

    name = StateEnum.MERGE_DATA.value

    def execute(self, ctx: WorkflowContext) -> Optional[str]:
        if self._already_completed(ctx):
            logger.info("MergeDataState: already completed — skipping.")
            return None

        # 0. 若配置了导表目标时间，先阻塞等待到达该时刻。
        _wait_until_merge_time(ctx)

        # 0.1 【2026-10-09 方案 ② 新增】消费 merge-only 通道。
        #
        # ``LastMergeDataState`` 把**昨日二审 approved** 的条目路由到
        # ``last_review.merge_only_entries`` —— 它们已经过了昨日二审，
        # 今日不该再走 first_review / second_review，直接合入 full 表。
        #
        # 做法：把它们 prepend 到 ``ctx.entries`` 的头部，下面的
        # ``split_translated(ctx.entries)`` 会把 target_text 非空的条目
        # 划到 ``translated``，和今日二审 approved 一起被
        # ``merge_incremental_into_full`` 合入 full 表。
        _consume_merge_only_entries(ctx)

        incremental_path = str(ctx.state_payload.get("pull_vcs.source_path") or "")
        if not incremental_path:
            logger.warning(
                "MergeDataState: no incremental source path available — "
                "did pull_vcs run? Skipping merge."
            )
            self._mark_completed(ctx)
            return None

        # 解析全量表路径：profile 显式配置 > 文件名推断。
        profile = ctx.language_profile
        full_path: Optional[str] = None
        if profile is not None:
            for key in _FULL_PATH_KEYS:
                candidate = (
                    profile.extra.get(key)
                    or profile.strategy_config.get(key)
                )
                if candidate:
                    full_path = str(candidate)
                    break
        if not full_path:
            full_path = infer_full_table_path(incremental_path)

        # 从 ctx 直接拿 source 实例——它是 workflow runner 按 profile.source.format
        # 构造的 LocalizationSource，适用于任何已注册格式。
        source = ctx.source

        # 【P4 兼容钩子】真正写磁盘前通知 VCS 后端 "即将修改这些路径"。
        # 对 svn/git/mock 是 no-op；对 perforce 会跑 `p4 edit` 取消本地
        # 文件的只读属性，否则 Python 直接 open(..., "w") 会 PermissionError。
        # 两份文件都要通知——merge_incremental_into_full 会同时写入
        # full 和（间接）incremental。
        _paths_to_prepare = [incremental_path]
        if full_path:
            _paths_to_prepare.append(full_path)
        try:
            ctx.vcs.prepare_for_write(_paths_to_prepare)
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 不致命，仅记日志。
            logger.warning(
                "MergeDataState: vcs.prepare_for_write failed (continuing): %s",
                exc,
            )

        # 【Q2 方案 B 消费点】translate 阶段把"key 已存在于全量表"的今日
        # incr 条目剔除出 ctx.entries，但磁盘上的 incr 文件还留着它们
        # ——这里物理删除，彻底闭环 full-table 去重。**必须在**
        # split_translated 之前执行，否则"translated=0 走早返回"分支里
        # shadowed 永远不被清理，形成每天过滤一次的脏循环。
        shadowed = ctx.state_payload.get("translate.shadowed_by_full_table_keys") or []
        removed = 0
        if shadowed:
            removed = delete_entries_from_incremental(
                source, incremental_path, shadowed,
            )
            logger.info(
                "MergeDataState: pre-merge cleanup — deleted %d full-table-shadowed "
                "entries from %s (keys=%s%s).",
                removed, incremental_path,
                shadowed[:3],
                "..." if len(shadowed) > 3 else "",
            )
            ctx.state_payload["merge_data.shadowed_removed_count"] = removed

        translated, untranslated = split_translated(ctx.entries)
        if not translated:
            logger.info(
                "MergeDataState: no translated entries this round "
                "(incremental=%s), nothing to merge.",
                incremental_path,
            )
            ctx.state_payload["merge_data.translated_count"] = 0
            # 【关键决策】当 shadowed>0 时，incr 文件已被物理修改（删除行），
            # push_vcs **必须 commit** 让 VCS 侧也同步删除——不能 skip。
            # 没 shadowed 时才走原来的 "0 translated → skip" 短路。
            if not shadowed or removed == 0:
                ctx.state_payload["push_vcs.skipped"] = True
                ctx.state_payload["push_vcs.skip_reason"] = (
                    "merge_data produced 0 translated entries this round "
                    "and no shadowed entries removed"
                )
            else:
                logger.info(
                    "MergeDataState: translated=0 but shadowed removed=%d → "
                    "letting push_vcs commit the pruned incremental file.",
                    removed,
                )
            self._mark_completed(ctx)
            return None

        result = merge_incremental_into_full(
            source=source,
            incremental_path=incremental_path,
            full_path=full_path,
            translated_entries=translated,
            untranslated_entries=untranslated,
        )

        # 新 key（通用命名）+ 老 key（dtxml_merge.* ）双写，保持 push_vcs
        # 等下游的向后兼容。
        ctx.state_payload["merge_data.full_path"] = result["full"]
        ctx.state_payload["merge_data.incremental_path"] = result["incremental"]
        ctx.state_payload["merge_data.translated_count"] = int(result["translated_count"])
        ctx.state_payload["merge_data.remaining_count"] = int(result["remaining_count"])
        ctx.state_payload["dtxml_merge.full_path"] = result["full"]
        ctx.state_payload["dtxml_merge.incremental_path"] = result["incremental"]
        ctx.state_payload["dtxml_merge.translated_count"] = int(result["translated_count"])
        ctx.state_payload["dtxml_merge.remaining_count"] = int(result["remaining_count"])

        # 关键：下一个 push_vcs 从 ctx.entries 写回增量表；
        # 替换为未翻译子集 → 提交内容=「移除已翻译后的增量表」。
        ctx.entries = list(untranslated)

        logger.info(
            "MergeDataState: merged %s translated entries into %s; "
            "%s entries remain in %s (format=%s).",
            result["translated_count"], result["full"],
            result["remaining_count"], result["incremental"],
            getattr(source, "format_name", type(source).__name__),
        )

        # 向批次目录落一份"合表快照"——即便 push_vcs 跳过/失败，这份快照
        # 也**独立于 VCS** 保留，是最后一道现场证据。
        _write_debug_snapshot(
            ctx=ctx,
            full_path=str(result["full"]),
            incremental_path=str(result["incremental"]),
            translated=translated,
            untranslated=untranslated,
        )

        self._mark_completed(ctx)
        return None


def _wait_until_merge_time(ctx: WorkflowContext) -> None:
    """若 profile 配置了 ``merge_start_time``，阻塞睡眠到该本地时刻。

    * 空串/未配置 → 立即返回；
    * ``"HH:MM"`` 解析成功：
        - 若本日该时刻**仍未到**，sleep 到那时才返回；
        - 若本日该时刻**已过**（例如 "02:00" 现在 10:00），顺延到次日同点；
    * 格式非法 → 记 warning，退化为立即执行。
    """
    profile = ctx.language_profile
    raw = (getattr(profile, "merge_start_time", "") or "").strip() if profile else ""
    if not raw:
        return
    try:
        hh, mm = raw.split(":", 1)
        hour = int(hh)
        minute = int(mm)
    except (ValueError, AttributeError):
        logger.warning(
            "MergeDataState: invalid merge_start_time %r (expected 'HH:MM'); "
            "executing immediately.",
            raw,
        )
        return

    now = datetime.now()
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)

    total_seconds = (target - now).total_seconds()
    if total_seconds <= 0:
        return

    logger.info(
        "MergeDataState: waiting until %s (%.1f minutes) before merging — "
        "merge_start_time=%s",
        target.isoformat(timespec="seconds"),
        total_seconds / 60.0,
        raw,
    )

    _notify(
        ctx,
        f"⏳ 【{ctx.config.project_code}】等待合并窗口\n"
        f"目标时间：{target.isoformat(timespec='minutes')}\n"
        f"配置项 merge_start_time={raw}",
    )

    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            break
        chunk = min(_WAIT_HEARTBEAT_SECONDS, remaining)
        time.sleep(chunk)
        remaining_after = (target - datetime.now()).total_seconds()
        if remaining_after > 0:
            logger.info(
                "MergeDataState: still waiting — %.1f minutes to %s",
                remaining_after / 60.0,
                target.isoformat(timespec="seconds"),
            )

    logger.info(
        "MergeDataState: merge window reached (%s), proceeding.",
        target.isoformat(timespec="seconds"),
    )
    _notify(
        ctx,
        f"🔀 【{ctx.config.project_code}】合并窗口已到，开始执行 merge_data。",
    )


def _notify(ctx: WorkflowContext, message: str) -> None:
    """安全地发一条通知；失败不影响主流程。

    会自动从 ``ctx.config.notification.mentioned`` 取出需要 @ 的用户列表
    透传给 notifier。
    """
    if ctx.notifier is None:
        return
    try:
        mentioned = tuple(
            (ctx.config.notification.mentioned or [])
            if getattr(ctx.config, "notification", None)
            else ()
        )
        ctx.notifier.notify(message, mentioned=mentioned)
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning("MergeDataState: notifier failed: %s", exc)


def _write_debug_snapshot(
    *,
    ctx: WorkflowContext,
    full_path: str,
    incremental_path: str,
    translated: List[Any],
    untranslated: List[Any],
) -> None:
    """把本轮合表产物复制一份到 ``workspace/batches/<batch>/merge_data/``。

    快照目录名保持为 ``dtxml_merge``（历史目录名）以免破坏运维脚本——
    真实合并算法与格式无关，但目录名保留以减少迁移风险。
    产出三份文件：

    * ``full_after_merge<ext>``——合入 translated 之后的全量表完整副本；
    * ``incremental_after_merge<ext>``——剔除 approved 之后的增量表完整副本；
    * ``merged_entries.json``——本轮合入了哪些 key 的清单。

    失败不致命——任何 I/O 错误都仅告警，不影响主流程继续推进 push_vcs。
    """
    batch_name = str(ctx.state_data.get("review.batch_name") or "")
    if not batch_name:
        batch_name = "merge_only_" + datetime.now().strftime("%Y%m%d%H%M%S")

    # 历史目录名保留为 "dtxml_merge"（即便现在用通用版 merge_data），
    # 避免破坏现有的产物浏览路径/运维脚本。
    snapshot_dir = Path(ctx.workspace) / "batches" / batch_name / "dtxml_merge"
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning(
            "MergeDataState: cannot create snapshot dir %s: %s", snapshot_dir, exc,
        )
        return

    # 拷贝两份快照——保留原文件后缀，便于肉眼直接打开。
    full_ext = Path(full_path).suffix or ".dat"
    inc_ext = Path(incremental_path).suffix or ".dat"
    for src, dst_name in (
        (full_path, f"full_after_merge{full_ext}"),
        (incremental_path, f"incremental_after_merge{inc_ext}"),
    ):
        if not src:
            continue
        try:
            shutil.copyfile(src, str(snapshot_dir / dst_name))
        except OSError as exc:
            logger.warning(
                "MergeDataState: snapshot copy %s → %s failed: %s",
                src, dst_name, exc,
            )

    # 写合入条目清单 json。
    payload: Dict[str, Any] = {
        "batch_name": batch_name,
        "translated_count": len(translated),
        "remaining_count": len(untranslated),
        "merged_at": datetime.now().isoformat(timespec="seconds"),
        "full_path": full_path,
        "incremental_path": incremental_path,
        "source_format": getattr(ctx.source, "format_name", type(ctx.source).__name__),
        "entries": [
            {
                "key": getattr(e, "key", ""),
                "source_text": getattr(e, "source_text", ""),
                "target_text": getattr(e, "target_text", ""),
            }
            for e in translated
        ],
    }
    merged_json = snapshot_dir / "merged_entries.json"
    try:
        merged_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning(
            "MergeDataState: snapshot write %s failed: %s", merged_json, exc,
        )
        return

    logger.info(
        "MergeDataState: snapshot written to %s (translated=%d, remaining=%d)",
        snapshot_dir, len(translated), len(untranslated),
    )


#: 【2026-10-09 方案 ② 新增】消费 "直接合入 full 表" 通道的 key。
#: 由 :class:`LastMergeDataState` 填充；由 :class:`MergeDataState` 消费。
_MERGE_ONLY_ENTRIES_KEY = "last_review.merge_only_entries"


def _consume_merge_only_entries(ctx: WorkflowContext) -> None:
    """从 ``ctx.state_payload[_MERGE_ONLY_ENTRIES_KEY]`` 读昨日二审 approved
    条目，按 Rule 2b 精确路由到 ``ctx.entries``；读取后清空通道。

    这些条目的 ``target_text`` 已经填充（昨日二审通过的最终译文），下面
    ``split_translated`` 会把它们划入 ``translated`` 和今日二审 approved
    一起合入 full 表 —— 完全跳过 first_review / second_review。

    **Rule 2b 精确版**：
      * key 不冲突 → prepend 到 ctx.entries 头部；
      * key 冲突 + source 相同 → **原地替换** ctx.entries 对应条目
        （保留昨日二审 approved 版本，它已过完整两轮审核，比今日的新版本
        更前进）；
      * key 冲突 + source 不同 → WARN 并丢弃昨日版本。
    """
    from ...sources.base import Entry  # noqa: WPS433 — 局部避免循环导入

    raw_list = ctx.state_payload.get(_MERGE_ONLY_ENTRIES_KEY) or []
    if not raw_list:
        return

    rolled: list = []
    for raw in raw_list:
        if not isinstance(raw, dict):
            continue
        try:
            rolled.append(
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
            logger.warning(
                "MergeDataState: skip malformed merge-only item: %s", exc,
            )

    # 清空通道，防止下次 run 重复合入。
    ctx.state_payload.pop(_MERGE_ONLY_ENTRIES_KEY, None)

    if not rolled:
        return

    # Rule 2b 精确判定。
    today_by_key = {e.key: e for e in ctx.entries}
    today_entries_mutable = list(ctx.entries)
    today_index_by_key = {e.key: i for i, e in enumerate(today_entries_mutable)}
    seen_in_rolled: set = set()

    prepend_entries: list = []
    replaced_in_today = 0
    dropped_diff_source = 0
    dropped_cross_channel = 0

    for e in rolled:
        if e.key in seen_in_rolled:
            dropped_cross_channel += 1
            continue
        seen_in_rolled.add(e.key)

        if e.key not in today_by_key:
            prepend_entries.append(e)
            continue

        today_version = today_by_key[e.key]
        if today_version.source_text == e.source_text:
            idx = today_index_by_key[e.key]
            today_entries_mutable[idx] = e
            today_by_key[e.key] = e
            replaced_in_today += 1
        else:
            logger.warning(
                "MergeDataState: dropping yesterday merge-only entry key=%r "
                "because today has the same key with a DIFFERENT source "
                "(today's version wins).",
                e.key,
            )
            dropped_diff_source += 1

    before = len(ctx.entries)
    ctx.entries = prepend_entries + today_entries_mutable
    logger.info(
        "MergeDataState: injected merge-only entries: new=%d, "
        "replaced_in_today=%d (same source), dropped_diff_source=%d, "
        "dropped_cross_channel=%d. ctx.entries: %d → %d "
        "— these skip first_review AND second_review, going straight into full-table merge.",
        len(prepend_entries), replaced_in_today, dropped_diff_source,
        dropped_cross_channel, before, len(ctx.entries),
    )


__all__ = ["MergeDataState"]
