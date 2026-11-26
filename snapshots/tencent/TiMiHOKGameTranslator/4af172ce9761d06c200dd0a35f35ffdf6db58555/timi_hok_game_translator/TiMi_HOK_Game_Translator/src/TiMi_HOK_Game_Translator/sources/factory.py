"""由 :class:`SourceConfig` 创建 :class:`LocalizationSource` 的工厂。

导入本模块的副作用：依次导入每个内置 source 实现，以触发它们上面的
:func:`register_source` 装饰器。
"""

from __future__ import annotations

from typing import Any, Dict

from ..config.schema import SourceConfig

# 导入内置格式以触发注册。用户自定义格式可在调用
# ``create_source`` 前先导入对应模块或手动调用 ``register_source``。
from . import (  # pylint: disable=unused-import
    csv_source,  # noqa: F401
    dtxml_source,  # noqa: F401
    json_source,  # noqa: F401
    xliff_source,  # noqa: F401
    xlsx_source,  # noqa: F401
    xml_source,  # noqa: F401
    yaml_source,  # noqa: F401
)
from .base import LocalizationSource, get_source_class, registered_formats


def create_source(source_config: SourceConfig) -> LocalizationSource:
    """根据 ``source_config`` 返回 :class:`LocalizationSource` 实例。"""
    cls = get_source_class(source_config.format)
    extra: Dict[str, Any] = dict(source_config.extra or {})
    return cls(encoding=source_config.encoding or "utf-8", extra=extra)


__all__ = ["create_source", "registered_formats"]
