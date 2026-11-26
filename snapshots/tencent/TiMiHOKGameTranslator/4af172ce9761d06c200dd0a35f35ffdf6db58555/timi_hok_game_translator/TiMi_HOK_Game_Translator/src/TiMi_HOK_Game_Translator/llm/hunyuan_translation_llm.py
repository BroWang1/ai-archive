"""混元 HY-MT 内部直连翻译模型 provider。

本模块对接腾讯内网的 **HY-MT 直连 OpenAPI**（非 TokenHub 公有云），
协议是 OpenAI chat.completions 的变体，差异点：

* URL 走 HTTP：
    - 开发/直连机型：``http://<HY-MT_HOST>:<PORT>/v1/chat/completions``
    - 在线集群：``http://stream-server-online-openapi.turbotke.production.polaris:1081/openapi/chat/completions``
* 必须额外带 ``Wsid`` 请求头；
* payload 必须包含 ``query_id``（UUID 字符串），以及
  ``top_p`` / ``top_k`` / ``repetition_penalty`` / ``max_tokens`` /
  ``system_prompt`` / ``stream`` / ``chat_template_kwargs`` 等字段；
* 返回体仍是 OpenAI 风格：``choices[0].message.content``。

启用方式::

    export GAME_TRANS_TOOLCHAIN__LLM__PROVIDER=hunyuan_translation
    export GAME_TRANS_TOOLCHAIN__LLM__API_KEY=<Bearer token>
    # 在 conf/llm.yaml 对应 profile 的 extra 中设置：
    #   wsid: "<YOUR_WSID>"
    #   top_p: 1.0
    #   top_k: -1
    #   repetition_penalty: 1.0
    #   reasoning_effort: "no_think"
    #   system_prompt: ""

关键 ``extra`` 字段（均可选，均有默认）：

* ``wsid``【**强烈建议显式配置**】HY-MT 的 Workspace ID，缺省时为 ``""``；
* ``top_p`` / ``top_k`` / ``repetition_penalty``：解码控制参数；
* ``system_prompt``：顶层 ``system_prompt`` 字段（不走 messages 的 system role）；
* ``reasoning_effort``：注入 ``chat_template_kwargs.reasoning_effort``，
  默认 ``"no_think"`` 走快思考；
* ``chat_template_kwargs``：如需覆盖整个对象，可整体传入；
* ``batch_concurrency``：>=1 时启用内部线程池（默认 0，交给上层 strategy 并发）；
* ``format_type`` / ``prompt_template`` / ``locale_names``：复用通用提示词。
"""

from __future__ import annotations

import concurrent.futures as _futures
import logging
import time
import uuid
from typing import Any, List, Optional, Sequence, Tuple

from ..commons import LLMProviderMissingError
from ..utils.think_leak_detector import detect as _detect_think_leak
from ._http import get_session, post_json
from .base import LLMClient, LLMResponse
from .prompts import build_translation_prompt

logger = logging.getLogger(__name__)

# HY-MT 直连默认接入点（空字符串 → 强制要求在 conf/llm.yaml 显式配置 api_base）
_DEFAULT_BASE = ""
# 默认模型名（HY-MT 内部命名，可在 llm.yaml / 环境变量中覆盖）
_DEFAULT_MODEL = "A3B_MoE_RL_8K_261007_s630_game_wzaa"

# 「思考过程外露」固定允许重试 1 次（命中后额外再请求一次），
# 独立于 self.retries 的网络重试计数，避免相互吞配额。
_THINK_LEAK_MAX_RETRIES = 1


def _normalize_src_lang(source_locale: str) -> str:
    """把 BCP-47 源语种归一化为检测器识别的轴：'zh' 或 'en'。

    检测器只区分「中文源」与「英文源」两条规则轴（见
    ``think_leak_detector._RATIO_LIMIT_EN_PIVOT``）。非 zh 一律按 en 处理，
    这与业务侧「中→多语」「英→多语」双轴的实际使用场景一致。
    """
    code = (source_locale or "").strip().lower()
    if not code:
        return "zh"
    # 兼容 'zh', 'zh-CN', 'zh-Hans', 'zh_cn' 等写法
    if code.startswith("zh"):
        return "zh"
    return "en"


