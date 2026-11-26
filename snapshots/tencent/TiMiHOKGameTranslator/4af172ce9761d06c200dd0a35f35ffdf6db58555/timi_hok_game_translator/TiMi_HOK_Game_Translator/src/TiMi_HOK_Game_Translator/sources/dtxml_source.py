"""DTXML 本地化源。

DTXML 是本项目旧流水线使用的表格 XML 方言。开源框架只支持一个能跑通
解析测试与 demo 的**最小子集**：

* 一个根元素 ``<metalib>``（或自定义名称）；
* 一个或多个 ``<struct name="..." version="...">`` 容器；
* 任意多个 ``<entry key="...">``，可选子元素为
  ``<source>`` / ``<target>`` / ``<context>`` / ``<comment>``。

如需支持完整的生产方言，可继承本类并重写读写器，再通过
:func:`register_source` 重新注册。
"""

from __future__ import annotations

from typing import Dict, List, Sequence
from xml.etree import ElementTree as ET

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source
from .xml_source import _indent


@register_source("dtxml")
class DtxmlSource(LocalizationSource):
    """:class:`LocalizationSource` 的 DTXML 实现。"""

    file_extensions = (".dtxml",)

    def load(self, path: str) -> List[Entry]:
        text = self._read_text(path, self.encoding)
        if not text.strip():
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise SourceError(f"Malformed DTXML at {path}: {exc}") from exc

        self.extra.setdefault("root_tag", _local(root.tag))
        self.extra.setdefault("root_attrib", dict(root.attrib))

        entries: List[Entry] = []
        for struct in _iter_structs(root):
            struct_name = struct.get("name", "")
            struct_version = struct.get("version", "")
            for entry_elem in struct:
                if _local(entry_elem.tag) != "entry":
                    continue
                key = (entry_elem.get("key") or "").strip()
                if not key:
                    continue
                entries.append(
                    Entry(
                        key=key,
                        source_text=_child_text(entry_elem, "source"),
                        target_text=_child_text(entry_elem, "target"),
                        context=_child_text(entry_elem, "context"),
                        comment=_child_text(entry_elem, "comment"),
                        metadata={
                            "struct_name": struct_name,
                            "struct_version": struct_version,
                        },
                    )
                )
        return entries

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        root_tag = self.extra.get("root_tag", "metalib")
        root_attrib: Dict[str, str] = {
            str(k): str(v) for k, v in self.extra.get("root_attrib", {}).items()
        }
        root = ET.Element(root_tag, root_attrib)

        # 按 struct 分组汇总条目。
        groups: Dict[str, List[Entry]] = {}
        struct_versions: Dict[str, str] = {}
        for entry in entries:
            struct_name = str(entry.metadata.get("struct_name") or "LocalizationEntry")
            struct_version = str(entry.metadata.get("struct_version") or "1")
            groups.setdefault(struct_name, []).append(entry)
            struct_versions[struct_name] = struct_version

        for struct_name, struct_entries in groups.items():
            struct_elem = ET.SubElement(
                root, "struct", {"name": struct_name, "version": struct_versions[struct_name]}
            )
            for entry in struct_entries:
                entry_elem = ET.SubElement(struct_elem, "entry", {"key": entry.key})
                for tag, value in (
                    ("source", entry.source_text),
                    ("target", entry.target_text),
                    ("context", entry.context),
                    ("comment", entry.comment),
                ):
                    if value:
                        child = ET.SubElement(entry_elem, tag)
                        child.text = value

        _indent(root)
        xml_bytes = ET.tostring(root, encoding=self.encoding, xml_declaration=True)
        self._write_text(path, xml_bytes.decode(self.encoding), self.encoding)


def _local(tag: str) -> str:
    """去掉 XML 命名空间前缀（``{ns}tag`` → ``tag``）。"""
    return tag.rsplit("}", 1)[-1]


def _iter_structs(root: ET.Element):
    for child in root:
        if _local(child.tag) == "struct":
            yield child


def _child_text(elem: ET.Element, tag: str) -> str:
    for child in elem:
        if _local(child.tag) == tag:
            return child.text or ""
    return ""


__all__ = ["DtxmlSource"]
