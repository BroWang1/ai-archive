"""XLIFF 1.2 本地化源（最小子集）。

支持读写如下结构::

    <xliff version="1.2" xmlns="urn:oasis:names:tc:xliff:document:1.2">
      <file source-language="en" target-language="zh-CN" datatype="plaintext">
        <body>
          <trans-unit id="key">
            <source>Play</source>
            <target state="translated">播放</target>
            <note>可选备注/上下文</note>
          </trans-unit>
          ...
        </body>
      </file>
    </xliff>

解析时为了简化会丢弃命名空间；``dump`` 时会重新附带 XLIFF 1.2 默认命名空间。
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence
from xml.etree import ElementTree as ET

from ..commons import SourceError
from .base import Entry, LocalizationSource, register_source
from .xml_source import _indent

_XLIFF_NS = "urn:oasis:names:tc:xliff:document:1.2"


@register_source("xliff")
class XliffSource(LocalizationSource):
    """:class:`LocalizationSource` 的 XLIFF 1.2 实现。"""

    file_extensions = (".xliff", ".xlf")

    def load(self, path: str) -> List[Entry]:
        text = self._read_text(path, self.encoding)
        if not text.strip():
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise SourceError(f"Malformed XLIFF at {path}: {exc}") from exc

        entries: List[Entry] = []
        for file_elem in _iter_local(root, "file"):
            self.extra.setdefault("source_language", file_elem.get("source-language", ""))
            self.extra.setdefault("target_language", file_elem.get("target-language", ""))
            self.extra.setdefault("datatype", file_elem.get("datatype", "plaintext"))

            for unit in _iter_all_local(file_elem, "trans-unit"):
                # XLIFF 1.2 语义：
                # * ``resname`` 是业务层的"资源 key"（如
                #   ``Guild_Construct_Building_Info_Text``），这才是上游
                #   翻译/合表要用的那个 key；
                # * ``id`` 只保证"文件内 trans-unit 的唯一数字标识"（Crowdin
                #   在导出 xliff 时填的是其内部的字符串 ID 如 ``11330230``，
                #   与业务无关）。
                # 顺序必须是 resname → id → "" 。如果反过来（id → resname），
                # 下游 ``split_approved_data`` 产出的 ``approved_keys`` 会
                # 变成一堆 Crowdin 数字 ID，与内存 ``ctx.entries[*].key``
                # （业务 key）永远匹配不上，把 20 → 0 擦掉审核结果。
                # （2026-10-09 实测事故现场）
                key = (unit.get("resname") or unit.get("id") or "").strip()
                if not key:
                    continue
                source_elem = _find_local(unit, "source")
                target_elem = _find_local(unit, "target")
                note_elem = _find_local(unit, "note")
                metadata: Dict[str, Any] = {}
                if target_elem is not None and target_elem.get("state"):
                    metadata["state"] = target_elem.get("state", "")
                if unit.get("approved"):
                    metadata["approved"] = unit.get("approved", "")
                entries.append(
                    Entry(
                        key=key,
                        source_text=_text(source_elem),
                        target_text=_text(target_elem),
                        context=_text(_find_local(unit, "context-group")) if False else "",
                        comment=_text(note_elem),
                        metadata=metadata,
                    )
                )
        return entries

    def dump(self, entries: Sequence[Entry], path: str) -> None:
        source_lang = str(self.extra.get("source_language", "en"))
        target_lang = str(self.extra.get("target_language", ""))
        datatype = str(self.extra.get("datatype", "plaintext"))

        ET.register_namespace("", _XLIFF_NS)
        root = ET.Element(f"{{{_XLIFF_NS}}}xliff", {"version": "1.2"})
        file_attrib = {"source-language": source_lang, "datatype": datatype}
        if target_lang:
            file_attrib["target-language"] = target_lang
        file_elem = ET.SubElement(root, f"{{{_XLIFF_NS}}}file", file_attrib)
        body = ET.SubElement(file_elem, f"{{{_XLIFF_NS}}}body")

        for entry in entries:
            # 对称于 ``load``——业务 key 写进 ``resname``；``id`` 仍填相同
            # 值，仅作文件内唯一数字标识兜底（跨平台往返更稳）。
            unit_attrib: Dict[str, str] = {
                "id": entry.key,
                "resname": entry.key,
            }
            if "approved" in entry.metadata:
                unit_attrib["approved"] = str(entry.metadata["approved"])
            unit = ET.SubElement(body, f"{{{_XLIFF_NS}}}trans-unit", unit_attrib)
            src = ET.SubElement(unit, f"{{{_XLIFF_NS}}}source")
            src.text = entry.source_text
            if entry.target_text or "state" in entry.metadata:
                tgt_attrib: Dict[str, str] = {}
                if "state" in entry.metadata:
                    tgt_attrib["state"] = str(entry.metadata["state"])
                tgt = ET.SubElement(unit, f"{{{_XLIFF_NS}}}target", tgt_attrib)
                tgt.text = entry.target_text
            if entry.comment:
                note = ET.SubElement(unit, f"{{{_XLIFF_NS}}}note")
                note.text = entry.comment

        _indent(root)
        xml_bytes = ET.tostring(root, encoding=self.encoding, xml_declaration=True)
        self._write_text(path, xml_bytes.decode(self.encoding), self.encoding)


def _iter_local(root: ET.Element, tag: str):
    for child in root:
        if _localname(child.tag) == tag:
            yield child


def _iter_all_local(root: ET.Element, tag: str):
    for elem in root.iter():
        if _localname(elem.tag) == tag:
            yield elem


def _find_local(parent: ET.Element, tag: str):
    for child in parent:
        if _localname(child.tag) == tag:
            return child
    return None


def _text(elem):
    if elem is None or elem.text is None:
        return ""
    return elem.text


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


__all__ = ["XliffSource"]
