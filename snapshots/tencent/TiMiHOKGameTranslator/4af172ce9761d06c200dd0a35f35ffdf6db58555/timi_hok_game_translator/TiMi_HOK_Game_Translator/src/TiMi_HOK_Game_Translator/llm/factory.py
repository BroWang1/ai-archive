"""LLM 提供商的工厂与注册表。"""

from __future__ import annotations

from typing import Any, Dict, Type

from ..commons import LLMProvider, LLMProviderMissingError
from ..config.schema import LLMConfig
from .anthropic_llm import AnthropicLLM
from .base import LLMClient
from .gemini_llm import GeminiLLM
from .hunyuan_translation_llm import HunyuanTranslationLLM
from .mock_llm import LocalMockLLM
from .openai_llm import OpenAICompatibleLLM, OpenAILLM
from .venus_llm import VenusLLM

_REGISTRY: Dict[str, Type[LLMClient]] = {
    LLMProvider.ECHO.value: LocalMockLLM,
    LLMProvider.OPENAI.value: OpenAILLM,
    LLMProvider.OPENAI_COMPATIBLE.value: OpenAICompatibleLLM,
    LLMProvider.ANTHROPIC.value: AnthropicLLM,
    LLMProvider.GEMINI.value: GeminiLLM,
    LLMProvider.HUNYUAN_TRANSLATION.value: HunyuanTranslationLLM,
    LLMProvider.VENUS.value: VenusLLM,
}

#: 老配置向后兼容：早期版本把"回显式占位 LLM"命名为 ``mock``；
#: 重命名为 ``echo`` 之后，这里把老值翻译回新值，保证既有 ``llm.yaml``
#: 不升级就能继续加载。
_LLM_PROVIDER_ALIASES: Dict[str, str] = {
    "mock": LLMProvider.ECHO.value,
}


def register_llm_provider(name: str, client_cls: Type[LLMClient]) -> None:
    """以 ``name`` 为名注册自定义 :class:`LLMClient` 实现。"""
    _REGISTRY[name.lower()] = client_cls

def registered_llm_providers() -> list:  # noqa: E302
    """返回当前已注册的提供商名称列表（排序后）。"""
    return sorted(_REGISTRY)

def create_llm_client(llm_config: LLMConfig) -> LLMClient:  # noqa: E302
    """根据 ``llm_config`` 构造 :class:`LLMClient` 实例。"""
    key = (llm_config.provider or "").lower()
    key = _LLM_PROVIDER_ALIASES.get(key, key)  # 兼容老的 "mock" → "echo"
    if key not in _REGISTRY:
        raise LLMProviderMissingError(
            f"Unknown llm.provider '{llm_config.provider}'. "
            f"Registered providers: {registered_llm_providers()}"
        )
    cls = _REGISTRY[key]
    extra: Dict[str, Any] = dict(llm_config.extra or {})
    return cls(
        model=llm_config.model,
        temperature=llm_config.temperature,
        max_tokens=llm_config.max_tokens,
        batch_size=llm_config.batch_size,
        api_key=llm_config.api_key,
        api_base=llm_config.api_base,
        timeout_seconds=llm_config.timeout_seconds,
        retries=llm_config.retries,
        retry_interval_seconds=llm_config.retry_interval_seconds,
        extra=extra,
    )

__all__ = ["create_llm_client", "register_llm_provider", "registered_llm_providers"]
