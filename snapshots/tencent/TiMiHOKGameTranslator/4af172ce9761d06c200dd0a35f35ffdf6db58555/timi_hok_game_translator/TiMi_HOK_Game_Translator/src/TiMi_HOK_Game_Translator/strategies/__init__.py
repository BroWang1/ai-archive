"""TiMi_HOK_Game_Translator.strategies 子包。

本包提供可被 YAML/装饰器两种方式复用的翻译策略类。两种扩展方式：

**方式一（推荐）：YAML 配置化**
    在 ``conf/languages/<lang>.yaml`` 的 ``strategy_config`` 里加::

        strategy_config:
          class: TwoStepTranslationStrategy   # 或 two_step
          pivot_locale: en

    零代码新增/切换语种。支持的内置短名见
    :data:`TiMi_HOK_Game_Translator.translation.factory._BUILTIN_STRATEGIES`。

**方式二：装饰器注册**
    继承 :class:`TwoStepTranslationStrategy` 或
    :class:`~TiMi_HOK_Game_Translator.translation.base.BaseTranslationStrategy`，
    追加 ``@register_translation_strategy("<lang>")``。适合策略类需要
    重写 ``filter`` / ``translate`` 等方法的深度定制场景。

当前内置示例：
    * :mod:`.minor_language_strategy` ——"中 → 英 → 目标"两步翻译模板，
      已注册 ``de``（德语）；其它小语种可通过 YAML ``class:
      TwoStepTranslationStrategy`` 直接复用，或继承后加装饰器注册。

注意：
    import 本模块（``import TiMi_HOK_Game_Translator.strategies``）会触发所有子模块
    的装饰器执行，从而完成注册。工厂层会在首次创建策略时统一导入。
"""

from . import minor_language_strategy  # noqa: F401 — 导入即注册

__all__ = ["minor_language_strategy"]
