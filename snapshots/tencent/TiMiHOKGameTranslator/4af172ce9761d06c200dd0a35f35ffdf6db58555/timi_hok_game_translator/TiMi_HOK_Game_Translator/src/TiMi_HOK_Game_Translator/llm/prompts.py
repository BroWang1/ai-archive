"""翻译提示词模板中心。

按**模型 provider**维度选择提示词模板，而不是按单个语种硬编码。
语种只负责"把 BCP-47 locale 代码映射为可读的语种名"（如 ``vi`` → ``越南语``
/ ``Vietnamese``），模板则按 provider 的调优偏好选择：

* **混元 HY-MT2**：使用官方推荐的中文提示词（含术语模式 / 结构化模式）；
* **其它 provider（OpenAI / Claude / Gemini / Venus / openai_compatible）**：
    - **源语=中文** → 使用中文 user 提示词 ``"将{src_cn}翻译成{tgt_cn}:{text}"``；
    - **源语≠中文** → 使用英文 system+user 提示词（对多数国际模型更友好）。

调用方::

    system, user = build_translation_prompt(
        provider="hunyuan_translation",
        source_locale="zh-CN",
        target_locale="vi",
        source_text="你好",
        format_type="plain",
    )
"""

from __future__ import annotations

from typing import Dict, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# BCP-47 → 中文语种名映射（混元翻译模型需要完整中文名）
# ---------------------------------------------------------------------------
LOCALE_CN_NAME: Dict[str, str] = {
    "zh": "中文",
    "zh-cn": "简体中文",
    "zh-tw": "台湾地区的繁体中文",
    "zh-hk": "香港地区的繁体中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "vi": "越南语",
    "th": "泰语",
    "id": "印度尼西亚语",
    "ms": "马来语",
    "fr": "法语",
    "de": "德语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "pt-br": "巴西葡萄牙语",
    "es": "西班牙语",
    "it": "意大利语",
    "tr": "土耳其语",
    "ar": "阿拉伯语",
    "nl": "荷兰语",
    "pl": "波兰语",
}

# BCP-47 → 英文语种名（OpenAI/Claude 等英文提示词场景使用）
LOCALE_EN_NAME: Dict[str, str] = {
    "zh": "Chinese",
    "zh-cn": "Simplified Chinese",
    "zh-tw": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "fr": "French",
    "de": "German",
    "ru": "Russian",
    "pt": "Portuguese",
    "pt-br": "Brazilian Portuguese",
    "es": "Spanish",
    "it": "Italian",
    "tr": "Turkish",
    "ar": "Arabic",
}

# 中文系源语的判定集合（lower-case）
_CHINESE_SOURCE_LOCALES = {"zh", "zh-cn", "zh-hans", "zh-tw", "zh-hk", "zh-hant"}


def locale_cn(
    locale: str,
    overrides: Optional[Dict[str, str]] = None,
) -> str:
    """BCP-47 代码转中文语种名。

    参数：
        locale: BCP-47 代码（``"vi"`` / ``"zh-tw"`` 等）。
        overrides: 可选的语种 JSON 覆盖字典（见 LanguageProfile.locale_names）；
            键使用 ``"cn"`` 时优先于内置字典。
    返回：
        用于提示词渲染的中文语种名；全部未命中时回落到 ``locale`` 本身。
    """
    if overrides:
        v = overrides.get("cn")
        if v:
            return v
    if not locale:
        return "目标语种"
    key = locale.strip().lower()
    return LOCALE_CN_NAME.get(key, LOCALE_CN_NAME.get(key.split("-")[0], locale))


def locale_en(
    locale: str,
    overrides: Optional[Dict[str, str]] = None,
) -> str:
    """BCP-47 代码转英文语种名。

    参数：
        locale: BCP-47 代码。
        overrides: 可选的语种 JSON 覆盖字典；键 ``"en"`` 优先于内置字典。
    返回：
        英文语种名；全部未命中时回落到 ``locale`` 本身。
    """
    if overrides:
        v = overrides.get("en")
        if v:
            return v
    if not locale:
        return "target language"
    key = locale.strip().lower()
    return LOCALE_EN_NAME.get(key, LOCALE_EN_NAME.get(key.split("-")[0], locale))


def _is_chinese_source(source_locale: str) -> bool:
    """判断源语种是否为中文系（含简体/繁体/港澳）。"""
    if not source_locale:
        return False
    return source_locale.strip().lower() in _CHINESE_SOURCE_LOCALES


# ---------------------------------------------------------------------------
# 混元 Hy-MT2 官方推荐提示词（docs/模型调用/混元调用指南.md 1830/2028 行）
# ---------------------------------------------------------------------------
_HUNYUAN_PLAIN = (
    "将以下文本翻译为 {target_lang}，注意只需要输出翻译后的结果，不要额外解释：\n"
    "{text}"
)

