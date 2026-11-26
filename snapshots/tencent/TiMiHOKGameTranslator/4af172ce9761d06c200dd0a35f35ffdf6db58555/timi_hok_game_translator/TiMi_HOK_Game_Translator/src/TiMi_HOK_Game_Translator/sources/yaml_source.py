"""YAML 本地化源。

复用 JSON 的结构，使一份条目文件可在两种格式之间无损互转。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source
from .json_source import _entry_to_dict, _parse


@register_source("yaml")
class YamlSource(LocalizationSource):
    """:class:`LocalizationSource` 的 YAML 实现。"""

    file_extensions = (".yaml", ".yml")

    def load(self, path: str) -> List[Entry]:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SourceError(
                "PyYAML is required for YAML sources. Install with 'pip install PyYAML'."
            ) from exc

        raw = self._read_text(path, self.encoding)
        if not raw.strip():
            return []
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as exc:
            raise SourceError(f"Malformed YAML at {path}: {exc}") from exc
        return _parse(data if data is not None else {})

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover
            raise SourceError(
                "PyYAML is required for YAML sources. Install with 'pip install PyYAML'."
            ) from exc

        payload: Dict[str, Any] = {
            "meta": self.extra.get("meta", {}),
            "entries": [_entry_to_dict(e) for e in entries],
        }
        content = yaml.safe_dump(
            payload, allow_unicode=True, sort_keys=False, default_flow_style=False
        )
        self._write_text(path, content, self.encoding)


__all__ = ["YamlSource"]
