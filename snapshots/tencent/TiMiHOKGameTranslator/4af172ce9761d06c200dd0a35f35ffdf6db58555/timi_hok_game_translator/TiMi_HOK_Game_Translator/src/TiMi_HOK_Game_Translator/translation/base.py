"""翻译策略层的基类与数据对象。

设计目标：

* **三段式契约**：子类只需实现
  :meth:`BaseTranslationStrategy.filter`（判定源文本是否送译）与
  :meth:`BaseTranslationStrategy.translate`（实际调用 LLM/外部服务）；
  完整流水线 :meth:`process` 由本基类提供。
* **串行/并发模式**均位于 :mod:`.executors`，运行时透明选择。
* **后端无关**：策略只依赖 :class:`~TiMi_HOK_Game_Translator.llm.LLMClient` 接口，
  不绑定具体厂商 SDK。LLM 实例由工厂注入。
* **可插拔副作用**：去重完成后，:class:`SiblingBroadcaster` 会被调用，
  便于将已批准译文广播回具有相同源文本的其他行。
* **不假设业务**：不硬编码 Excel 列名、不默认繁转简、不回退到某个厂商；
  这些行为均由**用户自定义**策略子类提供。
"""

from __future__ import annotations

import abc
import logging
import threading
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    runtime_checkable,
)

