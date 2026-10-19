"""Standalone Hugging Face inference helpers with lazy model imports."""

from typing import Any

__all__ = ["LingV3TTSConfig", "LingV3TTSForConditionalGeneration"]


def __getattr__(name: str) -> Any:
    if name == "LingV3TTSConfig":
        from .configuration_lingv3_tts import LingV3TTSConfig

        return LingV3TTSConfig
    if name == "LingV3TTSForConditionalGeneration":
        from .modeling_lingv3_tts import (
            LingV3TTSForConditionalGeneration,
        )

        return LingV3TTSForConditionalGeneration
    raise AttributeError(name)
