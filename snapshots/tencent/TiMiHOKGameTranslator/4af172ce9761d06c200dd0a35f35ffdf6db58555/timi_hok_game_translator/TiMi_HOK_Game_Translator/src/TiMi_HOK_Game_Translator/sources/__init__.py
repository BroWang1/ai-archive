"""TiMi_HOK_Game_Translator.sources 子包。

对外 API::

    from TiMi_HOK_Game_Translator.sources import (
        Entry, LocalizationSource,
        JsonSource, YamlSource, XmlSource, CsvSource, DtxmlSource, XliffSource,
        XlsxSource,
        create_source, register_source, registered_formats,
    )
"""

from .base import (
    Entry,
    LocalizationSource,
    get_source_class,
    register_source,
    registered_formats,
)
from .csv_source import CsvSource
from .dtxml_source import DtxmlSource
from .factory import create_source
from .json_source import JsonSource
from .xliff_source import XliffSource
from .xlsx_source import XlsxSource
from .xml_source import XmlSource
from .yaml_source import YamlSource

__all__ = [
    "CsvSource",
    "DtxmlSource",
    "Entry",
    "JsonSource",
    "LocalizationSource",
    "XliffSource",
    "XlsxSource",
    "XmlSource",
    "YamlSource",
    "create_source",
    "get_source_class",
    "register_source",
    "registered_formats",
]
