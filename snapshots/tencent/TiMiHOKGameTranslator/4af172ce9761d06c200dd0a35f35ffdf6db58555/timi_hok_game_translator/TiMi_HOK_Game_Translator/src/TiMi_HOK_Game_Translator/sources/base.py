"""本地化源文件抽象。

每种支持的文件格式都继承 :class:`LocalizationSource` 并通过
:func:`register_source` 装饰器注册。不要直接实例化子类，使用
:func:`TiMi_HOK_Game_Translator.sources.create_source` 代替。

内存中的标准表示为 :class:`Entry` 列表；各后端需确保
:attr:`Entry.metadata` 中的额外信息可在 ``load → dump`` 循环中完整往返。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Type

from ..commons import SourceError, UnknownSourceFormatError


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------
@dataclass
class Entry:
    """单个本地化条目。

    字段：
        key: 稳定的条目标识（惯例上以小数点分隔）。
        source_text: 源语言文本。
        target_text: 目标语言译文；尚未翻译时为空串。
        context: 自由形式的上下文（展示给翻译者/LLM）。
        comment: 人工备注（术语、占位符说明等）。
        en_terms: 中→英术语对列表（``[(zh, en), ...]``）。两步翻译的
            Step 1（中→英）会把本字段作为术语参考注入提示词；一步策略
            直译时忽略本字段。单元格内一般形如
            ``艾薇塔=Evita\\n护盾=shield``，由 :class:`XlsxSource` 解析。
        terms: 中→目标语术语对列表（``[(zh, target), ...]``）。
            * 一步策略（中→目标）直接作为术语参考注入；
            * 两步策略 Step 2（英→目标）会与 :attr:`en_terms` 做映射，
              拼成"英→目标"术语对注入，详见
              :class:`~TiMi_HOK_Game_Translator.strategies.minor_language_strategy.TwoStepTranslationStrategy`。
        metadata: 后端自定义字段（如 XLIFF 的 ``state`` 属性、
            DTXML 的 struct 名、CSV 行号），会在 ``load → dump`` 循环中保留。
    """

    key: str
    source_text: str = ""
    target_text: str = ""
    context: str = ""
    comment: str = ""
    en_terms: List[Any] = field(default_factory=list)
    terms: List[Any] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 抽象基类
# ---------------------------------------------------------------------------
class LocalizationSource(abc.ABC):
    """某一种文件格式的读/写接口。"""

    #: 本后端在注册表中的名称。
    format_name: str = ""

    #: 首选文件后缀（供工具与错误提示使用）。
    file_extensions: Sequence[str] = ()

    def __init__(self, *, encoding: str = "utf-8", extra: Optional[Dict[str, Any]] = None) -> None:
        self.encoding = encoding
        self.extra: Dict[str, Any] = dict(extra or {})

    # ------------------------------------------------------------------
    # 抽象 API
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def load(self, path: str) -> List[Entry]:
        """解析 ``path`` 文件并返回条目列表。"""

    @abc.abstractmethod
    def dump(self, entries: Sequence[Entry], path: str) -> None:
        """将 ``entries`` 序列化到 ``path``，会覆盖已有文件。"""

    # ------------------------------------------------------------------
    # 默认的合并实现
    # ------------------------------------------------------------------
    def merge(self, base: Sequence[Entry], patch: Sequence[Entry]) -> List[Entry]:
        """合并 ``base`` 与 ``patch``。

        语义：

        * ``patch`` 中的条目**覆盖** ``base`` 中同 key 的条目（按 :attr:`Entry.key` 匹配）；
        * 仅在 ``patch`` 中存在的条目**按原顺序追加**；
        * :attr:`Entry.metadata` 采用浅层合并（冲突时 patch 胜出）。

        后端如需更精细的合并逻辑（如 Crowdin 的批准标志）可覆盖本方法。
        """
        by_key: Dict[str, Entry] = {entry.key: entry for entry in base}
        for patch_entry in patch:
            if patch_entry.key in by_key:
                original = by_key[patch_entry.key]
                merged_metadata = {**original.metadata, **patch_entry.metadata}
                by_key[patch_entry.key] = Entry(
                    key=patch_entry.key,
                    source_text=patch_entry.source_text or original.source_text,
                    target_text=patch_entry.target_text or original.target_text,
                    context=patch_entry.context or original.context,
                    comment=patch_entry.comment or original.comment,
                    en_terms=list(patch_entry.en_terms) if patch_entry.en_terms else list(original.en_terms),
                    terms=list(patch_entry.terms) if patch_entry.terms else list(original.terms),
                    metadata=merged_metadata,
                )
            else:
                by_key[patch_entry.key] = patch_entry
        return list(by_key.values())

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    @staticmethod
    def _read_text(path: str, encoding: str) -> str:
        p = Path(path)
        if not p.exists():
            raise SourceError(f"Source file not found: {path}")
        try:
            return p.read_text(encoding=encoding)
        except OSError as exc:
            raise SourceError(f"Failed to read {path}: {exc}") from exc

    @staticmethod
    def _write_text(path: str, content: str, encoding: str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            p.write_text(content, encoding=encoding)
        except OSError as exc:
            raise SourceError(f"Failed to write {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
_REGISTRY: Dict[str, Type[LocalizationSource]] = {}


def register_source(name: str) -> Callable[[Type[LocalizationSource]], Type[LocalizationSource]]:
    """类装饰器：将一个 :class:`LocalizationSource` 实现注册为 ``name`` 格式。

    示例::

        @register_source("json")
        class JsonSource(LocalizationSource):
            ...
    """

    def decorator(cls: Type[LocalizationSource]) -> Type[LocalizationSource]:
        key = name.lower()
        cls.format_name = key
        _REGISTRY[key] = cls
        return cls

    return decorator


def get_source_class(name: str) -> Type[LocalizationSource]:
    """查找 ``name`` 对应的注册类。

    异常：
        UnknownSourceFormatError: ``name`` 未注册时抛出。
    """
    key = (name or "").lower()
    if key not in _REGISTRY:
        raise UnknownSourceFormatError(
            f"Unknown source format '{name}'. Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[key]


def registered_formats() -> List[str]:
    """返回当前已注册的格式名称列表（排序后）。"""
    return sorted(_REGISTRY)


__all__ = [
    "Entry",
    "LocalizationSource",
    "get_source_class",
    "register_source",
    "registered_formats",
]
