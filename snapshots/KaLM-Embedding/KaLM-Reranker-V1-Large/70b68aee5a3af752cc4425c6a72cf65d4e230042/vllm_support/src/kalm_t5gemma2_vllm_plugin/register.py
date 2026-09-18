from __future__ import annotations

from vllm import ModelRegistry

from .constants import ARCHITECTURE


def register() -> None:
    ModelRegistry.register_model(
        ARCHITECTURE,
        "kalm_t5gemma2_vllm_plugin.modeling:T5Gemma2VllmScoreClassification",
    )


__all__ = ["register"]
