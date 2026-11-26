"""JSON 本地化源。

读写 ``docs/examples/data/example_game.en.json`` 中的标准结构：

.. code-block:: json

    {
        "meta": {...},
        "entries": [
            {"key": "...", "source_text": "...", "context": "...", "comment": "..."}
        ]
    }

为了入站宽容，加载器也接受简单的 ``{"key": "text"}`` 映射。
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Sequence

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source


@register_source("json")
class JsonSource(LocalizationSource):
    """:class:`LocalizationSource` 的 JSON 实现。"""

    file_extensions = (".json",)

    def load(self, path: str) -> List[Entry]:
        raw = self._read_text(path, self.encoding)
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise SourceError(f"Malformed JSON at {path}: {exc}") from exc
        return _parse(data)

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        payload: Dict[str, Any] = {
            "meta": self.extra.get("meta", {}),
            "entries": [_entry_to_dict(e) for e in entries],
        }
        self._write_text(
            path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n", self.encoding
        )


def _parse(data: Any) -> List[Entry]:
    if isinstance(data, dict) and "entries" in data:
        return [_dict_to_entry(item) for item in data["entries"]]
    # 回退：单层 key -> 字符串的映射。
    if isinstance(data, dict):
        return [Entry(key=str(k), source_text=str(v)) for k, v in data.items()]
    if isinstance(data, list):
        return [_dict_to_entry(item) for item in data]
    raise SourceError(
        f"Unsupported JSON top-level structure: {type(data).__name__}. "
        "Expected an object with an 'entries' array or a bare key→string mapping."
    )


def _dict_to_entry(item: Any) -> Entry:
    if not isinstance(item, dict):
        raise SourceError(f"Each JSON entry must be an object, got {type(item).__name__}.")
    return Entry(
        key=str(item.get("key", "")),
        source_text=str(item.get("source_text", "")),
        target_text=str(item.get("target_text", "")),
        context=str(item.get("context", "")),
        comment=str(item.get("comment", "")),
        metadata=dict(item.get("metadata", {})),
    )


def _entry_to_dict(entry: Entry) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "key": entry.key,
        "source_text": entry.source_text,
    }
    if entry.target_text:
        result["target_text"] = entry.target_text
    if entry.context:
        result["context"] = entry.context
    if entry.comment:
        result["comment"] = entry.comment
    if entry.metadata:
        result["metadata"] = entry.metadata
    return result


__all__ = ["JsonSource"]
