"""LLM 抽象层。

具体提供商实现 :class:`LLMClient`，并在运行时由
:func:`~.factory.create_llm_client` 选择。内置实现包括：

* :class:`~.mock_llm.LocalMockLLM`——零依赖、确定性输出的模拟后端，
  作为默认项保证开箱即用的 demo。
* :class:`~.openai_llm.OpenAILLM` / :class:`~.openai_llm.OpenAICompatibleLLM`
  ——OpenAI 及其兼容厂商（DeepSeek / Kimi / GLM / 混元 Hy4 等）。
* :class:`~.anthropic_llm.AnthropicLLM`——Claude 系列。
* :class:`~.hunyuan_translation_llm.HunyuanTranslationLLM`——混元 Hy-MT2 翻译模型。
* :class:`~.venus_llm.VenusLLM`——腾讯内网 Venus。

更多私有/厂商专用提供商可放在 ``TiMi_HOK_Game_Translator.strategies/`` 子包下，
自行调用 :func:`register_llm_provider` 注册即可。
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple


# ---------------------------------------------------------------------------
# 数据对象
# ---------------------------------------------------------------------------
@dataclass
class LLMResponse:
    """单次翻译请求的结构化响应。"""

    text: str
    provider: str = ""
    model: str = ""
    usage: Dict[str, Any] = field(default_factory=dict)
    raw: Any = None


# ---------------------------------------------------------------------------
# 基类
# ---------------------------------------------------------------------------
class LLMClient(abc.ABC):
    """所有 LLM 提供商需实现的接口。"""

    #: 本提供商在工厂中注册的名称。
    provider_name: str = ""

    def __init__(
        self,
        *,
        model: str = "",
        temperature: float = 0.2,
        max_tokens: int = 1024,
        batch_size: int = 32,
        api_key: str = "",
        api_base: str = "",
        timeout_seconds: int = 30,
        retries: int = 3,
        retry_interval_seconds: int = 30,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.model = model
        self.temperature = float(temperature)
        self.max_tokens = int(max_tokens)
        self.batch_size = max(1, int(batch_size))
        self.api_key = api_key
        self.api_base = api_base
        self.timeout_seconds = int(timeout_seconds)
        self.retries = max(1, int(retries))
        self.retry_interval_seconds = max(0, int(retry_interval_seconds))
        self.extra: Dict[str, Any] = dict(extra or {})

    # ------------------------------------------------------------------
    # 抽象 API
    # ------------------------------------------------------------------
    @abc.abstractmethod
    def translate(
        self,
        text: str,
        *,
        source_locale: str = "",
        target_locale: str = "",
        context: str = "",
        terms: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> LLMResponse:
        """翻译单条 ``text`` 并返回结果。

        参数：
            text: 待翻译文本。
            source_locale: 源语言代码（BCP-47）。
            target_locale: 目标语言代码。
            context: 可选上下文（比如术语、岛语境描述）。
            terms: 术语对列表 ``[(源文, 译文), ...]``；非空时各 provider
                会把术语注入到提示词，详见
                :func:`~.prompts.build_translation_prompt`。
        返回：
            :class:`LLMResponse`。
        """

    # ------------------------------------------------------------------
    # 默认的批量实现
    # ------------------------------------------------------------------
    def batch_translate(
        self,
        texts: Sequence[str],
        *,
        source_locale: str = "",
        target_locale: str = "",
        context: str = "",
        terms: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> List[LLMResponse]:
        """按 :attr:`batch_size` 分段批量翻译。

        默认实现逆向调用 :meth:`translate`；支持原生批量接口的提供商应覆盖以提高效率。
        所有条目共用相同的 ``terms`` 列表；如需按条目独立术语，请走单条 translate。
        """
        results: List[LLMResponse] = []
        for chunk_start in range(0, len(texts), self.batch_size):
            chunk = texts[chunk_start : chunk_start + self.batch_size]
            for text in chunk:
                results.append(
                    self.translate(
                        text,
                        source_locale=source_locale,
                        target_locale=target_locale,
                        context=context,
                        terms=terms,
                    )
                )
        return results


__all__ = ["LLMClient", "LLMResponse"]
