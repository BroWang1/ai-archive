"""CSV 本地化源。

期望的列结构（必须含表头行）：

    key, source_text[, target_text, context, comment]

额外列会按列名保存到 :attr:`Entry.metadata` 中。
``dump`` 时先写固定列，再按确定顺序写入所有 entries 中出现过的 metadata 列。
"""

from __future__ import annotations

import csv
import io
from typing import Any, Dict, List, Sequence, Set

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source

_FIXED_COLUMNS = ("key", "source_text", "target_text", "context", "comment")


@register_source("csv")
class CsvSource(LocalizationSource):
    """:class:`LocalizationSource` 的 CSV 实现。"""

    file_extensions = (".csv",)

    def load(self, path: str) -> List[Entry]:
        text = self._read_text(path, self.encoding)
        if not text.strip():
            return []
        try:
            reader = csv.DictReader(io.StringIO(text))
        except csv.Error as exc:
            raise SourceError(f"Malformed CSV at {path}: {exc}") from exc

        if reader.fieldnames is None or "key" not in reader.fieldnames:
            raise SourceError(
                f"CSV at {path} must have a header row that includes a 'key' column."
            )

        entries: List[Entry] = []
        for row_no, row in enumerate(reader, start=2):
            key = (row.get("key") or "").strip()
            if not key:
                continue
            metadata: Dict[str, Any] = {}
            for col, val in row.items():
                if col in _FIXED_COLUMNS or col is None:
                    continue
                if val is not None and val != "":
                    metadata[col] = val
            metadata.setdefault("csv_row", row_no)
            entries.append(
                Entry(
                    key=key,
                    source_text=row.get("source_text") or "",
                    target_text=row.get("target_text") or "",
                    context=row.get("context") or "",
                    comment=row.get("comment") or "",
                    metadata=metadata,
                )
            )
        return entries

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        extra_columns: Set[str] = set()
        for entry in entries:
            for meta_key in entry.metadata:
                if meta_key != "csv_row":
                    extra_columns.add(str(meta_key))

        fieldnames = list(_FIXED_COLUMNS) + sorted(extra_columns)
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=fieldnames)
        writer.writeheader()
        for entry in entries:
            row: Dict[str, Any] = {
                "key": entry.key,
                "source_text": entry.source_text,
                "target_text": entry.target_text,
                "context": entry.context,
                "comment": entry.comment,
            }
            for extra_col in extra_columns:
                row[extra_col] = entry.metadata.get(extra_col, "")
            writer.writerow(row)
        self._write_text(path, buffer.getvalue(), self.encoding)


__all__ = ["CsvSource"]
