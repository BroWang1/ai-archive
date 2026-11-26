"""Google Gemini LLM 提供商实现。

启用方式::

    export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=gemini
    export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=<Google AI Studio Key>
    # 或：
    export GOOGLE_API_KEY=<Google AI Studio Key>

默认走 Google AI Studio 公网端点::

    https://generativelanguage.googleapis.com/v1beta/models/<model>:generateContent

参考：
    https://ai.google.dev/api/generate-content

Gemini 的 REST 请求体结构与 OpenAI 不同（``contents`` + ``parts``，
system 走 ``systemInstruction``），因此单独实现一个 provider。

性能优化：使用共享 ``requests.Session`` 复用 TCP/TLS 连接；
不强依赖 ``google-generativeai`` SDK，避免 pip 依赖冲突。
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional, Sequence, Tuple

from ..commons import LLMProviderMissingError
from ._http import get_session, post_json
from .base import LLMClient, LLMResponse
from .prompts import build_translation_prompt

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemini-2.5-flash"
_DEFAULT_BASE = "https://generativelanguage.googleapis.com"


class GeminiLLM(LLMClient):
    """Google Gemini（generateContent 协议）实现。

    支持从以下 3 处获取 API Key（按优先级）：

    1. ``llm.yaml`` 的 ``api_key`` 字段（build_bootstrap 后写入 LLMConfig.api_key）；
    2. 环境变量 ``GAME_TRANS_TOOLCHAIN__LLM__API_KEY``；
    3. 环境变量 ``GOOGLE_API_KEY``（Google 官方约定）。

    ``api_base`` 允许覆盖，支持企业内部的 Gemini 代理网关（如 Vertex AI 托管的
    OpenAI 兼容入口不属于本 provider，走 ``openai_compatible`` 即可）。
    """

    provider_name = "gemini"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool_key = f"{self.provider_name}:{(self.api_base or _DEFAULT_BASE).rstrip('/')}"
        self._session = get_session(self._pool_key, pool_maxsize=max(32, self.batch_size))

    # ------------------------------------------------------------------
    def _resolve_key(self) -> str:
        return (
            self.api_key
            or os.getenv("GAME_TRANS_TOOLCHAIN__LLM__API_KEY", "")
            or os.getenv("GOOGLE_API_KEY", "")
        )

    def _resolve_endpoint(self, model: str) -> str:
        base = (self.api_base or _DEFAULT_BASE).rstrip("/")
        # 兼容两种风格：
        #   1) 用户给 "https://.../v1beta"                 → 本函数自动补 /models/<m>:generateContent
        #   2) 用户给 "https://.../v1beta/models"          → 本函数自动补 /<m>:generateContent
        #   3) 用户给完整 "https://.../<m>:generateContent" → 原样使用
        if ":generatecontent" in base.lower():
            return base
        if base.endswith("/models"):
            return f"{base}/{model}:generateContent"
        if "/v1" not in base and "/v2" not in base:
            base = f"{base}/v1beta"
        return f"{base}/models/{model}:generateContent"

    def _headers(self) -> dict:
        key = self._resolve_key()
        if not key:
            raise LLMProviderMissingError(
                "Gemini API key is missing. Set GAME_TRANS_TOOLCHAIN__LLM__API_KEY "
                "or GOOGLE_API_KEY, or fill `api_key` in conf/llm.yaml."
            )
        return {
            # Google 的两种鉴权方式都支持：优先 x-goog-api-key；
            # 走代理网关时部分服务只认 Bearer，一并带上不冲突。
            "x-goog-api-key": key,
            "Authorization": f"Bearer {key}",
        }

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

        # Gemini generateContent 协议：
        #   contents: [{"role": "user", "parts": [{"text": "..."}]}]
        #   systemInstruction: {"parts": [{"text": "..."}]}   # 可选
        payload: dict = {
            "contents": [
                {"role": "user", "parts": [{"text": user_prompt}]},
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
            },
        }
        if system_prompt:
            payload["systemInstruction"] = {"parts": [{"text": system_prompt}]}
        # 透传用户在 extra.generation_config 里的自定义覆盖（topP / topK / stopSequences 等）
        extra_gen = self.extra.get("generation_config")
        if isinstance(extra_gen, dict):
            payload["generationConfig"].update(extra_gen)

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._do_request(payload, model)
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover - 网络路径
                last_error = exc
                logger.warning(
                    "GeminiLLM: attempt %d/%d failed: %s",
                    attempt, self.retries, exc,
                )
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------------
    def _do_request(self, payload: dict, model: str) -> LLMResponse:
        data = post_json(
            session=self._session,
            url=self._resolve_endpoint(model),
            payload=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected Gemini response type: {type(data).__name__}")

        # Gemini 响应：
        #   {"candidates": [{"content": {"parts": [{"text": "..."}], "role": "model"}}],
        #    "usageMetadata": {"promptTokenCount": N, "candidatesTokenCount": M, ...}}
        text_parts: list = []
        for cand in data.get("candidates", []) or []:
            if not isinstance(cand, dict):
                continue
            content = cand.get("content") or {}
            for part in content.get("parts", []) or []:
                if isinstance(part, dict) and "text" in part:
                    text_parts.append(part.get("text", ""))
        translated = "".join(text_parts).strip()

        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            text=translated,
            provider=self.provider_name,
            model=model,
            usage=usage if isinstance(usage, dict) else {},
            raw=data,
        )


__all__ = ["GeminiLLM"]
