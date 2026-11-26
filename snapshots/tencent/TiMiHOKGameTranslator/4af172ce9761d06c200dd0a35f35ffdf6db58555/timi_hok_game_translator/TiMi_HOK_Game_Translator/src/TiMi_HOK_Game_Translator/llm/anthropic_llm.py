"""Anthropic Messages 协议 LLM 提供商实现。

启用方式::

    export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=anthropic
    export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=sk-ant-...

默认走 Anthropic 官方 endpoint ``https://api.anthropic.com``。
参考：``docs/模型调用/Anthropic Message 协议字段说明.md``。

性能优化：使用共享 ``requests.Session`` 复用 TCP/TLS 连接，
不强依赖 ``anthropic`` SDK，内网环境可直接使用。
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Sequence, Tuple

from ..commons import LLMProviderMissingError
from ._http import get_session, post_json
from .base import LLMClient, LLMResponse
from .prompts import build_translation_prompt

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-3-5-sonnet-20241022"
_DEFAULT_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicLLM(LLMClient):
    """Claude 系列模型（Anthropic Messages 协议）实现。"""

    provider_name = "anthropic"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._pool_key = f"{self.provider_name}:{(self.api_base or _DEFAULT_BASE).rstrip('/')}"
        self._session = get_session(self._pool_key, pool_maxsize=max(32, self.batch_size))

    # ------------------------------------------------------------------
    def _resolve_endpoint(self) -> str:
        base = (self.api_base or _DEFAULT_BASE).rstrip("/")
        return f"{base}/v1/messages"

    def _headers(self) -> dict:
        if not self.api_key:
            raise LLMProviderMissingError(
                "Anthropic API key is missing. Set GAME_TRANS_TOOLCHAIN__LLM__API_KEY "
                "or the ANTHROPIC_API_KEY environment variable."
            )
        return {
            "anthropic-version": _ANTHROPIC_VERSION,
            "x-api-key": self.api_key,
            # 聚合入口（如 TokenHub）兼容 Bearer，顺带带上不冲突
            "Authorization": f"Bearer {self.api_key}",
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

        payload: dict = {
            "model": model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [{"role": "user", "content": user_prompt}],
        }
        if system_prompt:
            payload["system"] = system_prompt

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._do_request(payload, model)
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover - 网络路径
                last_error = exc
                logger.warning(
                    "AnthropicLLM: attempt %d/%d failed: %s",
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
            url=self._resolve_endpoint(),
            payload=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected response type: {type(data).__name__}")

        # Anthropic 响应：{"content":[{"type":"text","text":"..."}], "usage":{...}}
        text_parts: list = []
        for block in data.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                text_parts.append(block.get("text", ""))
        translated = "".join(text_parts).strip()

        return LLMResponse(
            text=translated,
            provider=self.provider_name,
            model=model,
            usage=data.get("usage", {}) or {},
            raw=data,
        )


__all__ = ["AnthropicLLM"]
