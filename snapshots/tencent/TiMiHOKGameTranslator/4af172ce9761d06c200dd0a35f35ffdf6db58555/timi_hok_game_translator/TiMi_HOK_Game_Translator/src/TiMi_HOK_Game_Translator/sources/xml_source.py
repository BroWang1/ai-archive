"""XML 本地化源。

采用如下标签布局::

    <localization project_code="..." source_locale="..." target_locale="...">
      <entry key="..." context="..." comment="...">
        <source>...</source>
        <target>...</target>
      </entry>
      ...
    </localization>

根属性会保存到 :attr:`LocalizationSource.extra`，以便 ``dump`` 时回写。
"""

from __future__ import annotations

from typing import Dict, List, Sequence
from xml.etree import ElementTree as ET

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source


@register_source("xml")
class XmlSource(LocalizationSource):
    """:class:`LocalizationSource` 的 XML 实现。"""

    file_extensions = (".xml",)

    def load(self, path: str) -> List[Entry]:
        text = self._read_text(path, self.encoding)
        if not text.strip():
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise SourceError(f"Malformed XML at {path}: {exc}") from exc

        # 保留根元素属性，便于 round-trip。
        self.extra.setdefault("root_tag", root.tag)
        self.extra.setdefault("root_attrib", dict(root.attrib))

        entries: List[Entry] = []
        for elem in root.findall("entry"):
            key = (elem.get("key") or "").strip()
            if not key:
                continue
            source_text = _child_text(elem, "source")
            target_text = _child_text(elem, "target")
            entries.append(
                Entry(
                    key=key,
                    source_text=source_text,
                    target_text=target_text,
                    context=elem.get("context", ""),
                    comment=elem.get("comment", ""),
                    metadata={
                        f"attr:{name}": value
                        for name, value in elem.attrib.items()
                        if name not in {"key", "context", "comment"}
                    },
                )
            )
        return entries

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        root_tag = self.extra.get("root_tag", "localization")
        root_attrib: Dict[str, str] = {
            str(k): str(v) for k, v in self.extra.get("root_attrib", {}).items()
        }
        root = ET.Element(root_tag, root_attrib)
        for entry in entries:
            attrs: Dict[str, str] = {"key": entry.key}
            if entry.context:
                attrs["context"] = entry.context
            if entry.comment:
                attrs["comment"] = entry.comment
            for meta_key, meta_val in entry.metadata.items():
                if isinstance(meta_key, str) and meta_key.startswith("attr:"):
                    attrs[meta_key[5:]] = str(meta_val)
            elem = ET.SubElement(root, "entry", attrs)
            source_elem = ET.SubElement(elem, "source")
            source_elem.text = entry.source_text
            if entry.target_text:
                target_elem = ET.SubElement(elem, "target")
                target_elem.text = entry.target_text
        _indent(root)
        xml_bytes = ET.tostring(root, encoding=self.encoding, xml_declaration=True)
        # 因为请求了声明，``tostring`` 返回 bytes；解码后交给公共的
        # ``_write_text`` 写入。
        self._write_text(path, xml_bytes.decode(self.encoding), self.encoding)


def _child_text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    if child is None or child.text is None:
        return ""
    return child.text


def _indent(elem: ET.Element, level: int = 0) -> None:
    """就地美化缩进（避免使用仅 Python 3.9+ 可用的 ``ET.indent``）。"""
    indent = "\n" + level * "    "
    if len(elem):  # pylint: disable=len-as-condition
        if not elem.text or not elem.text.strip():
            elem.text = indent + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _indent(child, level + 1)
        if not child.tail or not child.tail.strip():  # noqa: F821 — 循环变量仍在作用域
            child.tail = indent
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = indent


__all__ = ["XmlSource"]