_HUNYUAN_STRUCTURED = (
    "# 任务目标\n"
    "将下方 source_text 中的 {format_type} 格式数据翻译为 {target_lang}。\n\n"
    "# 严格约束\n"
    "1. 结构锁定：绝对保持原有的 {format_type} 数据结构、缩进和层级完全不变。\n"
    "2. 选择性翻译：仅翻译面向用户展示的可见文本内容。\n"
    "3. 禁止修改：严禁翻译或更改任何代码标签、键名 (Key)、变量占位符（如 "
    "{{var}}、${{var}}、%s、%d 等）或代码属性。\n\n"
    "# 数据输入\n"
    "{text}"
)

# 术语模式提示词模板。``{term_pairs}`` 由代码按每条一行拼成
# ``<源文> 翻译成 <译文>``；``term_pairs`` 末尾不含换行。
_HUNYUAN_TERMINOLOGY = (
    "参考下面的翻译：\n"
    "{term_pairs}\n"
    "将以下文本翻译为 {target_lang}，注意只需要输出翻译后的结果，不要额外解释：\n"
    "\n"
    "{text}"
)

# 结构化格式判定（format_type → 混元接受的格式名）
_STRUCTURED_FORMATS = {
    "json": "JSON",
    "xml": "XML",
    "dtxml": "XML",
    "html": "HTML",
    "markdown": "Markdown",
    "md": "Markdown",
    "yaml": "YAML",
    "xliff": "XML",
}

# ---------------------------------------------------------------------------
# 通用英文 system/user 提示词（OpenAI / Claude 等）
# ---------------------------------------------------------------------------
_GENERIC_SYSTEM = (
    "You are a professional game localization translator. "
    "Preserve placeholders like {value}, {0}, %s, %d and inline tags verbatim. "
    "Return only the translation without any additional commentary."
)


def _build_hunyuan_prompt(
    target_locale: str,
    source_text: str,
    format_type: str,
    locale_names: Optional[Dict[str, str]] = None,
    terms: Optional[Sequence[Tuple[str, str]]] = None,
) -> Tuple[str, str]:
    """构造混元 Hy-MT2 的提示词。混元翻译模型不使用 system role。

    * ``terms`` 非空 → 走术语模式（:data:`_HUNYUAN_TERMINOLOGY`）；
    * ``format_type`` 为结构化格式 → 走结构化模板（:data:`_HUNYUAN_STRUCTURED`）；
    * 其它 → 走默认模板（:data:`_HUNYUAN_PLAIN`）。

    术语模式与结构化模式互斥；本框架业务约定术语优先（术语是对翻译结果的
    硬约束，结构化只是数据格式提示）。
    """
    target_lang = locale_cn(target_locale, locale_names)

    # 术语模式优先：有术语对就走术语模板
    if terms:
        term_pairs = "\n".join(
            f"{src} 翻译成 {dst}" for src, dst in terms if src and dst
        )
        if term_pairs:
            user = _HUNYUAN_TERMINOLOGY.format(
                term_pairs=term_pairs,
                target_lang=target_lang,
                text=source_text,
            )
            return "", user

    fmt_key = (format_type or "plain").lower()
    if fmt_key in _STRUCTURED_FORMATS:
        user = _HUNYUAN_STRUCTURED.format(
            format_type=_STRUCTURED_FORMATS[fmt_key],
            target_lang=target_lang,
            text=source_text,
        )
    else:
        user = _HUNYUAN_PLAIN.format(target_lang=target_lang, text=source_text)
    return "", user


