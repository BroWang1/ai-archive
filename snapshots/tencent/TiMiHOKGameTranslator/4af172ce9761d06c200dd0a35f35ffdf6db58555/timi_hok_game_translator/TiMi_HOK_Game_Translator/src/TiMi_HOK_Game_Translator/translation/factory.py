"""翻译策略的注册表与工厂。

框架支持三种策略绑定方式，优先级从高到低：

* **YAML 配置声明**——在 ``conf/languages/<lang>.yaml`` 的 ``strategy_config``
  里加 ``class: TwoStepTranslationStrategy``（或完整 import 路径，如
  ``my_pkg.strategies.MyStrategy``）。这是**推荐**方式，零代码扩展，
  运维/测试同学也能自助切换策略。
* **语种专属子类**——用户继承 :class:`BaseTranslationStrategy` 并使用
  ``@register_translation_strategy("vi")`` 装饰器；当 ``language_id="vi"``
  时，:func:`get_translation_strategy` 会返回该子类的实例。适合策略有
  大量重写/定制逻辑的场景。
* **纯配置内置回退**——以上两种都没匹配到时返回
  :class:`GenericTranslationStrategy`，以 profile 的 ``strategy_config`` 初始化。

本工厂**不携带**任何与具体游戏绑定的子类，保证这份开源包干净。
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Callable, Dict, List, Optional, Type

from .base import BaseTranslationStrategy, SiblingBroadcaster
from .generic_strategy import GenericTranslationStrategy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 注册表
# ---------------------------------------------------------------------------
_REGISTRY: Dict[str, Type[BaseTranslationStrategy]] = {}

#: 内置策略类"短名 → 类"映射表。
#:
#: 用于 YAML 中 ``strategy_config.class`` 字段的声明式查找——用户在
#: ``conf/languages/<lang>.yaml`` 里写 ``class: TwoStepTranslationStrategy``
#: 即可直接把该语种绑定到两步翻译策略，无需在代码里加
#: ``@register_translation_strategy`` 装饰器。
#:
#: 支持三种写法（均不区分大小写）：
#:   1. 短名：``"TwoStepTranslationStrategy"`` 或 ``"two_step"``；
#:   2. 完整 import 路径：``"my_pkg.my_mod.MyStrategy"``（含 ``.``）；
#:   3. 留空 / 省略 ``class`` 字段 → 走装饰器注册表 → 兜底 Generic。
#:
#: 注册表在 :func:`_ensure_builtin_strategies_loaded` 首次调用后填充，
#: 避免模块级循环 import。
_BUILTIN_STRATEGIES: Dict[str, Type[BaseTranslationStrategy]] = {}

#: 懒加载开关——首次调用 get_translation_strategy 时自动 import
#: ``TiMi_HOK_Game_Translator.strategies`` 子包，触发其内所有策略装饰器注册。
#: 不在模块级 import 以避免循环依赖。
_STRATEGIES_PKG_LOADED = False


def _ensure_builtin_strategies_loaded() -> None:
    """首次调用时导入 ``TiMi_HOK_Game_Translator.strategies`` 以触发装饰器注册。

    使用模块级 ``_STRATEGIES_PKG_LOADED`` 标记保证只做一次；
    导入失败时记 debug 日志但不抛错，保证框架在没有 strategies 子包时
    也能正常工作。

    同时填充 :data:`_BUILTIN_STRATEGIES` 短名表，供
    :func:`_resolve_strategy_class` 按 YAML ``class`` 字段查找。
    """
    global _STRATEGIES_PKG_LOADED
    if _STRATEGIES_PKG_LOADED:
        return
    _STRATEGIES_PKG_LOADED = True
    try:
        import importlib

        importlib.import_module("TiMi_HOK_Game_Translator.strategies")
    except ImportError as exc:  # pragma: no cover — strategies 可被用户删除
        logger.debug(
            "TiMi_HOK_Game_Translator.strategies not loaded (%s); only GenericTranslationStrategy available",
            exc,
        )

    # 填充内置短名表（延迟 import 避免模块级循环依赖）
    _BUILTIN_STRATEGIES["GenericTranslationStrategy"] = GenericTranslationStrategy
    _BUILTIN_STRATEGIES["generic"] = GenericTranslationStrategy
    try:
        from ..strategies.minor_language_strategy import TwoStepTranslationStrategy

        _BUILTIN_STRATEGIES["TwoStepTranslationStrategy"] = TwoStepTranslationStrategy
        _BUILTIN_STRATEGIES["two_step"] = TwoStepTranslationStrategy
    except ImportError as exc:  # pragma: no cover — strategies 子包可被用户删除
        logger.debug(
            "TwoStepTranslationStrategy not available (%s); YAML class='TwoStepTranslationStrategy' will fail",
            exc,
        )


def _resolve_strategy_class(
    strategy_config: Optional[Dict[str, Any]],
) -> Optional[Type[BaseTranslationStrategy]]:
    """解析 ``strategy_config.class`` 字段 → 策略类。

    支持三种写法：

    1. **留空 / 省略**：返回 ``None``，调用方继续走装饰器注册表与兜底。
    2. **短名**（无 ``.``）：从 :data:`_BUILTIN_STRATEGIES` 查，不区分大小写。
    3. **完整 import 路径**（含 ``.``）：如 ``my_pkg.strategies.Russian``，
       走 :func:`importlib.import_module` + :func:`getattr`。

    若查找/导入失败，记 WARNING 日志并返回 ``None``，让调用方降级到装饰器
    注册表或 Generic 兜底——保持配置错误时流水线仍可跑的宽容性。
    """
    if not strategy_config:
        return None
    raw = strategy_config.get("class")
    if not raw:
        return None
    name = str(raw).strip()
    if not name:
        return None

    # 情况 3：完整 import 路径
    if "." in name:
        module_path, _, class_name = name.rpartition(".")
        try:
            module = importlib.import_module(module_path)
            cls = getattr(module, class_name)
        except (ImportError, AttributeError) as exc:
            logger.warning(
                "strategy_config.class=%r: cannot import %s.%s (%s); "
                "falling back to decorator registry",
                name, module_path, class_name, exc,
            )
            return None
        if not isinstance(cls, type) or not issubclass(cls, BaseTranslationStrategy):
            logger.warning(
                "strategy_config.class=%r resolved to %r which is not a "
                "BaseTranslationStrategy subclass; ignoring",
                name, cls,
            )
            return None
        return cls

    # 情况 2：短名（不区分大小写精确匹配）
    cls = _BUILTIN_STRATEGIES.get(name)
    if cls is None:
        # 大小写不敏感兜底查找
        lowered = name.lower()
        for key, value in _BUILTIN_STRATEGIES.items():
            if key.lower() == lowered:
                cls = value
                break
    if cls is None:
        logger.warning(
            "strategy_config.class=%r is not a known builtin short name "
            "(available: %s); falling back to decorator registry",
            name, sorted(_BUILTIN_STRATEGIES.keys()),
        )
        return None
    return cls


def register_translation_strategy(
    language_id: str,
    *,
    replace: bool = False,
) -> Callable[[Type[BaseTranslationStrategy]], Type[BaseTranslationStrategy]]:
    """类装饰器：将 ``cls`` 绑定到 ``language_id``。

    参数：
        language_id: 本策略服务的 BCP-47 标签或产品 slug。
        replace: ``False``（默认）时，重复绑定会抛出 :class:`ValueError`；
            测试/插件 bootstrap 情景下可传 ``True`` 强行覆盖。

    示例::

        @register_translation_strategy("vi")
        class VietnameseStrategy(BaseTranslationStrategy):
            ...
    """

    def _decorator(cls: Type[BaseTranslationStrategy]) -> Type[BaseTranslationStrategy]:
        if not issubclass(cls, BaseTranslationStrategy):
            raise TypeError(
                f"{cls.__name__} must inherit from BaseTranslationStrategy"
            )
        if not replace and language_id in _REGISTRY and _REGISTRY[language_id] is not cls:
            raise ValueError(
                f"Language id {language_id!r} is already bound to "
                f"{_REGISTRY[language_id].__name__}. Pass replace=True to override."
            )
        _REGISTRY[language_id] = cls
        cls.language_id = language_id
        return cls

    return _decorator


def registered_languages() -> List[str]:
    """返回当前已注册的语种 id 列表（排序后）。"""
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# 工厂
# ---------------------------------------------------------------------------
def get_translation_strategy(
    language_id: str,
    *,
    llm: Optional[Any] = None,
    strategy_config: Optional[Dict[str, Any]] = None,
    source_locale: str = "",
    target_locale: str = "",
    sibling_broadcaster: Optional[SiblingBroadcaster] = None,
) -> BaseTranslationStrategy:
    """返回已初始化好的 ``language_id`` 对应策略实例。

    查找顺序（新）：

    1. **YAML 显式声明** ``strategy_config.class``（短名或完整 import 路径）——
       推荐方式，零代码扩展；
    2. 装饰器注册表中的精确匹配（``@register_translation_strategy("vi")``）；
    3. 通配符注册（如 ``@register_translation_strategy("vi_*")``）——
       待实现；
    4. 以 ``strategy_config`` 初始化的 :class:`GenericTranslationStrategy`。

    返回的实例**不缓存**，多次调用之间 ``strategy_config`` 可以自由修改。
    """
    _ensure_builtin_strategies_loaded()

    # 优先级 1：YAML strategy_config.class 显式声明
    cls: Optional[Type[BaseTranslationStrategy]] = _resolve_strategy_class(strategy_config)
    source = "yaml.class"

    # 优先级 2：装饰器注册表
    if cls is None:
        cls = _REGISTRY.get(language_id)
        if cls is not None:
            source = "decorator"

    # 优先级 3：Generic 兜底
    if cls is None:
        cls = GenericTranslationStrategy
        source = "generic_fallback"

    strategy = cls(
        language_id=language_id,
        llm=llm,
        strategy_config=strategy_config,
        source_locale=source_locale,
        target_locale=target_locale,
        sibling_broadcaster=sibling_broadcaster,
    )
    if source == "yaml.class":
        logger.info(
            "Translation strategy for %r resolved via YAML strategy_config.class → %s",
            language_id, cls.__name__,
        )
    elif source == "generic_fallback":
        logger.debug(
            "No bespoke strategy for %r — using GenericTranslationStrategy",
            language_id,
        )
    else:  # decorator
        logger.debug(
            "Translation strategy for %r resolved via decorator registry → %s",
            language_id, cls.__name__,
        )
    return strategy


__all__ = [
    "get_translation_strategy",
    "register_translation_strategy",
    "registered_languages",
]
