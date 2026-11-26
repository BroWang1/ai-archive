"""Venus 内网 LLM 提供商实现。

Venus 是腾讯内部的大模型服务平台，承载 llama3-70B / llama3.1-70B /
Qwen 等翻译模型。本模块基于 ``venus_api_base.http_client.HttpClient``
按 :class:`LLMClient` 协议封装到框架内。

关键配置（放在 ``conf/llm.yaml`` 对应 profile 的 ``extra`` 下）：

* ``server_id`` 【必填】Venus 服务 ID（旧 ``MODEL_SERVER_IDS``）；
* ``app_group_id``【必填】Venus 应用组 ID；
* ``secret_id`` / ``secret_key`` 两种填法（任选其一即可）：
    1. profile 的 ``api_key`` 以 ``<secret_id>:<secret_key>`` 格式填写；
    2. 分别放在 ``extra.secret_id`` / ``extra.secret_key``；
* ``model_params`` 可选，直接透传到请求体（如
  ``{"temperature": 0.1, "top_p": 0.1, "repetition_penalty": 1.1,
     "do_sample": false, ...}``）。

启用方式::

    export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=venus
    export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=<secret_id>:<secret_key>
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional, Sequence, Tuple

from ..commons import LLMProviderMissingError
from .base import LLMClient, LLMResponse
from .prompts import build_translation_prompt

logger = logging.getLogger(__name__)

_DEFAULT_API_BASE = "http://v2.open.venus.oa.com/chat/single"


class VenusLLM(LLMClient):
    """Venus 内网大模型 provider。

    依赖 ``venus_api_base`` 包（内网安装）；缺省时在首次调用时抛出清晰错误。
    """

    provider_name = "venus"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client: Optional[Any] = None

        # 解析鉴权凭据：优先 extra.secret_id/secret_key，然后 api_key 冒号分隔
        self._secret_id = str(self.extra.get("secret_id", "") or "")
        self._secret_key = str(self.extra.get("secret_key", "") or "")
        if (not self._secret_id or not self._secret_key) and self.api_key:
            parts = self.api_key.split(":", 1)
            if len(parts) == 2:
                self._secret_id = self._secret_id or parts[0].strip()
                self._secret_key = self._secret_key or parts[1].strip()
            else:
                # 旧 model_service 中 secret 直接硬编码两段，这里兼容"只传 secret_key"场景
                self._secret_key = self._secret_key or self.api_key

        # 必填：server_id / app_group_id
        self._server_id = int(self.extra.get("server_id") or 0)
        self._app_group_id = int(
            self.extra.get("app_group_id")
            or self.extra.get("venus_app_group_id")
            or 0
        )
        # 可选的请求体扩展参数（透传到 Venus，复用旧 model_service 的 model_params）
        self._model_params = dict(self.extra.get("model_params") or {})

    # ------------------------------------------------------------------
    def _get_http_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from venus_api_base.config import Config  # type: ignore
            from venus_api_base.http_client import HttpClient  # type: ignore
        except ImportError as exc:  # pragma: no cover — 内网可选依赖
            raise LLMProviderMissingError(
                "The 'venus' provider requires 'venus_api_base'. "
                "Install the internal package from your corporate mirror."
            ) from exc

        if not self._secret_id or not self._secret_key:
            raise LLMProviderMissingError(
                "Venus credentials missing. Provide extra.secret_id + "
                "extra.secret_key, or set api_key='<secret_id>:<secret_key>'."
            )

        self._client = HttpClient(
            config=Config(read_timeout=self.timeout_seconds),
            secret_id=self._secret_id,
            secret_key=self._secret_key,
        )
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
        if not self._server_id or not self._app_group_id:
            raise LLMProviderMissingError(
                "Venus profile missing extra.server_id / extra.app_group_id."
            )

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

        body = self._build_payload(system_prompt, user_prompt)
        endpoint = (self.api_base or _DEFAULT_API_BASE).strip()

        last_error: Optional[Exception] = None
        for attempt in range(1, self.retries + 1):
            try:
                return self._do_request(endpoint, body)
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover — 网络路径
                last_error = exc
                logger.warning(
                    "VenusLLM: attempt %d/%d failed: %s",
                    attempt, self.retries, exc,
                )
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
        assert last_error is not None
        raise last_error

    # ------------------------------------------------------------------
    def _build_payload(self, system_prompt: str, user_prompt: str) -> dict:
        """构造 Venus 请求体，参数命名与旧 model_service 保持一致。"""
        messages: list = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload: dict = {
            "appGroupId": self._app_group_id,
            "serverId": self._server_id,
            "messages": messages,
            "temperature": self.temperature,
        }
        # 透传可选的调优参数（do_sample / top_p / top_k / repetition_penalty 等）
        for k, v in self._model_params.items():
            # 不覆盖已显式传入的核心字段
            payload.setdefault(k, v)
        return payload

    def _do_request(self, endpoint: str, body: dict) -> LLMResponse:
        import json as _json

        client = self._get_http_client()
        header = {"Content-Type": "application/json"}
        resp = client.post(endpoint, header=header, body=_json.dumps(body))

        content, usage = _extract_venus_content(resp)
        if not content:
            logger.warning("VenusLLM: empty content in response: %r", resp)

        return LLMResponse(
            text=content.strip(),
            provider=self.provider_name,
            model=self.model or f"venus-{self._server_id}",
            usage=usage,
            raw=resp,
        )


def _extract_venus_content(resp: Any) -> Tuple[str, dict]:
    """从 Venus 响应中提取翻译文本与 usage。

    Venus 返回结构常见三种，按优先级依次尝试：

    1) 当前内网主路径：``{"data": {"response": "..."}}``——
       ``v2.open.venus.oa.com/chat/single`` 实测返回此字段；
    2) OpenAI 风格：``{"data": {"choices": [{"message": {"content": ...}}]}}``；
    3) 旧封装：``{"data": {"generated_text": "..."}}`` /
       ``{"data": {"output": "..."}}`` 等。
    """
    if not isinstance(resp, dict):
        return "", {}
    data = resp.get("data") if "data" in resp else resp
    if not isinstance(data, dict):
        return "", {}

    # 优先 OpenAI 风格
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        message = choices[0].get("message") or {}
        if isinstance(message, dict):
            text = message.get("content") or ""
            if text:
                return str(text), dict(data.get("usage") or {})

    # 兼容多种返回字段（新/旧封装）；"response" 是 Venus 当前
    # /chat/single 接口的实际字段名——放首位，命中率最高。
    for key in ("response", "generated_text", "output", "content", "result"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value, dict(data.get("usage") or {})

    return "", dict(data.get("usage") or {})


__all__ = ["VenusLLM"]
