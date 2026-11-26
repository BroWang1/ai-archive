"""TiMi_HOK_Game_Translator.llm 子包。

对外 API::

    from TiMi_HOK_Game_Translator.llm import (
        LLMClient, LLMResponse,
        LocalMockLLM, OpenAILLM, OpenAICompatibleLLM,
        AnthropicLLM, HunyuanTranslationLLM,
        build_translation_prompt,
        create_llm_client, register_llm_provider, registered_llm_providers,
    )
"""

from .anthropic_llm import AnthropicLLM
from .base import LLMClient, LLMResponse
from .factory import create_llm_client, register_llm_provider, registered_llm_providers
from .gemini_llm import GeminiLLM
from .hunyuan_translation_llm import HunyuanTranslationLLM
from .mock_llm import LocalMockLLM
from .openai_llm import OpenAICompatibleLLM, OpenAILLM
from .prompts import build_translation_prompt, locale_cn, locale_en
from .venus_llm import VenusLLM

__all__ = [
    "LLMClient",
    "LLMResponse",
    "LocalMockLLM",
    "OpenAILLM",
    "OpenAICompatibleLLM",
    "AnthropicLLM",
    "GeminiLLM",
    "HunyuanTranslationLLM",
    "VenusLLM",
    "build_translation_prompt",
    "locale_cn",
    "locale_en",
    "create_llm_client",
    "register_llm_provider",
    "registered_llm_providers",
]