from ..commons import DEFAULT_LLM_BATCH_SIZE
from ..llm import LLMClient, LocalMockLLM

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据对象
# ---------------------------------------------------------------------------
@dataclass
class Entry:
    """单个翻译单元。

    本对象是 Source / Strategy / LLM / Platform 之间的**传输格式**。
    它故意不携带 Excel 专属列；格式相关的字段一律放入 :attr:`metadata`。

    字段：
        key: 条目的稳定标识（一般为 hash 或开发者自定义 key），在单个源中必须唯一。
        source_text: 待翻译的原文。
        target_text: 翻译后的目标文本（翻译前为空）。
        context: 选传给 LLM 的上下文提示（如发言角色、UI 位置等）。
        comment: 自由形式的备注，给翻译者/审校者看。
        en_terms: 中→英术语对（``[(zh, en), ...]``），两步翻译 Step 1 使用。
        terms: 中→目标语术语对（``[(zh, target), ...]``），一步策略直接使用，
            两步策略 Step 2 使用（会先与 en_terms 做映射转为英→目标语术语）。
        metadata: 后端自定义字段，Source 在
            :meth:`~TiMi_HOK_Game_Translator.sources.LocalizationSource.load` 时填充，
            在 :meth:`~TiMi_HOK_Game_Translator.sources.LocalizationSource.dump` 时读取。
    """

    key: str
    source_text: str = ""
    target_text: str = ""
    context: str = ""
    comment: str = ""
    en_terms: List[Tuple[str, str]] = field(default_factory=list)
    terms: List[Tuple[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TranslationResult:
    """一次策略 :meth:`~BaseTranslationStrategy.process` 调用的聚合结果。

    字段：
        translated: 已填充 ``target_text`` 的条目。
        untranslated: 被 :meth:`~BaseTranslationStrategy.filter` 拒绝、
            或在 :meth:`~BaseTranslationStrategy.translate` 时失败的条目。
        errors: 以 :attr:`Entry.key` 为键的错误描述（缺失 key
            表示“被过滤但无错”）。
        stats: 计数器，供日志/监控使用（``total``/``success``/``failed``/
            ``duration_seconds`` 等）。
    """

    translated: List[Entry] = field(default_factory=list)
    untranslated: List[Entry] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)
    stats: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 可选副作用 Protocol
# ---------------------------------------------------------------------------
@runtime_checkable
class SiblingBroadcaster(Protocol):
    """将翻译结果广播到同行条目的可选回调。

    场景：源文件中多个行可能共享相同的 ``source_text`` 但不同 key；
    策略在送入 LLM 前会去重。审校通过后，需将结果广播回全部同行
    行，保证最终 dump 完整。

    ``SiblingBroadcaster`` 对每个去重后的已译条目调用一次，返回一个
    正整数表示受影响的行数（仅供日志使用）。
    """

    def broadcast(self, translated: Entry, all_entries: Sequence[Entry]) -> int:
        ...


class NoopSiblingBroadcaster:
    """默认的空 :class:`SiblingBroadcaster` 实现（什么也不做）。

    不需要同行广播时可将 ``sibling_broadcaster`` 参数置空，内部会使用本类。
    """

    def broadcast(self, translated: Entry, all_entries: Sequence[Entry]) -> int:  # noqa: D401,ARG002
        return 0


# ---------------------------------------------------------------------------
# BaseTranslationStrategy
# ---------------------------------------------------------------------------
class BaseTranslationStrategy(abc.ABC):
    """单语种翻译策略的抽象基类。

    子类通过类属性 :attr:`language_id`（或 ``@register_translation_strategy`` 装饰器）
    声明自己服务的语种，并实现两个方法：

    * :meth:`filter`——判定 ``source_text`` 是否应送入 LLM（“已翻译/包含禁用字符”
      等语种专属规则在此处）；
    * :meth:`translate`——实际调用 LLM 并返回译文（可选额外返回一份英文侧译，
      用于两步翻译策略）。

    其余所有能力——分批、并发、进度上报、错误汇总、去重、同行广播——均由
    :meth:`process` 内置实现。

    字段：
        language_id: 本策略服务的 BCP-47/产品 slug。
        display_name: 日志中使用的人可读名称。
        source_locale / target_locale: BCP-47 标签。为空时可以从
            :meth:`translate` 的 context 参数中传入。
        use_concurrent_by_default: :meth:`process` 默认是否采用并发执行器。
        default_max_workers: 并发执行器的线程池大小。
        batch_size: 调用 :meth:`LLMClient.batch_translate` 时的首选批量大小。
        progress_log_interval: :meth:`process` 中记录进度日志的频率。
        llm: 默认 :meth:`translate` 使用的 LLM 客户端（子类可忽略它并自行选择）。
        strategy_config: 从 :attr:`LanguageProfile.strategy_config` 拷贝的自由字典，
            子类从中读取语种专用参数。
        sibling_broadcaster: 可选的译后副作用回调。
    """

    # -- 类级默认值，子类按需覆盖。 -------------------------
    language_id: str = ""
    display_name: str = ""
    source_locale: str = ""
    target_locale: str = ""
    use_concurrent_by_default: bool = True
    default_max_workers: int = 5
    batch_size: int = DEFAULT_LLM_BATCH_SIZE
    progress_log_interval: int = 10
    returns_english_data: bool = False

    def __init__(
        self,
        *,
        language_id: str = "",
        llm: Optional[LLMClient] = None,
        strategy_config: Optional[Dict[str, Any]] = None,
        source_locale: str = "",
        target_locale: str = "",
        sibling_broadcaster: Optional[SiblingBroadcaster] = None,
    ) -> None:
        # 实例属性遮盖类属性，使子类既可通过类变量配置、也可通过构造参数配置。
        if language_id:
            self.language_id = language_id
        if source_locale:
            self.source_locale = source_locale
        if target_locale:
            self.target_locale = target_locale

        self.strategy_config: Dict[str, Any] = dict(strategy_config or {})
        self._apply_strategy_config()

        # 默认使用 LocalMockLLM，保证开箱即用。
        self.llm: LLMClient = llm or LocalMockLLM()
        self.sibling_broadcaster: SiblingBroadcaster = (
            sibling_broadcaster or NoopSiblingBroadcaster()
        )

        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # 配置管道
    # ------------------------------------------------------------------
    _CONFIG_ATTRS: Tuple[str, ...] = (
        "display_name",
        "source_locale",
        "target_locale",
        "use_concurrent_by_default",
        "default_max_workers",
        "batch_size",
        "progress_log_interval",
        "returns_english_data",
    )

    def _apply_strategy_config(self) -> None:
        """从 :attr:`strategy_config` 中拉取内置字段并赋值到 ``self``。

        不属于 :data:`_CONFIG_ATTRS` 的 key 会保留在字典中，供子类自行消费。
        """
        for name in self._CONFIG_ATTRS:
            if name in self.strategy_config:
                setattr(self, name, self.strategy_config[name])
        if not self.display_name:
            self.display_name = self.language_id or self.__class__.__name__

    # ------------------------------------------------------------------
    # 抽象接口
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def filter(self, source_text: str, *, entry: Entry) -> bool:
        """当 ``source_text`` 应被翻译时返回 ``True``。

        在 :meth:`translate` **之前**调用；返回 ``False`` 时条目会被放入
        :attr:`TranslationResult.untranslated`，不会到达 LLM。
        """

    @abc.abstractmethod
    def translate(
        self,
        source_text: str,
        *,
        entry: Entry,
        source_locale: str,
        target_locale: str,
        context: str,
    ) -> Tuple[str, Optional[str]]:
        """翻译 ``source_text`` 并返回 ``(target_text, english_side)``。

        第二个返回值是英文侧译（``en_data`` 位）：同时产出英文枚译的策略可在此返回；
        否则为 ``None``。
        """

    # ------------------------------------------------------------------
    # 可选钩子
    # ------------------------------------------------------------------
    def post_translate(self, result: TranslationResult) -> None:  # noqa: B027 — 可选钩子
        """:meth:`process` 完成后回调。

        默认什么也不做。子类可重写以添加术语校验、质量门禁、写临时文件、
        POST 监控数据等副作用。
        """

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    def process(
        self,
        entries: Sequence[Entry],
        *,
        source_locale: str = "",
        target_locale: str = "",
        use_concurrent: Optional[bool] = None,
        max_workers: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> TranslationResult:
        """端到端翻译 ``entries``，遵循 filter / 并发策略。

        参数：
            entries: 待处理的条目列表。``source_text`` 相同的条目会先去重，
                只发往 LLM 一次，完成后通过 :attr:`sibling_broadcaster`
                广播回同行行。
            source_locale / target_locale: 本次调用的覆盖。为空时使用策略自己的默认值。
            use_concurrent: ``None`` 时使用策略默认值。
            max_workers: ``None`` 时使用策略默认值。
            progress_callback: 可选回调，``(done, total)`` 为参数，按
                :attr:`progress_log_interval` 频率回调。

        返回：
            :class:`TranslationResult`，包含已译/未译条目与汇总统计。
        """
        source_locale = source_locale or self.source_locale
        target_locale = target_locale or self.target_locale
        if use_concurrent is None:
            use_concurrent = self.use_concurrent_by_default
        if max_workers is None:
            max_workers = self.default_max_workers

        # --- 按 source_text 去重，保证相同原文只送一次 LLM。
        deduped, siblings = _deduplicate(entries)
        total = len(deduped)
        logger.info(
            "[%s] Processing %d entries (%d unique, concurrent=%s, workers=%d)",
            self.display_name, len(entries), total, use_concurrent, max_workers,
        )

        result = TranslationResult(stats={"total_input": len(entries), "unique": total})

        # --- 选择执行器。
        # 局部导入，保证 executors 为可选，并避免循环导入。
        if use_concurrent and total > 1:
            from .executors.concurrent import run_concurrent
            translated, untranslated, errors = run_concurrent(
                self, deduped,
                source_locale=source_locale,
                target_locale=target_locale,
                max_workers=max_workers,
                progress_callback=progress_callback,
            )
        else:
            from .executors.serial import run_serial
            translated, untranslated, errors = run_serial(
                self, deduped,
                source_locale=source_locale,
                target_locale=target_locale,
                progress_callback=progress_callback,
            )

        # --- 广播到同行行。
        sibling_extra: List[Entry] = []
        for tr in translated:
            broadcast_count = 0
            try:
                broadcast_count = self.sibling_broadcaster.broadcast(tr, entries)
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001 — 同行失败不致命
                logger.warning(
                    "[%s] Sibling broadcast failed for key=%s: %s",
                    self.display_name, tr.key, exc,
                )
            if broadcast_count:
                logger.debug(
                    "[%s] broadcaster touched %d sibling rows for key=%s",
                    self.display_name, broadcast_count, tr.key,
                )
            # 即使没有外部 broadcaster，也需将译文写回去重后隐藏的同行条目，
            # 保证调用方拿到完整的译文列表。
            for sibling in siblings.get(tr.source_text, ()):
                if sibling.key == tr.key:
                    continue
                sibling.target_text = tr.target_text
                sibling_extra.append(sibling)
        translated.extend(sibling_extra)

        result.translated = translated
        result.untranslated = untranslated
        result.errors = errors
        result.stats.update({
            "success": len(translated),
            "failed": len(untranslated),
        })

        self.post_translate(result)
        return result

    # ------------------------------------------------------------------
    # 自省
    # ------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"{self.__class__.__name__}"
            f"(language_id={self.language_id!r}, display_name={self.display_name!r})"
        )


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _deduplicate(
    entries: Sequence[Entry],
) -> Tuple[List[Entry], Dict[str, List[Entry]]]:
    """将 ``entries`` 拆分为 ``(按 source_text 去重后的列表, siblings_map)``。

    空的 ``source_text`` 作为各自独立的 key，避免不小心将多个空行合并。
    """
    unique: List[Entry] = []
    siblings: Dict[str, List[Entry]] = {}
    seen: Dict[str, Entry] = {}

    for entry in entries:
        text = entry.source_text or ""
        if not text:
            unique.append(entry)
            continue
        if text in seen:
            siblings.setdefault(text, []).append(entry)
        else:
            seen[text] = entry
            unique.append(entry)

    return unique, siblings


__all__ = [
    "BaseTranslationStrategy",
    "Entry",
    "NoopSiblingBroadcaster",
    "SiblingBroadcaster",
    "TranslationResult",
]