class HunyuanTranslationLLM(LLMClient):
    """HY-MT 内部直连翻译模型实现。

    HTTP 层复用 ``requests.Session`` 连接池；鉴权为 ``Bearer`` + ``Wsid`` 双头。
    """

    provider_name = "hunyuan_translation"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # 内部批量并发数：默认 0 表示串行（由外层 translation.executors.concurrent 并发）
        self._batch_concurrency = int(self.extra.get("batch_concurrency", 0) or 0)
        # 共享连接池 key——同 api_base 的 provider 实例共用连接池
        self._pool_key = f"{self.provider_name}:{(self.api_base or _DEFAULT_BASE).rstrip('/')}"
        self._session = get_session(self._pool_key, pool_maxsize=max(32, self.batch_size))

        # HY-MT 必备头：Workspace ID
        self._wsid = str(self.extra.get("wsid", "") or "")

        # 解码控制参数（HY-MT 直连 payload 必填/推荐字段）
        self._top_p = float(self.extra.get("top_p", 1.0))
        self._top_k = int(self.extra.get("top_k", -1))
        self._repetition_penalty = float(self.extra.get("repetition_penalty", 1.0))
        self._system_prompt = str(self.extra.get("system_prompt", "") or "")
        self._stream = bool(self.extra.get("stream", False))

        # chat_template_kwargs 可整体覆盖，也可只配 reasoning_effort
        raw_tpl_kwargs = self.extra.get("chat_template_kwargs")
        if isinstance(raw_tpl_kwargs, dict) and raw_tpl_kwargs:
            self._chat_template_kwargs: dict = dict(raw_tpl_kwargs)
        else:
            self._chat_template_kwargs = {
                "reasoning_effort": str(
                    self.extra.get("reasoning_effort", "no_think") or "no_think"
                ),
            }

    # ------------------------------------------------------------------
    def _endpoint(self) -> str:
        """构造 chat/completions 完整 URL。

        兼容两种 api_base 写法：
        * ``http://host:port`` —— 自动补 ``/v1/chat/completions``；
        * ``http://host:port/v1`` —— 补 ``/chat/completions``；
        * ``http://host.../openapi`` —— 补 ``/chat/completions``；
        * 已带 ``/chat/completions`` 的完整 URL —— 原样使用。
        """
        base = (self.api_base or _DEFAULT_BASE).strip().rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1") or base.endswith("/openapi"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _headers(self) -> dict:
        if not self.api_key:
            raise LLMProviderMissingError(
                "HY-MT API key is missing. Set GAME_TRANS_TOOLCHAIN__LLM__API_KEY "
                "to your HY-MT Bearer token."
            )
        headers: dict = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        if self._wsid:
            headers["Wsid"] = self._wsid
        return headers

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
        _, user_prompt = build_translation_prompt(
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

        # HY-MT 直连 payload：严格按参考脚本字段构造
        payload: dict = {
            "model": model,
            "query_id": f"TiMi_HOK_Game_Translator_{uuid.uuid4()}",
            "messages": [{"role": "user", "content": user_prompt}],
            "temperature": self.temperature,
            "top_p": self._top_p,
            "top_k": self._top_k,
            "repetition_penalty": self._repetition_penalty,
            "max_tokens": self.max_tokens,
            "system_prompt": self._system_prompt,
            "stream": self._stream,
            "chat_template_kwargs": dict(self._chat_template_kwargs),
        }

        last_error: Optional[Exception] = None
        # 「思考过程外露」允许的额外请求次数（独立计数，用完即接受当前译文）。
        # 外露重试与网络失败重试共享 self.retries 的循环额度（默认 3 轮），
        # 对 ~0.02% 的实测触发率来说完全够用。
        leak_retries_left = _THINK_LEAK_MAX_RETRIES
        for attempt in range(1, self.retries + 1):
            try:
                response = self._do_request(payload, model)
            except Exception as exc:  # pylint: disable=broad-except  # pragma: no cover - 网络路径
                last_error = exc
                logger.warning(
                    "HunyuanTranslationLLM(HY-MT): attempt %d/%d failed: %s",
                    attempt, self.retries, exc,
                )
                if attempt < self.retries:
                    time.sleep(self.retry_interval_seconds)
                continue

            # 成功拿到响应——做「思考过程外露」自检。
            # 命中：丢弃本次结果并再请求一次（最多 _THINK_LEAK_MAX_RETRIES 次），
            # 并刷新 query_id 避免被服务端缓存同样答案。
            leak = _detect_think_leak(
                response.text,
                source_text=text,
                target_lang=target_locale or None,
                src_lang=_normalize_src_lang(source_locale),
            )
            if leak.leaked:
                logger.warning(
                    "HunyuanTranslationLLM(HY-MT): think-leak detected, "
                    "retries_left=%d, %s",
                    leak_retries_left, leak.describe(),
                )
                if leak_retries_left > 0:
                    leak_retries_left -= 1
                    # 刷新 query_id，让下游不要命中可能的缓存
                    payload["query_id"] = f"TiMi_HOK_Game_Translator_{uuid.uuid4()}"
                    if attempt < self.retries:
                        continue
                # 外露重试额度耗尽或循环本身已到最后一轮：
                # 退而求其次接受当前译文，交由后续人工兜底
                logger.warning(
                    "HunyuanTranslationLLM(HY-MT): think-leak retry budget "
                    "exhausted, accepting latest translation (len=%d).",
                    len(response.text),
                )
                return response

            return response
        assert last_error is not None
        raise last_error

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
        """批量翻译。

        * ``extra.batch_concurrency = 0``（默认）——保持串行，交由外层
          ``translation.executors.concurrent`` 做条目级并发；
        * ``extra.batch_concurrency >= 1``——在本类内启用线程池并发，
          适合不走 strategy 层的脚本/独立调用场景。
        """
        workers = self._batch_concurrency
        if workers < 1 or len(texts) <= 1:
            return super().batch_translate(
                texts,
                source_locale=source_locale,
                target_locale=target_locale,
                context=context,
                terms=terms,
            )

        workers = min(workers, len(texts))
        results: List[Optional[LLMResponse]] = [None] * len(texts)

        def _one(idx: int, text: str) -> None:
            results[idx] = self.translate(
                text,
                source_locale=source_locale,
                target_locale=target_locale,
                context=context,
                terms=terms,
            )

        with _futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_one, i, t) for i, t in enumerate(texts)]
            for fut in _futures.as_completed(futures):
                fut.result()  # 让异常冒泡

        return [r for r in results if r is not None]

    # ------------------------------------------------------------------
    def _do_request(self, payload: dict, model: str) -> LLMResponse:
        data = post_json(
            session=self._session,
            url=self._endpoint(),
            payload=payload,
            headers=self._headers(),
            timeout=self.timeout_seconds,
        )
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected response type: {type(data).__name__}")

        choices = data.get("choices") or []
        translated = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            translated = (message.get("content") or "").strip()

        return LLMResponse(
            text=translated,
            provider=self.provider_name,
            model=model,
            usage=data.get("usage", {}) or {},
            raw=data,
        )


__all__ = ["HunyuanTranslationLLM"]