def _build_chinese_source_prompt(
    source_locale: str,
    target_locale: str,
    source_text: str,
    locale_names: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """源语=中文时的通用提示词：``将{src_cn}翻译成{tgt_cn}:{text}``。

    对所有非混元 provider（OpenAI / Claude / Gemini / Venus /
    openai_compatible 等）都适用——这些厂商的中文翻译模型对该模板
    理解度很高，且比英文 prompt 短 1/3 token。

    不使用 system role——该简短模板已经包含足够指令，加 system 反而
    会让部分模型在译文前输出"好的"等客套话。
    """
    src_cn = locale_cn(source_locale, locale_names)
    tgt_cn = locale_cn(target_locale, locale_names)
    user = f"将{src_cn}翻译成{tgt_cn}:{source_text}"
    return "", user


def _build_generic_prompt(
    source_locale: str,
    target_locale: str,
    source_text: str,
    context: str,
    locale_names: Optional[Dict[str, str]] = None,
) -> Tuple[str, str]:
    """通用英文 system + user 提示词（OpenAI / Claude 公共版本）。

    仅在**源语不是中文**时使用；源语是中文的场景走
    :func:`_build_chinese_source_prompt` 以获得更紧凑的中文提示。
    """
    src_name = locale_en(source_locale, locale_names) if source_locale else "auto"
    tgt_name = (
        locale_en(target_locale, locale_names) if target_locale else "unspecified"
    )
    parts = [
        f"Source language: {src_name}",
        f"Target language: {tgt_name}",
    ]
    if context:
        parts.append(f"Context: {context}")
    parts.append(f"Text: {source_text}")
    return _GENERIC_SYSTEM, "\n".join(parts)


def build_translation_prompt(
    *,
    provider: str,
    source_locale: str = "",
    target_locale: str = "",
    source_text: str = "",
    context: str = "",
    format_type: str = "plain",
    override_template: str = "",
    locale_names: Optional[Dict[str, str]] = None,
    terms: Optional[Sequence[Tuple[str, str]]] = None,
) -> Tuple[str, str]:
    """根据 provider / 源语种 选择提示词。

    返回 ``(system_prompt, user_prompt)``。``system_prompt`` 为空字符串时
    表示该 provider 的习惯不使用 system role。

    选择策略（按优先级从高到低）：

    1. ``override_template`` 非空 → 直接用模板，占位符 ``{text}`` /
       ``{target_lang}`` / ``{source_lang}``；
    2. provider 为 ``hunyuan_translation`` → 混元官方推荐提示词
       （含术语模式 + 结构化模式）；
    3. 源语是**中文系**（zh / zh-CN / zh-TW ...）→ 中文紧凑提示词
       ``"将{src_cn}翻译成{tgt_cn}:{text}"``；
    4. 兜底 → 通用英文 system+user 提示词。

    参数：
        provider: LLM provider 名称。
        source_locale / target_locale: BCP-47 代码。
        source_text / context: 原文与可选上下文。
        format_type: 结构化翻译格式（混元专用）。
        override_template: 语种 JSON ``strategy_config.prompt_template``
            传入的自定义模板。
        locale_names: ``LanguageProfile.locale_names`` 覆盖字典
            （``{"cn": "...", "en": "..."}``）。
        terms: 术语对列表 ``[(源文, 译文), ...]``；
            混元：切换到术语模式；其它 provider：以 ``Reference terms:``
            形式追加到 user 消息末尾。
    """
    # 1) 显式覆盖模板优先级最高
    if override_template:
        user = override_template.format(
            text=source_text,
            target_lang=locale_cn(target_locale, locale_names),
            source_lang=locale_cn(source_locale, locale_names),
        )
        if terms:
            user = _append_terms_hint(user, terms)
        return "", user

    key = (provider or "").strip().lower()

    # 2) 混元翻译模型使用官方推荐提示词（原生支持术语模式）
    if key in {"hunyuan_translation", "hunyuan-mt", "hy-mt"}:
        return _build_hunyuan_prompt(
            target_locale, source_text, format_type, locale_names, terms=terms,
        )

    # 3) 源语是中文系 → 中文紧凑提示词
    if _is_chinese_source(source_locale):
        system, user = _build_chinese_source_prompt(
            source_locale, target_locale, source_text, locale_names,
        )
        if terms:
            user = _append_terms_hint(user, terms, chinese=True)
        return system, user

    # 4) 兜底：通用英文 system+user 模板（源语非中文：如 Step 2 的 en→vi）
    system, user = _build_generic_prompt(
        source_locale, target_locale, source_text, context, locale_names,
    )
    if terms:
        user = _append_terms_hint(user, terms)
    return system, user


def _append_terms_hint(
    user_prompt: str,
    terms: Sequence[Tuple[str, str]],
    *,
    chinese: bool = False,
) -> str:
    """给非混元 provider 的 user 消息追加术语对参考（通用兜底）。

    参数：
        chinese: 为 True 时使用中文表述（配合
            :func:`_build_chinese_source_prompt`）；默认英文。

    输出形如（英文版本）::

        <原 user_prompt>

        Reference terms (keep these translations consistent):
        - 艾薇塔 → Evita
        - 护盾 → shield
    """
    pairs = [(src, dst) for src, dst in terms if src and dst]
    if not pairs:
        return user_prompt
    if chinese:
        joined = "\n".join(f"- {src} → {dst}" for src, dst in pairs)
        return f"{user_prompt}\n\n参考术语（请保持译文一致）：\n{joined}"
    joined = "\n".join(f"- {src} → {dst}" for src, dst in pairs)
    return (
        f"{user_prompt}\n\n"
        "Reference terms (keep these translations consistent):\n"
        f"{joined}"
    )


__all__ = [
    "LOCALE_CN_NAME",
    "LOCALE_EN_NAME",
    "locale_cn",
    "locale_en",
    "build_translation_prompt",
]
