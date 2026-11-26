"""兄弟行广播（same-source 一译多扩散）与"今日 vs 昨日 pending"去重工具。

实现 ``broadcast_siblings_by_origin`` 语义——把同一 ``source_text`` 的译文
扩散到所有同源行，同时结合昨日 pending 快照做去重：

* **不依赖 pandas**——直接用 :class:`Entry` dataclass 操作，内存小、单测易写；
* 快照文件沿用 :class:`XlsxSource` 的 ``Key/Source/Target/Context/Comment``
  列头，便于人工打开排查。

典型调用链（在 ``translate`` 和 ``first_review``/``second_review`` 中接入）::

    # translate state 入口：
    save_incr_snapshot(ctx.entries, snapshot_path)
    # 按语种分区拿 last_tasks.json 路径（profile 多语种时各走各的子目录）。
    last_tasks_json_path = TailTaskStore.path_for(ctx.workspace, lang=_resolve_lang(ctx))
    pending_pairs = load_pending_source_pairs(last_tasks_json_path, stages=("first", "second"))
    ctx.entries, overridden = filter_against_pending(ctx.entries, pending_pairs)
    ctx.entries, siblings_map = collapse_by_source(ctx.entries)
    # ... 翻译 / 审核都只处理代表 ...

    # first_review / second_review 的 split_approved 之后：
    ctx.entries = broadcast_siblings_by_source(
        approved_entries=ctx.entries,
        snapshot_path=snapshot_path,
    )
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, List, Sequence, Set, Tuple

from ..sources.base import Entry
from ..sources.xlsx_source import XlsxSource

logger = logging.getLogger(__name__)

#: 单个 source_text 广播出的兄弟行上限（超过记一次 WARN，不阻塞流程）。
_SIBLING_BROADCAST_WARN_THRESHOLD = 20


# ---------------------------------------------------------------------------
# 快照 I/O
# ---------------------------------------------------------------------------
def save_incr_snapshot(entries: Sequence[Entry], snapshot_path: Path) -> None:
    """把今日 incr 的完整 entries 落盘为 xlsx 快照（含所有兄弟行）。

    用途：
        * ``translate`` 状态在**去重前**调用，保存今日 incr 的"全量真相"；
        * ``first_review`` / ``second_review`` 的 split_approved 后，读这个
          快照把同 source 的兄弟行回捞合入 approved_entries。

    参数：
        entries: 今日 incr 的 Entry 列表（**去重前**，含所有兄弟行）。
        snapshot_path: 落盘路径（父目录会被自动创建）。
    """
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    XlsxSource(encoding="utf-8").dump(list(entries), str(snapshot_path))
    logger.info(
        "sibling_broadcast: saved incr snapshot: %d entries → %s",
        len(entries), snapshot_path,
    )


def load_pending_source_pairs(
    last_tasks_json_path: Path,
    *,
    stages: Iterable[str] = ("first", "second"),
) -> Set[Tuple[str, str]]:
    """读 ``workspace/last_tasks.json`` 的指定 slot，返回昨日 pending 的 ``(key, source)`` 集合。

    具体做法：对每个 slot 取 ``upload_path``（即昨日 pending.xlsx 的本地路径），
    用 :class:`XlsxSource` 加载后收集 ``(entry.key, entry.source_text)``。

    路径不存在或内容为空时静默返回**空集合**（无昨日遗留 ≠ 异常）。
    """
    pairs: Set[Tuple[str, str]] = set()
    if not last_tasks_json_path.exists():
        return pairs
    try:
        raw = json.loads(last_tasks_json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "sibling_broadcast: failed to read %s (%s); treating as no pending.",
            last_tasks_json_path, exc,
        )
        return pairs
    for stage in stages:
        slot = raw.get(stage) or {}
        upload_path = slot.get("upload_path") or ""
        if not upload_path:
            continue
        p = Path(upload_path)
        if not p.exists():
            logger.warning(
                "sibling_broadcast: last_tasks.json[%s].upload_path points to a "
                "non-existent file %s — ignoring this slot.",
                stage, upload_path,
            )
            continue
        try:
            entries = XlsxSource(encoding="utf-8").load(str(p))
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "sibling_broadcast: failed to load pending xlsx %s (%s); "
                "ignoring this slot.",
                p, exc,
            )
            continue
        for e in entries:
            if e.key:
                pairs.add((e.key, e.source_text or ""))
        logger.info(
            "sibling_broadcast: loaded %d pending (key,source) pairs from "
            "last_tasks.json[%s] = %s",
            len(entries), stage, p.name,
        )
    return pairs


# ---------------------------------------------------------------------------
# 去重 1：今日 incr 过滤昨日 pending
# ---------------------------------------------------------------------------
def filter_against_pending(
    entries: Sequence[Entry],
    pending_pairs: Set[Tuple[str, str]],
) -> Tuple[List[Entry], List[Entry]]:
    """按 (key, source) 元组和昨日 pending 做一致性比对。

    规则（和用户 Q 对齐）：

    * **(K, S) ∈ pending_pairs**（key 和 source 都和昨日 pending 完全一致）
      → **屏蔽今日这条**（昨日那条 tail task 还在审，等它审完即可，
      避免 Crowdin 侧出现同一个 (key, source) 的两条 task 相互覆盖）。
    * **key 在昨日 pending 但 source 不同** → **保留今日版本**（source 已更新，
      需要重新翻译 + 审核），同时打一条 WARN 日志提示："今日 K 覆盖了
      昨日 pending 的旧 source"。昨日的那条旧 task 仍在 Crowdin 继续审，
      审完后 approved 进 carry_over 时上游会按 (key, source) 兜底丢弃
      —— 保守方案 Q1-A（不主动去 Crowdin 侧撤销）。
    * **key 不在昨日 pending** → 保留今日版本。

    返回：
        ``(kept, dropped)`` —— ``kept`` 是继续走流程的 entries；
        ``dropped`` 是因 Rule 2a 命中而被屏蔽的今日条目（只用于日志，不扩散）。
    """
    if not pending_pairs:
        return list(entries), []
    pending_keys = {k for k, _ in pending_pairs}

    kept: List[Entry] = []
    dropped: List[Entry] = []
    for e in entries:
        pair = (e.key, e.source_text or "")
        if pair in pending_pairs:
            # Rule 2a：(key, source) 完全一致 → 屏蔽今日版本。
            dropped.append(e)
            continue
        if e.key in pending_keys:
            # Rule 2b：同 key 但 source 变了 → 保留今日版本 + WARN。
            logger.warning(
                "sibling_broadcast: key=%r source changed vs yesterday's "
                "pending (today will override). Yesterday's tail task will "
                "still live on Crowdin side; its late-approved result (if any) "
                "will be dropped by carry-over source check.",
                e.key,
            )
        kept.append(e)
    if dropped:
        logger.info(
            "sibling_broadcast: filtered against yesterday's pending: "
            "%d → %d entries (dropped %d because (key, source) is still being "
            "reviewed in a tail task).",
            len(entries), len(kept), len(dropped),
        )
    return kept, dropped


# ---------------------------------------------------------------------------
# 去重 2：按 source_text 分组，每组保留第一条代表
# ---------------------------------------------------------------------------
def collapse_by_source(
    entries: Sequence[Entry],
) -> Tuple[List[Entry], int]:
    """按 ``source_text`` 分组，每组**保留第一条**作代表，其余作为兄弟剔除。

    兄弟不额外存"map"——它们在**快照文件**里备着，审完后由
    :func:`broadcast_siblings_by_source` 回捞扩散。

    返回：
        ``(representatives, collapsed_count)``：
        * ``representatives`` 是去重后的代表列表；
        * ``collapsed_count`` 是被折叠掉的兄弟总数（仅用于日志）。

    边界：
        * 空 source_text 的 entry 视为**独立组**（不与其他空 source 合并）。
          空 source 的翻译无意义，但有 key 的条目保留以免下游处理崩溃。
    """
    seen_sources: Set[str] = set()
    representatives: List[Entry] = []
    collapsed = 0
    for e in entries:
        src = e.source_text or ""
        if not src:
            # 空 source：原样保留，不参与去重分组。
            representatives.append(e)
            continue
        if src in seen_sources:
            collapsed += 1
            continue
        seen_sources.add(src)
        representatives.append(e)
    if collapsed:
        logger.info(
            "sibling_broadcast: collapsed same-source entries: %d → %d "
            "(folded %d siblings into representatives).",
            len(entries), len(representatives), collapsed,
        )
    return representatives, collapsed


# ---------------------------------------------------------------------------
# 扩散：审完后把 approved 的 target_text 复制给同 source 的兄弟
# ---------------------------------------------------------------------------
def broadcast_siblings_by_source(
    approved_entries: Sequence[Entry],
    snapshot_path: Path,
    *,
    warn_threshold: int = _SIBLING_BROADCAST_WARN_THRESHOLD,
) -> List[Entry]:
    """从快照回捞兄弟行，用 approved_entries 的 target 覆盖兄弟的 target。

    参数：
        approved_entries: 代表审完后的 approved entries（已经从 approved.xlsx
            读回最新 target 的 ctx.entries）。
        snapshot_path: :func:`save_incr_snapshot` 落盘的快照 xlsx 路径。
        warn_threshold: 单 source 兄弟数超阈值记一次 WARN（不阻塞）。

    返回：
        扩散后的 Entry 列表：approved_entries 原样 + 同 source 的兄弟（target
        复制自代表）。按 ``key`` 去重防御式保证唯一。

    边界：
        * approved_entries 为空 → 返回空列表（本轮审没通过任何代表）；
        * 快照不存在/读失败 → 返回 approved_entries 原样 + WARN；
        * 兄弟的 source 对应的代表没在 approved_entries 里 → 跳过（代表没通过，
          兄弟也不扩散，交给下次 run 的 tail task 续审）。
    """
    if not approved_entries:
        logger.info(
            "sibling_broadcast: approved_entries is empty — nothing to broadcast.",
        )
        return []
    if not snapshot_path.exists():
        logger.warning(
            "sibling_broadcast: snapshot %s not found; skipping sibling "
            "broadcast (approved=%d).",
            snapshot_path, len(approved_entries),
        )
        return list(approved_entries)

    try:
        snapshot_entries = XlsxSource(encoding="utf-8").load(str(snapshot_path))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "sibling_broadcast: failed to load snapshot %s (%s); skipping.",
            snapshot_path, exc,
        )
        return list(approved_entries)

    # 1) 代表 source → approved 的 target
    approved_target_by_source = {}
    approved_by_key = {}
    for e in approved_entries:
        approved_by_key[e.key] = e
        src = e.source_text or ""
        if src and e.target_text and src not in approved_target_by_source:
            approved_target_by_source[src] = e.target_text

    if not approved_target_by_source:
        logger.info(
            "sibling_broadcast: approved_entries have no (source, target) "
            "pairs — nothing to broadcast (approved=%d).",
            len(approved_entries),
        )
        return list(approved_entries)

    # 2) 从快照里挑出"同 source 但 key 不在 approved_entries 里"的兄弟。
    siblings: List[Entry] = []
    sibling_count_by_source: dict = {}
    for e in snapshot_entries:
        src = e.source_text or ""
        if not src or src not in approved_target_by_source:
            continue
        if e.key in approved_by_key:
            continue  # 已经在 approved 里了，不重复
        # 克隆一份，sibling 的 target 覆盖为代表的译文。
        sibling = Entry(
            key=e.key,
            source_text=e.source_text,
            target_text=approved_target_by_source[src],
            context=e.context,
            comment=e.comment,
            metadata=dict(e.metadata or {}),
        )
        siblings.append(sibling)
        sibling_count_by_source[src] = sibling_count_by_source.get(src, 0) + 1

    # 3) 超阈值 WARN。
    for src, cnt in sibling_count_by_source.items():
        if cnt > warn_threshold:
            logger.warning(
                "sibling_broadcast: source has %d siblings (threshold=%d); "
                "all will be broadcast but please verify this is intended. "
                "source preview=%r",
                cnt, warn_threshold, (src[:60] + "..." if len(src) > 60 else src),
            )

    result = list(approved_entries) + siblings
    if siblings:
        logger.info(
            "sibling_broadcast: broadcast complete: approved=%d + siblings=%d "
            "= %d total (sources=%d).",
            len(approved_entries), len(siblings), len(result),
            len(approved_target_by_source),
        )
    return result


__all__ = [
    "save_incr_snapshot",
    "load_pending_source_pairs",
    "filter_against_pending",
    "collapse_by_source",
    "broadcast_siblings_by_source",
]
