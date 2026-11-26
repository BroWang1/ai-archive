"""可插拔的翻译策略层。

:mod:`TiMi_HOK_Game_Translator.llm` 负责**调用**底层服务（发送 prompt、拿返回）；
本包负责**编排**：

* 单语种过滤规则（如"目标为越南语时，
  已含泰文的条目不送翻"）；
* 单语种 prompt / 模型选择；
* 串行 vs 并发执行模式；
* 译后钩子（术语校验、同行广播等）；
* 结果格式化与去重。

用户可通过 :func:`register_translation_strategy`
装饰器注册自定义策略；内置的
:class:`GenericTranslationStrategy` 纯配置驱动，
新增语种一般无需写代码。

对外 API::

    from TiMi_HOK_Game_Translator.translation import (
        BaseTranslationStrategy,
        GenericTranslationStrategy,
        Entry, TranslationResult,
        register_translation_strategy,
        get_translation_strategy,
    )
"""

from .base import (
    BaseTranslationStrategy,
    Entry,
    SiblingBroadcaster,
    TranslationResult,
)
from .factory import (
    get_translation_strategy,
    register_translation_strategy,
    registered_languages,
)
from .generic_strategy import GenericTranslationStrategy

__all__ = [
    "BaseTranslationStrategy",
    "Entry",
    "GenericTranslationStrategy",
    "SiblingBroadcaster",
    "TranslationResult",
    "get_translation_strategy",
    "register_translation_strategy",
    "registered_languages",
]
