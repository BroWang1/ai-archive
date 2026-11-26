"""纯配置驱动的翻译策略。

新增一个语种一般无需写代码：

1. 在 ``<languages_dir>/<lang>.json`` 中声明 ``strategy_config``（展示名、
   可选 prompt 模板等）——``languages_dir`` 由 ``config.yaml`` 指定，
   本仓库惯用 ``conf/languages``，demo 默认 ``configs/languages``；
2. 以 ``--language <lang>`` 运行流水线。

:class:`GenericTranslationStrategy` 会读取该 JSON，将非空条目送给当前配置的
:class:`~TiMi_HOK_Game_Translator.llm.LLMClient`，并返回结果。

如需更复杂的能力（自定义过滤、多模型路由、同行广播等），请继承
:class:`BaseTranslationStrategy` 并使用 :func:`register_translation_strategy` 注册。
"""

from __future__ import annotations

import logging
from typing import Optional, Tuple

from .base import BaseTranslationStrategy, Entry

logger = logging.getLogger(__name__)


class GenericTranslationStrategy(BaseTranslationStrategy):
    """完全由 ``strategy_config`` 驱动的零代码策略。

    支持的 ``strategy_config`` 字段：

    ================================  ===============================================================
    Key                               含义
    ================================  ===============================================================
    ``display_name``                  日志中使用的人可读名称。
    ``prompt_template``               非空时作为 ``context`` 传递给 LLM。
    ``allow_empty``                   True 时接受空 ``source_text`` 并直接返回。
    ``skip_predicate``                可调用对象 ``(text, entry) -> bool``；True 表示跳过翻译。
    ``use_concurrent_by_default``     :meth:`process` 默认是否使用并发执行。
    ``default_max_workers``           并发执行器线程池大小。
    ``batch_size``                    首选批量大小（目前仅用于上报）。
    ``returns_english_data``          同时向 LLM 索取英文侧译。
    ================================  ===============================================================

    未知 key 保留在 :attr:`strategy_config` 中，子类可通过
    ``self.strategy_config[key]`` 读取。
    """

    language_id = "generic"

    def filter(self, source_text: str, *, entry: Entry) -> bool:
        # 用户自定义谓词优先于内置行为。
        predicate = self.strategy_config.get("skip_predicate")
        if callable(predicate):
            try:
                return not bool(predicate(source_text, entry))
            except Exception as exc:  # pylint: disable=broad-except  # noqa: BLE001
                logger.warning(
                    "[%s] skip_predicate raised for key=%s: %s — treating as skip",
                    self.display_name, entry.key, exc,
                )
                return False

        if source_text:
            return True
        return bool(self.strategy_config.get("allow_empty", False))

    def translate(
        self,
        source_text: str,
        *,
        entry: Entry,
        source_locale: str,
        target_locale: str,
        context: str,
    ) -> Tuple[str, Optional[str]]:
        template = self.strategy_config.get("prompt_template", "")
        if template:
            try:
                effective_context = template.format(text=source_text, context=context)
            except (KeyError, IndexError) as exc:
                logger.debug(
                    "[%s] prompt_template format failed (%s); using raw context",
                    self.display_name, exc,
                )
                effective_context = context
        else:
            effective_context = context

        response = self.llm.translate(
            source_text,
            source_locale=source_locale,
            target_locale=target_locale,
            context=effective_context,
            terms=list(getattr(entry, "terms", []) or []),
        )
        english: Optional[str] = None
        if self.returns_english_data:
            english = response.metadata.get("english_side") if response.metadata else None
        return response.text, english


__all__ = ["GenericTranslationStrategy"]
