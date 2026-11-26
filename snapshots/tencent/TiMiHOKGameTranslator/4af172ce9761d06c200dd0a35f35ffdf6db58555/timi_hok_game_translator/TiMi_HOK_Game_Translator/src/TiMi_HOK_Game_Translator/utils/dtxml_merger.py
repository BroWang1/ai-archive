"""DTXML 增量/全量表合并工具。

游戏本地化流水线中，待翻译文本通常先放到 **增量表**（如 ``99.*_增量.dtxml``）
处理，翻译完成后需要把这些条目迁移到 **全量表**（如 ``98.*_全量.dtxml``）。
本模块提供与工作流框架解耦的纯函数实现，可被工作流 state、独立脚本或测试直接复用。

对外导出：
    - :func:`infer_full_table_path` 由增量表路径推断全量表路径；
    - :func:`split_translated` 按 ``target_text`` 划分已/未翻译条目；
    - :func:`merge_incremental_into_full` 执行真正的"从增量移到全量"操作；
    - :func:`load_full_table_keys` 读全量表的 key 集合（供"今日 incr vs 全量表
      去重"场景使用）；
    - :func:`delete_entries_from_incremental` 从增量表删除指定 key 的条目
      （供"命中全量表的今日 incr 条目清理"场景使用）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple
from xml.etree import ElementTree as ET

from ..sources.base import Entry
from ..sources.dtxml_source import DtxmlSource

logger = logging.getLogger(__name__)

#: 增量表文件名匹配规则（按优先级向下尝试）：
#:
#: 1. **英文命名**（推荐）：``99.incr.dtxml`` / ``99.<name>_incr.dtxml`` / ``99.<name>.incr.dtxml``
#:    —— 适用于新项目和跨平台无中文坑的场景；
#: 2. **中文命名**（向后兼容）：``99.<name>_增量.dtxml`` —— 老项目/线上游戏数据表沿用。
_INCREMENTAL_PATTERN_EN = re.compile(
    r"^(?P<prefix>\d+)\.(?P<name>.*?)(?:[._])?incr(?P<ext>\.dtxml)$",
    re.IGNORECASE,
)
_INCREMENTAL_PATTERN_CN = re.compile(
    r"^(?P<prefix>\d+)\.(?P<name>.+?)_增量(?P<ext>\.dtxml)$"
)

#: 默认前缀映射：99（增量）↔ 98（全量）
_DEFAULT_INCREMENT_PREFIX = "99"
_DEFAULT_FULL_PREFIX = "98"


def infer_full_table_path(incremental_path: str) -> str:
    """由增量表路径推断同目录下的全量表路径。

    参数：
        incremental_path: 增量表绝对或相对路径。支持两套命名：

            * **英文**：``99.incr.dtxml``、``99.foo_incr.dtxml``、
              ``99.foo.incr.dtxml`` → 推断为 ``98.full.dtxml``、
              ``98.foo_full.dtxml``、``98.foo.full.dtxml``；
            * **中文（向后兼容）**：``99.<name>_增量.dtxml`` →
              ``98.<name>_全量.dtxml``。

    返回：
        推断出的全量表路径；两套规则都匹配不上时按"把 ``_增量`` 替换为 ``_全量``"
        或 ``_incr`` → ``_full`` 做字符串级退化，仍无法命中时在原 stem 后加
        ``.full`` 扩展。
    """
    p = Path(incremental_path)
    stem_with_ext = p.name

    # 优先匹配英文模式（新规则）
    m_en = _INCREMENTAL_PATTERN_EN.match(stem_with_ext)
    if m_en:
        prefix = m_en.group("prefix")
        name = m_en.group("name")
        new_prefix = _DEFAULT_FULL_PREFIX if prefix == _DEFAULT_INCREMENT_PREFIX else prefix
        # 保留 name 和 incr 之间的分隔符风格：优先用原文件名里的分隔符
        # （下划线/点/无）与 "full" 拼接。
        sep = ""
        if name:
            # 查看原文件名里 incr 前的分隔符
            # 简化策略：如果 name 非空，用 "_"；如果 name 空，就直接 "full"
            sep = "_"
            new_name = f"{new_prefix}.{name}{sep}full{m_en.group('ext')}"
        else:
            new_name = f"{new_prefix}.full{m_en.group('ext')}"
        return str(p.with_name(new_name))

    # 回退匹配中文模式（向后兼容）
    m_cn = _INCREMENTAL_PATTERN_CN.match(stem_with_ext)
    if m_cn:
        prefix = m_cn.group("prefix")
        new_prefix = _DEFAULT_FULL_PREFIX if prefix == _DEFAULT_INCREMENT_PREFIX else prefix
        new_name = f"{new_prefix}.{m_cn.group('name')}_全量{m_cn.group('ext')}"
        return str(p.with_name(new_name))

    # 最后退化：字符串级替换
    for src, dst in (("_增量", "_全量"), ("_incr", "_full"), (".incr", ".full")):
        if src in stem_with_ext:
            return str(p.with_name(stem_with_ext.replace(src, dst)))

    # 兜底：既没匹配到数字前缀，也没找到 _增量 / _incr 子串
    return str(p.with_name(p.stem + ".full" + p.suffix))


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


def _load_dtxml(path: Path, encoding: str = "utf-8") -> Tuple[DtxmlSource, List[Entry]]:
    """加载 dtxml 文件；文件不存在时返回空列表但保留默认 root_tag。

    参数：
        path: dtxml 绝对路径。
        encoding: 文件编码。
    返回：
        ``(source, entries)``——source 对象已记录 root_tag/root_attrib，可直接复用于 dump。
    """
    source = DtxmlSource(encoding=encoding)
    if not path.exists():
        logger.info("dtxml_merger: file not found, will create on dump: %s", path)
        return source, []
    entries = list(source.load(str(path)))
    return source, entries


def merge_incremental_into_full(
    *,
    incremental_path: str,
    full_path: Optional[str] = None,
    translated_entries: Sequence[Entry],
    untranslated_entries: Sequence[Entry],
    encoding: str = "utf-8",
) -> Dict[str, object]:
    """把已翻译条目从增量表移到全量表（按 ``entry.key``=``<Cell Name="Key">`` upsert）。

    行为：
        - 全量表以 ``entry.key``（即 dtxml 的 ``<Cell Name="Key">`` 字段 /
          简化方言的 ``<entry key="...">`` 属性）为主键 upsert：
          已存在就覆盖、不存在就插入；
        - 增量表只保留 ``untranslated_entries``；
        - ``translated_entries`` 为空也会执行（无变更），便于无条件嵌入工作流。

    参数：
        incremental_path: 增量表绝对路径。
        full_path: 全量表绝对路径；为 ``None`` 时按 :func:`infer_full_table_path` 推断。
        translated_entries: 本轮已翻译条目（写入全量表）。
        untranslated_entries: 本轮未翻译条目（保留在增量表）。
        encoding: dtxml 读写编码，默认 utf-8。
    返回：
        ``{"incremental": str, "full": str, "translated_count": int, "remaining_count": int}``。
    """
    inc_path = Path(incremental_path).resolve()
    full = Path(full_path).resolve() if full_path else Path(infer_full_table_path(str(inc_path)))

    # 1) 读全量表（允许不存在，首次会创建）
    full_source, full_entries = _load_dtxml(full, encoding=encoding)

    # 2) upsert 已翻译条目到全量表
    full_by_key: Dict[str, Entry] = {e.key: e for e in full_entries}
    for te in translated_entries:
        full_by_key[te.key] = te
    merged_full_entries = list(full_by_key.values())

    # 3) 写回全量表
    full.parent.mkdir(parents=True, exist_ok=True)
    full_source.dump(merged_full_entries, str(full))

    # 4) 写回增量表（只保留未翻译），尽量继承原文件头
    inc_source = DtxmlSource(encoding=encoding)
    if inc_path.exists():
        try:
            root = ET.fromstring(inc_path.read_text(encoding=encoding))
            inc_source.extra.setdefault("root_tag", root.tag.rsplit("}", 1)[-1])
            inc_source.extra.setdefault("root_attrib", dict(root.attrib))
        except ET.ParseError:
            logger.warning(
                "dtxml_merger: incremental table has invalid XML, overwriting: %s",
                inc_path,
            )
    inc_source.dump(list(untranslated_entries), str(inc_path))

    return {
        "incremental": str(inc_path),
        "full": str(full),
        "translated_count": len(translated_entries),
        "remaining_count": len(untranslated_entries),
    }


def load_full_table_keys(
    full_path: str,
    *,
    encoding: str = "utf-8",
) -> Set[str]:
    """读全量表所有 ``entry.key`` 作为一个集合返回。

    用途：translate 阶段用它来判断"今日 incr 的 entry.key 是否已经存在
    于全量表"——命中则跳过翻译+审核（因为全量表的 Key 唯一性原则：
    同一个 key 只保留一条已审译文）。

    参数：
        full_path: 全量表的绝对路径。为空或文件不存在均返回**空集合**，
            调用方因此得到"没有命中任何已存在 key"的结果——所有今日 incr
            条目正常走翻译流程（和首日 bootstrap 场景兼容）。
        encoding: 文件编码；一般和 incr 保持一致。

    返回：
        key 集合（可能为空）。
    """
    if not full_path:
        return set()
    p = Path(full_path)
    if not p.exists():
        return set()
    try:
        entries = DtxmlSource(encoding=encoding).load(str(p))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "dtxml_merger: load_full_table_keys failed (%s); treating as empty.",
            exc,
        )
        return set()
    return {e.key for e in entries if e.key}


def delete_entries_from_incremental(
    incremental_path: str,
    keys_to_remove: Iterable[str],
    *,
    encoding: str = "utf-8",
) -> int:
    """从增量表删除指定 key 的条目并覆盖写回（继承原文件头）。

    用途：translate 阶段把"命中全量表 key"的今日 incr 条目剔除后，
    dtxml_merge 调用本函数把这些 key 从磁盘上的 incr 文件物理删掉——
    否则下次 run 的 pull_vcs 又会把它们捞回来，陷入"每天过滤一次"
    的脏循环。

    参数：
        incremental_path: 增量表绝对路径。
        keys_to_remove: 要删除的 key 集合（可迭代）。
        encoding: 文件编码。

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

    source = DtxmlSource(encoding=encoding)
    try:
        entries = source.load(str(inc_path))
    except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
        logger.warning(
            "dtxml_merger: delete_entries_from_incremental failed to read %s: %s",
            inc_path, exc,
        )
        return 0

    before = len(entries)
    kept = [e for e in entries if e.key not in keys]
    removed = before - len(kept)
    if removed == 0:
        return 0

    # 继承原文件头
    try:
        root = ET.fromstring(inc_path.read_text(encoding=encoding))
        source.extra.setdefault("root_tag", root.tag.rsplit("}", 1)[-1])
        source.extra.setdefault("root_attrib", dict(root.attrib))
    except ET.ParseError:
        logger.warning(
            "dtxml_merger: incremental table has invalid XML header, overwriting: %s",
            inc_path,
        )

    source.dump(kept, str(inc_path))
    logger.info(
        "dtxml_merger: deleted %d entries from incremental %s (remaining=%d)",
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
