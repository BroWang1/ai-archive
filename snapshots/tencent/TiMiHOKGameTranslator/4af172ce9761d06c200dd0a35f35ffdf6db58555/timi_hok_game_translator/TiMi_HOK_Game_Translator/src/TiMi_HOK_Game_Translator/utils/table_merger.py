"""通用增量/全量表合并工具（格式无关版）。

与 :mod:`TiMi_HOK_Game_Translator.utils.dtxml_merger` 的区别——本模块**不绑定 dtxml**，
而是通过 :class:`~TiMi_HOK_Game_Translator.sources.base.LocalizationSource` 协议抽象，
对任何已注册的 source 格式（dtxml / json / xliff / xlsx / csv / yaml / xml）
都能通用执行"按 key upsert 全量表、从增量表删除指定 keys、读取全量表
key 集合"等操作。

设计原则：
    * **只依赖 ``LocalizationSource`` 接口**——不假设任何格式细节；
    * **文件头/元数据的保留由各 source 的 load/dump 自行负责**；
    * **文件名推断支持任意扩展名**：``99.incr.<ext>`` → ``98.full.<ext>``，
      同时向后兼容老 dtxml 的中文命名 ``99.<name>_增量.dtxml`` →
      ``98.<name>_全量.dtxml``。

对外导出：
    - :func:`infer_full_table_path`
    - :func:`split_translated`
    - :func:`merge_incremental_into_full`
    - :func:`load_full_table_keys`
    - :func:`delete_entries_from_incremental`
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from ..sources.base import Entry, LocalizationSource

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 文件名推断
# ---------------------------------------------------------------------------
#: 英文命名（通用、推荐，支持任意扩展名）：
#:
#:   99.incr.dtxml       → 98.full.dtxml
#:   99.incr.json        → 98.full.json
#:   99.foo_incr.xliff   → 98.foo_full.xliff
#:   99.foo.incr.yaml    → 98.foo.full.yaml
_INCREMENTAL_PATTERN_EN = re.compile(
    r"^(?P<prefix>\d+)\.(?P<name>.*?)(?:[._])?incr(?P<ext>\.[A-Za-z0-9]+)$",
    re.IGNORECASE,
)

#: 中文命名（向后兼容老 dtxml 项目）：
#:
#:   99.<name>_增量.dtxml → 98.<name>_全量.dtxml
_INCREMENTAL_PATTERN_CN = re.compile(
    r"^(?P<prefix>\d+)\.(?P<name>.+?)_增量(?P<ext>\.[A-Za-z0-9]+)$"
)

_DEFAULT_INCREMENT_PREFIX = "99"
_DEFAULT_FULL_PREFIX = "98"


def infer_full_table_path(incremental_path: str) -> str:
    """从增量表路径推断同目录下的全量表路径（格式无关）。

    支持的命名：

    * **英文（通用）**：任意扩展名
      - ``99.incr.<ext>``        → ``98.full.<ext>``
      - ``99.<name>_incr.<ext>`` → ``98.<name>_full.<ext>``
      - ``99.<name>.incr.<ext>`` → ``98.<name>.full.<ext>``
    * **中文（dtxml 向后兼容）**：
      - ``99.<name>_增量.<ext>``  → ``98.<name>_全量.<ext>``

    匹配不到两套规则时，按字符串级替换 ``_增量``→``_全量`` /
    ``_incr``→``_full`` / ``.incr``→``.full``；仍然无法命中时在
    原 stem 后加 ``.full``。

    参数：
        incremental_path: 增量表绝对或相对路径。
    返回：
        推断出的全量表路径（字符串）。
    """
    p = Path(incremental_path)
    stem_with_ext = p.name

    # 优先匹配英文模式
    m_en = _INCREMENTAL_PATTERN_EN.match(stem_with_ext)
    if m_en:
        prefix = m_en.group("prefix")
        name = m_en.group("name")
        new_prefix = _DEFAULT_FULL_PREFIX if prefix == _DEFAULT_INCREMENT_PREFIX else prefix
        if name:
            new_name = f"{new_prefix}.{name}_full{m_en.group('ext')}"
        else:
            new_name = f"{new_prefix}.full{m_en.group('ext')}"
        return str(p.with_name(new_name))

    # 回退：中文模式
    m_cn = _INCREMENTAL_PATTERN_CN.match(stem_with_ext)
    if m_cn:
        prefix = m_cn.group("prefix")
        new_prefix = _DEFAULT_FULL_PREFIX if prefix == _DEFAULT_INCREMENT_PREFIX else prefix
        new_name = f"{new_prefix}.{m_cn.group('name')}_全量{m_cn.group('ext')}"
        return str(p.with_name(new_name))

    # 字符串级退化
    for src, dst in (("_增量", "_全量"), ("_incr", "_full"), (".incr", ".full")):
        if src in stem_with_ext:
            return str(p.with_name(stem_with_ext.replace(src, dst)))

    # 兜底
    return str(p.with_name(p.stem + ".full" + p.suffix))


# ---------------------------------------------------------------------------
# 条目划分
# ---------------------------------------------------------------------------
def split_translated(
    entries: Sequence[Entry],
) -> Tuple[List[Entry], List[Entry]]:
    """按 ``target_text`` 是否非空把条目分为已翻译/未翻译两组。

    参数：
        entries: 原始条目列表。
    返回：
        ``(translated, untranslated)``——元素为原对象引用，不做深拷贝。
    """
    translated: List[Entry] = []
    untranslated: List[Entry] = []
    for e in entries:
        if (e.target_text or "").strip():
            translated.append(e)
        else:
            untranslated.append(e)
    return translated, untranslated


# ---------------------------------------------------------------------------
# 核心：upsert 全量表 + 精简增量表
# ---------------------------------------------------------------------------
def merge_incremental_into_full(
    *,
    source: LocalizationSource,
    incremental_path: str,
    full_path: Optional[str] = None,
    translated_entries: Sequence[Entry],
    untranslated_entries: Sequence[Entry],
) -> Dict[str, object]:
    """按 ``entry.key`` 把已翻译条目从增量表 upsert 到全量表（格式无关）。

    行为：
        * 读旧全量表（文件不存在视为空）；
        * 已存在的 key 覆盖、不存在的插入；
        * 写回全量表（含上述合并结果）；
        * 增量表只保留 ``untranslated_entries`` 并写回；
        * ``translated_entries`` 为空也会执行（增量表仍会被重写一次，
          便于清掉"删除 shadowed"后的空壳），返回 ``translated_count=0``。

    参数：
        source: 从 :attr:`WorkflowContext.source` 传入的 source 实例，
            读写都用它——确保增量表和全量表共享文件头/元数据语义。
        incremental_path: 增量表绝对路径。
        full_path: 全量表路径；``None`` 时按 :func:`infer_full_table_path` 推断。
        translated_entries: 本轮已翻译条目（写入全量表）。
        untranslated_entries: 本轮未翻译条目（保留在增量表）。
    返回：
        ``{"incremental": str, "full": str, "translated_count": int,
        "remaining_count": int}``。
    """
    inc_path = Path(incremental_path).resolve()
    full = Path(full_path).resolve() if full_path else Path(
        infer_full_table_path(str(inc_path))
    )

    # 1) 读旧全量表（允许不存在）
    full_entries: List[Entry] = []
    if full.exists():
        try:
            full_entries = list(source.load(str(full)))
        except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
            logger.warning(
                "table_merger: failed to load full table %s (%s); "
                "treating as empty.",
                full, exc,
            )
            full_entries = []
    else:
        logger.info("table_merger: full table not found, will create: %s", full)

    # 2) upsert：translated 覆盖同 key 的旧 entry
    by_key: Dict[str, Entry] = {e.key: e for e in full_entries}
    for te in translated_entries:
        by_key[te.key] = te
    merged_full_entries = list(by_key.values())

    # 3) 写回全量表
    full.parent.mkdir(parents=True, exist_ok=True)
    source.dump(merged_full_entries, str(full))

    # 4) 写回增量表（只保留未翻译）
    source.dump(list(untranslated_entries), str(inc_path))

    return {
        "incremental": str(inc_path),
        "full": str(full),
        "translated_count": len(translated_entries),
        "remaining_count": len(untranslated_entries),
    }


# ---------------------------------------------------------------------------
# 全量表 key 集合（供 translate 阶段去重用）
# ---------------------------------------------------------------------------
def load_full_table_keys(
    source: LocalizationSource,
    full_path: str,
) -> Set[str]:
    """读全量表所有 ``entry.key`` 作为一个集合返回（格式无关）。

    用途：``translate`` 阶段判断"今日 incr 的 entry.key 是否已经存在于
    全量表"——命中则跳过翻译+审核。

    参数：
        source: 用于读全量表的 source 实例。
        full_path: 全量表绝对路径；为空或文件不存在均返回**空集合**。
    返回：
        key 集合（可能为空）。
    """
    if not full_path:
        return set()
    p = Path(full_path)
    if not p.exists():
        return set()
    try:
        entries = source.load(str(p))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "table_merger: load_full_table_keys failed (%s); treating as empty.",
            exc,
        )
        return set()
    return {e.key for e in entries if e.key}


# ---------------------------------------------------------------------------
# 从增量表物理删除指定 keys
# ---------------------------------------------------------------------------
def delete_entries_from_incremental(
    source: LocalizationSource,
    incremental_path: str,
    keys_to_remove: Iterable[str],
) -> int:
    """从增量表删除指定 key 的条目并覆盖写回（格式无关）。

    用途：``translate`` 阶段把"命中全量表 key"的今日 incr 条目剔除后，
    ``merge_data`` 调用本函数把这些 key 从磁盘上的 incr 文件物理删掉——
    否则下次 run 的 pull_vcs 又会把它们捞回来。

    参数：
        source: 用于读写增量表的 source 实例。
        incremental_path: 增量表绝对路径。
        keys_to_remove: 要删除的 key 集合（可迭代）。
    返回：
        实际被删除的条目数（0 表示 keys 不在 incr 里，无操作）。
        文件不存在或读取失败时返回 ``0``。
    """
    keys = {str(k) for k in keys_to_remove if k}
    if not keys:
        return 0
    inc_path = Path(incremental_path)
    if not inc_path.exists():
        return 0

    try:
        entries = source.load(str(inc_path))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "table_merger: delete_entries_from_incremental failed to read %s: %s",
            inc_path, exc,
        )
        return 0

    before = len(entries)
    kept = [e for e in entries if e.key not in keys]
    removed = before - len(kept)
    if removed == 0:
        return 0

    source.dump(kept, str(inc_path))
    logger.info(
        "table_merger: deleted %d entries from incremental %s (remaining=%d)",
        removed, inc_path, len(kept),
    )
    return removed


__all__ = [
    "infer_full_table_path",
    "split_translated",
    "merge_incremental_into_full",
    "load_full_table_keys",
    "delete_entries_from_incremental",
]
