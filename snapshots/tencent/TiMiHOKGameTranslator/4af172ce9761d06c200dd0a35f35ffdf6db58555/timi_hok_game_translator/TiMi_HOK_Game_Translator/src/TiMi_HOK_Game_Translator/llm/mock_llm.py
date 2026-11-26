"""供 demo 与单测使用的确定性回显 LLM（provider: ``echo``）。

不会访问任何外部服务，直接将源文本包上目标语种标记，足以驱动完整工作流。
老配置里的 ``provider: mock`` 由 :mod:`TiMi_HOK_Game_Translator.llm.factory` 自动翻译到
``echo``，向后兼容。
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from .base import LLMClient, LLMResponse


class LocalMockLLM(LLMClient):
    """:class:`LLMClient` 的无网络实现，供本地 demo/测试使用。

    .. note::
        类名保留 ``LocalMockLLM`` 以保持向后兼容；``provider_name`` 已更新为
        ``echo`` 以更准确地反映该后端的"回显原文"行为。
    """

    provider_name = "echo"

    def translate(
        self,
        text: str,
        *,
        source_locale: str = "",
        target_locale: str = "",
        context: str = "",
        terms: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> LLMResponse:
        tag = f"[{target_locale}]" if target_locale else "[echo]"
        translated = f"{tag} {text}" if text else ""
        usage: dict = {"input_chars": len(text), "output_chars": len(translated)}
        if terms:
            # 便于单测断言术语是否被传递到 LLM 层
            usage["terms_count"] = len(terms)
        return LLMResponse(
            text=translated,
            provider=self.provider_name,
            model=self.model or "echo-1",
            usage=usage,
        )

    def batch_translate(
        self,
        texts: Sequence[str],
        *,
        source_locale: str = "",
        target_locale: str = "",
        context: str = "",
        terms: Optional[Sequence[Tuple[str, str]]] = None,
    ) -> List[LLMResponse]:
        # 依然使用默认的逆向批量实现，但将 ``batch_size``
        # 注入到首个响应的 ``usage`` 字典，方便单测取用。
        results = super().batch_translate(
            texts,
            source_locale=source_locale,
            target_locale=target_locale,
            context=context,
            terms=terms,
        )
        if results:
            results[0].usage["batch_size"] = self.batch_size
        return results


__all__ = ["LocalMockLLM"]
