"""Excel (xlsx) 本地化源。

用途：
    把 :class:`~TiMi_HOK_Game_Translator.sources.base.Entry` 列表序列化为 Crowdin / Phrase
    等审校平台能直接识别的表格文件。审校平台解析 xlsx 的能力远优于 dtxml、
    xml、csv，因此在 ``first_review`` / ``second_review`` 阶段应优先走 xlsx。

列结构（固定、通用）::

    | Key | Source | Target | Context | Comment | EnTerms | Terms | EnglishSide |
    |-----|--------|--------|---------|---------|---------|-------|-------------|

    * ``EnTerms`` 列：中→英术语对（常驻），单元格内每行一个 ``源文=英译``，
      多条用换行分隔。两步翻译 Step 1（中→英）会把本列作为术语参考注入。
    * ``Terms`` 列：中→目标语术语对，格式与 ``EnTerms`` 一致。一步策略直接
      注入；两步策略 Step 2 会与 ``EnTerms`` 做映射再注入。
    * ``EnglishSide`` 列：两步翻译 Step 1 的英文中间结果（只读不写入模型），
      仅做"排查痕迹"用。审校平台（Phrase/Crowdin）按前 5 列定位，**不读本列**，
      因此留存在 xlsx 里不会污染上传/审校流程。源表留空即可，由框架自动写回。
    * 旧 5 列文件（无 EnTerms/Terms/EnglishSide）仍可正常 load，缺失列视为空字符串。

设计约束：
    * 可选依赖——仅在实际使用时才 import ``openpyxl``；
    * 列头大小写宽容——load 时 ``KEY`` / ``source`` / ``Target`` / ``en_terms``
      / ``enterms`` / ``ENTERMS`` 都认；
    * 空行自动跳过；``Key`` 为空的行视为无效，丢弃；
    * ``metadata`` 以 ``row_number`` 字段携带原始行号，便于后续回写定位。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source

logger = logging.getLogger(__name__)

#: xlsx 使用的固定表头，顺序即列顺序。
_HEADERS = ("Key", "Source", "Target", "Context", "Comment", "EnTerms", "Terms", "EnglishSide")

#: 工作表默认名称。
_DEFAULT_SHEET_NAME = "Translation"

#: 术语单元格内：条目分隔符（换行）与源译分隔符（等号）。
_TERM_ROW_SEP = "\n"
_TERM_PAIR_SEP = "="


def _normalize_header(name: str) -> str:
    """把列头规范化为小写 + 去下划线，便于容错识别。

    例如：``EnTerms`` / ``en_terms`` / ``EN_TERMS`` / ``enterms``
    都会归一到 ``enterms``。
    """
    return (name or "").strip().lower().replace("_", "")


#: 列头规范化名 → 内部字段名。
_HEADER_ALIASES: Dict[str, str] = {
    "key": "key",
    "source": "source",
    "target": "target",
    "context": "context",
    "comment": "comment",
    "enterms": "en_terms",
    "terms": "terms",
    # EnglishSide / english_side / englishpivot 都识别为同一个字段，
    # 便于手工填/旧文件兼容。
    "englishside": "english_side",
    "englishpivot": "english_side",
}


def _parse_terms(raw: str) -> List[Tuple[str, str]]:
    """解析术语单元格字符串为 ``[(源文, 译文), ...]``。

    格式约定：
        ``源文1=译文1\\n源文2=译文2\\n...``

    容错：
        * 空字符串/None 返回空列表；
        * 空行跳过；
        * 缺少 ``=`` 的行记一行 debug 日志后跳过；
        * ``=`` 两边自动 strip。
    """
    if not raw:
        return []
    pairs: List[Tuple[str, str]] = []
    for line in str(raw).split(_TERM_ROW_SEP):
        line = line.strip()
        if not line:
            continue
        if _TERM_PAIR_SEP not in line:
            logger.debug(
                "XlsxSource: term row missing '%s' separator, skipped: %r",
                _TERM_PAIR_SEP, line,
            )
            continue
        src, dst = line.split(_TERM_PAIR_SEP, 1)
        src = src.strip()
        dst = dst.strip()
        if not src or not dst:
            continue
        pairs.append((src, dst))
    return pairs


def _dump_terms(terms: Sequence[Tuple[str, str]]) -> str:
    """把 ``[(源文, 译文), ...]`` 还原为单元格字符串。空列表返回空串。"""
    if not terms:
        return ""
    return _TERM_ROW_SEP.join(f"{src}{_TERM_PAIR_SEP}{dst}" for src, dst in terms)


@register_source("xlsx")
class XlsxSource(LocalizationSource):
    """:class:`LocalizationSource` 的 xlsx 实现。"""

    file_extensions = (".xlsx",)

    def load(self, path: str) -> List[Entry]:
        openpyxl = _require_openpyxl()
        try:
            wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except Exception as exc:  # noqa: BLE001 — openpyxl 自己的异常类型众多
            raise SourceError(f"Failed to open xlsx {path}: {exc}") from exc

        # 优先取名为 Translation 的 sheet，没有则用第一个 sheet。
        sheet = wb[_DEFAULT_SHEET_NAME] if _DEFAULT_SHEET_NAME in wb.sheetnames else wb.active
        rows_iter = sheet.iter_rows(values_only=True)
        header_row = next(rows_iter, None)
        if header_row is None:
            wb.close()
            return []

        # 建立「标准化表头名 → 列索引」的映射，列顺序允许和 _HEADERS 不一致，
        # 并且允许 EnTerms/en_terms/ENTERMS 等多种拼写。
        col_index: Dict[str, int] = {}
        for idx, cell in enumerate(header_row):
            if cell is None:
                continue
            norm = _normalize_header(str(cell))
            field_name = _HEADER_ALIASES.get(norm)
            if field_name:
                col_index[field_name] = idx
        if "key" not in col_index:
            wb.close()
            raise SourceError(
                f"xlsx {path}: header missing required column 'Key'. "
                f"Got headers: {list(header_row)}"
            )

        entries: List[Entry] = []
        for row_number, row in enumerate(rows_iter, start=2):  # 第 1 行是表头
            key_val = _cell_text(row, col_index.get("key"))
            if not key_val:
                continue
            metadata: Dict[str, Any] = {"row_number": row_number}
            # EnglishSide 列：两步翻译 Step 1 的英文中间结果；非空则塞进
            # metadata["english_side"]，与 executor 层的写入点保持同一 key。
            english_side = _cell_text(row, col_index.get("english_side"))
            if english_side:
                metadata["english_side"] = english_side
            entries.append(
                Entry(
                    key=key_val,
                    source_text=_cell_text(row, col_index.get("source")),
                    target_text=_cell_text(row, col_index.get("target")),
                    context=_cell_text(row, col_index.get("context")),
                    comment=_cell_text(row, col_index.get("comment")),
                    en_terms=_parse_terms(_cell_text(row, col_index.get("en_terms"))),
                    terms=_parse_terms(_cell_text(row, col_index.get("terms"))),
                    metadata=metadata,
                )
            )
        wb.close()

        # 把列头原顺序记录下来，供 dump 继承（可选能力，不是必须）。
        self.extra.setdefault("headers", list(_HEADERS))
        return entries

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        openpyxl = _require_openpyxl()
        wb = openpyxl.Workbook()
        sheet = wb.active
        sheet.title = _DEFAULT_SHEET_NAME

        sheet.append(list(_HEADERS))
        for entry in entries:
            metadata = getattr(entry, "metadata", None) or {}
            english_side = metadata.get("english_side", "") or ""
            sheet.append(
                [
                    entry.key,
                    entry.source_text,
                    entry.target_text,
                    entry.context,
                    entry.comment,
                    _dump_terms(getattr(entry, "en_terms", []) or []),
                    _dump_terms(getattr(entry, "terms", []) or []),
                    english_side,
                ]
            )

        # 简单的列宽设置，便于人工在 Crowdin UI 外预览时阅读。
        for col_idx, width in enumerate((40, 60, 60, 40, 40, 40, 40, 50), start=1):
            sheet.column_dimensions[_col_letter(col_idx)].width = width

        try:
            # 确保目录存在
            from pathlib import Path as _P

            _P(path).parent.mkdir(parents=True, exist_ok=True)
            wb.save(path)
        except OSError as exc:
            raise SourceError(f"Failed to write xlsx {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _require_openpyxl():
    """惰性导入 openpyxl；未安装时给出可操作的错误提示。"""
    try:
        import openpyxl  # noqa: WPS433 — 局部导入
    except ImportError as exc:  # pragma: no cover
        raise SourceError(
            "XlsxSource requires the optional 'openpyxl' package. "
            "Install with `pip install openpyxl` or "
            "`pip install TiMi_HOK_Game_Translator[excel]`."
        ) from exc
    return openpyxl


def _cell_text(row: Optional[Sequence[Any]], idx: Optional[int]) -> str:
    """安全读单元格文本，所有 None/数值都转成字符串。"""
    if row is None or idx is None or idx >= len(row):
        return ""
    value = row[idx]
    if value is None:
        return ""
    return str(value)


def _col_letter(col_idx: int) -> str:
    """1 → 'A'，2 → 'B' ... 26 → 'Z'，27 → 'AA' 的朴素实现。"""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


__all__ = ["XlsxSource"]
