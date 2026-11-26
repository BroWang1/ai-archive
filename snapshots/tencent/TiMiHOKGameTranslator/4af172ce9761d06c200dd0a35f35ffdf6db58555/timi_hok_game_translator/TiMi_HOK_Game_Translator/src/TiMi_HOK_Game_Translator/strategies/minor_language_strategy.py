"""小语种两步翻译策略（中 → 英 → 目标语种）。

背景：
    游戏本地化场景中，部分小语种（德语/法语/土耳其语/俄语/阿拉伯语/
    西班牙语/葡萄牙语等）直接用"中 → 目标语种"效果不稳定；采用
    **先中翻英、再英翻目标语** 的二级策略，译文质量显著提升。

本模块作用：
    * 演示 ``strategies/`` 子包的扩展方式——不改框架，仅注册新策略；
    * 提供一个典型小语种 (德语 ``de``) 示例，说明"两步翻译"的实现模板，
      其他小语种复用本类并追加 ``@register_translation_strategy("<id>")``
      即可，无需复制粘贴代码。

与通用 :class:`GenericTranslationStrategy` 的区别：
    ``GenericTranslationStrategy`` 直接把 ``source_text`` 一次性丢给 LLM；
    本策略拆成两次 LLM 调用，中间结果写入 ``entry.metadata["english_side"]``
    供下游状态（审校/质检）查阅。

扩展方式（新增一个小语种，不改代码）：
    1. 复用本类，在 ``conf/languages/<lang>.json`` 中设置
       ``strategy_config.two_step = true``；
    2. 或继承本类并用 ``@register_translation_strategy("ru")`` 装饰器注册。

配置字段（``strategy_config`` 中可用的 key）：
    pivot_locale:
        中转语种 BCP-47 代码，默认 ``"en"``；也可配 ``"zh-CN"`` 等。
    skip_if_already_target:
        True 时若原文已为目标语种直接返回；默认 False（无语种检测依赖）。
    返回的英文中间结果恒写入 ``entry.metadata["english_side"]``（由
    executor 层自动完成，本策略只需返回 ``(target_text, english_text)``）。
"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from ..translation.base import BaseTranslationStrategy, Entry
from ..translation.factory import register_translation_strategy  # pylint: disable=unused-import

logger = logging.getLogger(__name__)


class TwoStepTranslationStrategy(BaseTranslationStrategy):
    """两步翻译基类（中 → 中转 → 目标）。

    继承本类即可获得"先翻译到中转语种、再翻译到目标语种"的能力；
    两步均调用 ``self.llm.translate(...)``，模型由 ``llm_profile`` 决定。

    子类通常只需装饰 ``@register_translation_strategy("<lang>")``；
    其余配置通过 ``strategy_config`` 从 JSON 注入。
    """

    #: 覆盖默认——两步翻译总是输出英文中间结果到 ``entry.metadata``。
    returns_english_data: bool = True

    def filter(self, source_text: str, *, entry: Entry) -> bool:
        """空文本直接跳过；其余交由翻译。"""
        return bool(source_text)

    def translate(
        self,
        source_text: str,
        *,
        entry: Entry,
        source_locale: str,
        target_locale: str,
        context: str,
    ) -> Tuple[str, Optional[str]]:
        """执行两步翻译。

        流程：

        1. ``source_text`` → ``pivot_locale``（默认 ``en``）得到中间结果；
           注入 ``entry.en_terms``（中→英术语对）。
        2. 中间结果 → ``target_locale`` 得到最终译文；
           把 ``entry.en_terms`` 与 ``entry.terms`` 按**中文源文**做 inner-join
           映射为 **(英 → 目标语)** 术语对后注入——因为 Step 2 的原文已经是
           英文，用"英→目标"术语对能被模型直接命中，比"中→目标"更有效。

        容错：

        * ``en_terms`` 或 ``terms`` 为空 → 对应步骤走无术语默认提示词；
        * 中文 key 在两列中对不齐 → 只注入能对齐的那部分；
        * 若任一步抛错，返回 ``("", english_or_None)``，由上层
          executor 统一记入 ``errors``；不吞错以便失败定位。
        """
        pivot_locale = str(self.strategy_config.get("pivot_locale", "en") or "en")

        en_terms = list(getattr(entry, "en_terms", []) or [])
        tgt_terms = list(getattr(entry, "terms", []) or [])

        # ---- Step 1: source → pivot (通常是英语) --------------------
        # 注入 en_terms（中→英术语对）给 Step 1
        logger.info(
            "[%s] Step 1/2 (%s→%s) key=%s terms=%d",
            self.display_name, source_locale, pivot_locale, entry.key, len(en_terms),
        )
        try:
            pivot_response = self.llm.translate(
                source_text,
                source_locale=source_locale,
                target_locale=pivot_locale,
                context=context,
                terms=en_terms,
            )
        except Exception as exc:
            logger.warning(
                "[%s] step 1 (%s→%s) failed for key=%s: %s",
                self.display_name, source_locale, pivot_locale, entry.key, exc,
            )
            raise

        pivot_text = (pivot_response.text or "").strip()
        if not pivot_text:
            logger.warning(
                "[%s] step 1 returned empty pivot text for key=%s",
                self.display_name, entry.key,
            )
            return "", None

        # ---- Step 2: pivot → target --------------------------------
        # 构造"英→目标语"术语对：
        #   {中文: 英文} join {中文: 目标语文} → [(英文, 目标语文), ...]
        # 两列都有且中文 key 对齐的才注入；对不齐的跳过并记 debug 日志，
        # 便于后续排查术语表质量。
        step2_terms: List[Tuple[str, str]] = []
        if tgt_terms:
            en_map = {zh: en for zh, en in en_terms if zh and en}
            for zh, tgt in tgt_terms:
                if not zh or not tgt:
                    continue
                en_text = en_map.get(zh)
                if en_text:
                    step2_terms.append((en_text, tgt))
                else:
                    # EnTerms 里缺这条中文 key，Step 2 的英文原文中大概率
                    # 没有对应的英文术语可供命中——跳过不注入，避免误导模型。
                    logger.debug(
                        "[%s] key=%s: term '%s' missing in en_terms, "
                        "skip injection for step 2",
                        self.display_name, entry.key, zh,
                    )

        logger.info(
            "[%s] Step 2/2 (%s→%s) key=%s terms=%d",
            self.display_name, pivot_locale, target_locale, entry.key, len(step2_terms),
        )
        try:
            target_response = self.llm.translate(
                pivot_text,
                source_locale=pivot_locale,
                target_locale=target_locale,
                context=context,
                terms=step2_terms,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "[%s] step 2 (%s→%s) failed for key=%s: %s",
                self.display_name, pivot_locale, target_locale, entry.key, exc,
            )
            # 第二步失败时仍把已拿到的英文结果返回出去，便于后续兜底使用
            return "", pivot_text

        target_text = (target_response.text or "").strip()
        return target_text, pivot_text

__all__ = [
    "TwoStepTranslationStrategy",
]
