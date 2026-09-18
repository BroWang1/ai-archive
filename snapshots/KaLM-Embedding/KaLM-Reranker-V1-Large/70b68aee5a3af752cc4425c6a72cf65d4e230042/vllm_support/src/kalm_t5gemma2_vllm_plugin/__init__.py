from __future__ import annotations

from .constants import (
    ARCHITECTURE,
    MODEL_ID,
    PLUGIN_NAME,
    SUPPORTED_ENCODER_CHUNK_SIZES,
    TEXT_MODALITY,
)
from .reranker import KaLMVLLMOfflineReranker, KaLMVLLMReranker

__version__ = "0.1.0"

__all__ = [
    "ARCHITECTURE",
    "KaLMVLLMOfflineReranker",
    "KaLMVLLMReranker",
    "MODEL_ID",
    "PLUGIN_NAME",
    "SUPPORTED_ENCODER_CHUNK_SIZES",
    "TEXT_MODALITY",
    "__version__",
]
