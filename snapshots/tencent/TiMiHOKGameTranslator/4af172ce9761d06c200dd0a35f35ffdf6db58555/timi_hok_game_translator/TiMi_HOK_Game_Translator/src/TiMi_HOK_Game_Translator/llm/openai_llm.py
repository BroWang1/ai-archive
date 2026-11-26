"""OpenAI 及其兼容厂商的 LLM 提供商实现。

启用方式::

    pip install "TiMi_HOK_Game_Translator[openai]"
    export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=openai
    export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=sk-...

该实现同时适配所有 **OpenAI chat.completions 兼容** 的厂商（混元 Hy4 系列、
DeepSeek、Kimi、GLM、通义千问 OpenAI 兼容模式、Xiaomi MiMo、MiniMax 兼容版
等）。只需在 ``conf/llm.yaml`` 的 profile 中覆盖 ``api_base`` 与 ``model``：

* OpenAI 官方：``https://api.openai.com/v1``
* DeepSeek：``https://api.deepseek.com/v1``
* Kimi/Moonshot：``https://api.moonshot.cn/v1``
* GLM：``https://open.bigmodel.cn/api/paas/v4``
* 通义千问兼容模式：``https://dashscope.aliyuncs.com/compatible-mode/v1``
* 混元 Hy4：``https://api.hunyuan.cloud.tencent.com/v1``

提示词由 :mod:`.prompts` 统一生成，不在本模块硬编码。
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional, Sequence, Tuple

from ..commons import LLMProviderMissingError
from .base import LLMClient, LLMResponse
from .prompts import build_translation_prompt

_DEFAULT_MODEL = "gpt-4o-mini"


class OpenAILLM(LLMClient):
    """OpenAI 及其兼容厂商的 chat.completions 实现。

    通过 ``extra.prompt_template`` 可按语种覆盖提示词；
    通过 ``extra.format_type`` 可声明原文格式（如 ``dtxml``）以启用结构化模板。
    """

    provider_name = "openai"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client: Optional[Any] = None

    # ------------------------------------------------------------------
    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as exc:  # pragma: no cover — 可选依赖
            raise LLMProviderMissingError(
                "The 'openai' provider requires the 'openai' package. "
                "Install with: pip install 'TiMi_HOK_Game_Translator[openai]'."
            ) from exc

        api_key = self.api_key or os.getenv("OPENAI_API_KEY", "")
        if not api_key:
            raise LLMProviderMissingError(
                "OpenAI API key is missing. Set GAME_TRANS_TOOLCHAIN__LLM__API_KEY "
                "or the OPENAI_API_KEY environment variable."
            )
        kwargs: dict = {"api_key": api_key, "timeout": self.timeout_seconds}
        if self.api_base:
            kwargs["base_url"] = self.api_base
        self._client = OpenAI(**kwargs)
        return self._client

    # ------------------------------------------------------------------
    def translate(
        self,
        text: str,
        *,
        source_locale: str = "",
        target_locale: str = "",
        context: str = "",
        terms: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> LLMResponse:
        client = self._get_client()
        model = self.model or _DEFAULT_MODEL

        system_prompt, user_prompt = build_translation_prompt(
            provider=self.provider_name,
            source_locale=source_locale,
            target_locale=target_locale,
            source_text=text,
            context=context,
            format_type=str(self.extra.get("format_type", "plain")),
            override_template=str(self.extra.get("prompt_template", "")),
            locale_names=self.extra.get("locale_names") or None,
            terms=terms,
        )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
                choice = response.choices[0]
                translated = (choice.message.content or "").strip()
                return LLMResponse(
                    text=translated,
                    provider=self.provider_name,
                    model=model,
                    usage=getattr(response, "usage", None).__dict__
                    if getattr(response, "usage", None)
                    else {},
                    raw=response,
                )
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover - 网络路径
                last_error = exc
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise last_error


class OpenAICompatibleLLM(OpenAILLM):
    """OpenAI 兼容厂商的别名类（DeepSeek/Kimi/GLM/Qwen 兼容模式/Hy4 等）。

    与 :class:`OpenAILLM` 行为完全一致，仅通过 ``provider_name`` 区分日志。
    """

    provider_name = "openai_compatible"


__all__ = ["OpenAILLM", "OpenAICompatibleLLM"]
