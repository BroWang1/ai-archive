from __future__ import annotations

import importlib.metadata
import math
import os
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from .constants import (
    ARCHITECTURE,
    DEFAULT_DECODER_PAD_TO_MULTIPLE_OF,
    DEFAULT_DOCUMENT_MAX_LENGTH,
    DEFAULT_ENCODER_CHUNK_SIZE,
    DEFAULT_INSTRUCTION,
    DEFAULT_MAX_MODEL_LEN,
    DEFAULT_QUERY_MAX_LENGTH,
    DEFAULT_SYSTEM_INSTRUCTION,
    MODEL_ID,
    NO_TOKEN_ID,
    PLUGIN_NAME,
    SUPPORTED_ENCODER_CHUNK_SIZES,
    TEXT_MODALITY,
    YES_TOKEN_ID,
    decoder_text,
    encoder_text,
    parse_encoder_chunk_size,
    validate_answer_tokens,
)


TESTED_VLLM_VERSION = "0.19.1"


def _positive_int(value: int, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return parsed


def _sigmoid(value: float) -> float:
    if value >= 0:
        scale = math.exp(-value)
        return 1.0 / (1.0 + scale)
    scale = math.exp(value)
    return scale / (1.0 + scale)


def build_hf_overrides(encoder_chunk_size: int) -> dict[str, object]:
    return {
        "architectures": [ARCHITECTURE],
        "num_labels": 1,
        "yes_token_id": YES_TOKEN_ID,
        "no_token_id": NO_TOKEN_ID,
        "encoder_chunk_size": encoder_chunk_size,
        "decoder_pad_to_multiple_of": DEFAULT_DECODER_PAD_TO_MULTIPLE_OF,
        "problem_type": "regression",
    }


def _enable_plugin() -> None:
    allowed = os.environ.get("VLLM_PLUGINS")
    if allowed is None:
        os.environ["VLLM_PLUGINS"] = PLUGIN_NAME
        return
    names = {item.strip() for item in allowed.split(",") if item.strip()}
    if PLUGIN_NAME not in names:
        raise RuntimeError(
            f"VLLM_PLUGINS={allowed!r} excludes {PLUGIN_NAME!r}. Add the plugin "
            "name or unset VLLM_PLUGINS."
        )


def check_runtime() -> None:
    installed_vllm = importlib.metadata.version("vllm")
    if installed_vllm != TESTED_VLLM_VERSION:
        raise RuntimeError(
            f"This adapter requires vLLM {TESTED_VLLM_VERSION}; "
            f"found {installed_vllm}."
        )

    discovered = {
        entry.name: entry.value
        for entry in importlib.metadata.entry_points(group="vllm.general_plugins")
    }
    if PLUGIN_NAME not in discovered:
        raise RuntimeError(
            f"vLLM plugin {PLUGIN_NAME!r} is not installed. Install the "
            "vllm_support package before creating the reranker."
        )

    from vllm.model_executor.models import ModelRegistry
    from vllm.plugins import load_general_plugins

    load_general_plugins()
    if ARCHITECTURE not in set(ModelRegistry.get_supported_archs()):
        raise RuntimeError(f"{ARCHITECTURE} was not registered in ModelRegistry.")


class KaLMVLLMReranker:
    """Single-GPU vLLM adapter preserving the original KaLM score contract."""

    def __init__(
        self,
        model: str | Path = MODEL_ID,
        *,
        query_max_length: int = DEFAULT_QUERY_MAX_LENGTH,
        document_max_length: int = DEFAULT_DOCUMENT_MAX_LENGTH,
        encoder_chunk_size: object = DEFAULT_ENCODER_CHUNK_SIZE,
        dtype: str = "bfloat16",
        tensor_parallel_size: int = 1,
        max_model_len: int = DEFAULT_MAX_MODEL_LEN,
        gpu_memory_utilization: float = 0.85,
        batch_size: int = 32,
        instruction: str = DEFAULT_INSTRUCTION,
        system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION,
        skip_runtime_check: bool = False,
    ) -> None:
        self.model = str(model)
        self.query_max_length = _positive_int(
            query_max_length, "query_max_length"
        )
        self.document_max_length = _positive_int(
            document_max_length, "document_max_length"
        )
        self.encoder_chunk_size = parse_encoder_chunk_size(encoder_chunk_size)
        self.dtype = str(dtype)
        self.tensor_parallel_size = _positive_int(
            tensor_parallel_size, "tensor_parallel_size"
        )
        if self.tensor_parallel_size != 1:
            raise ValueError(
                "The published adapter supports tensor_parallel_size=1 only."
            )
        self.max_model_len = _positive_int(max_model_len, "max_model_len")
        self.gpu_memory_utilization = float(gpu_memory_utilization)
        if not 0 < self.gpu_memory_utilization <= 1:
            raise ValueError("gpu_memory_utilization must be in the interval (0, 1].")
        self.batch_size = _positive_int(batch_size, "batch_size")
        if not isinstance(instruction, str) or not isinstance(
            system_instruction, str
        ):
            raise TypeError("instruction and system_instruction must be strings.")
        self.instruction = instruction
        self.system_instruction = system_instruction

        _enable_plugin()
        if not skip_runtime_check:
            check_runtime()

        from transformers import AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model,
            trust_remote_code=True,
        )
        validate_answer_tokens(self.tokenizer)

        from vllm import LLM
        from vllm.pooling_params import PoolingParams

        self.pooling_params = PoolingParams(use_activation=False)
        self.llm = LLM(
            model=self.model,
            runner="pooling",
            trust_remote_code=True,
            hf_overrides=build_hf_overrides(self.encoder_chunk_size),
            dtype=self.dtype,
            tensor_parallel_size=1,
            max_model_len=self.max_model_len,
            gpu_memory_utilization=self.gpu_memory_utilization,
            enforce_eager=True,
            limit_mm_per_prompt={TEXT_MODALITY: 1},
        )

    def close(self) -> None:
        llm = getattr(self, "llm", None)
        if llm is None:
            return
        engine = getattr(llm, "llm_engine", None)
        engine_core = getattr(engine, "engine_core", None)
        shutdown = getattr(engine_core, "shutdown", None)
        if callable(shutdown):
            shutdown()
        self.llm = None

    def __enter__(self) -> "KaLMVLLMReranker":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def _encoder_ids(self, document: str) -> tuple[str, list[int]]:
        text = encoder_text(document)
        token_ids = self.tokenizer(
            text,
            add_special_tokens=False,
            truncation=True,
            max_length=self.document_max_length,
        )["input_ids"]
        if not token_ids:
            raise ValueError("Encoded document prompt is empty.")
        return text, list(token_ids)

    def _decoder_ids(self, query: str, instruction: str) -> tuple[str, list[int]]:
        text = decoder_text(
            self.tokenizer,
            query,
            instruction=instruction,
            system_instruction=self.system_instruction,
            query_max_length=self.query_max_length,
        )
        token_ids = self.tokenizer.encode(text, add_special_tokens=False)
        if not token_ids:
            raise ValueError("Encoded decoder prompt is empty.")
        return text, list(token_ids)

    def _prompt(self, query: str, document: str, instruction: str):
        from vllm.inputs import ExplicitEncoderDecoderPrompt, TokensPrompt

        encoder_prompt, encoder_ids = self._encoder_ids(document)
        decoder_prompt, decoder_ids = self._decoder_ids(query, instruction)
        return ExplicitEncoderDecoderPrompt(
            encoder_prompt=TokensPrompt(
                prompt_token_ids=encoder_ids,
                prompt=encoder_prompt,
                multi_modal_data={TEXT_MODALITY: [encoder_prompt]},
            ),
            decoder_prompt=TokensPrompt(
                prompt_token_ids=decoder_ids,
                prompt=decoder_prompt,
            ),
        )

    @staticmethod
    def _validate_pairs(
        pairs: Sequence[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        if isinstance(pairs, (str, bytes)) or not isinstance(pairs, Sequence):
            raise TypeError("pairs must be a sequence of (query, document) pairs.")
        validated: list[tuple[str, str]] = []
        for index, pair in enumerate(pairs):
            if (
                isinstance(pair, (str, bytes))
                or not isinstance(pair, Sequence)
                or len(pair) != 2
            ):
                raise ValueError(f"pairs[{index}] must contain exactly two strings.")
            query, document = pair
            if not isinstance(query, str) or not isinstance(document, str):
                raise TypeError(f"pairs[{index}] must contain exactly two strings.")
            validated.append((query, document))
        return validated

    @staticmethod
    def _margins_from_outputs(outputs: Iterable[Any]) -> list[float]:
        margins: list[float] = []
        for output in outputs:
            values = output.outputs.probs
            if len(values) != 1:
                raise RuntimeError(f"Expected one raw margin, got {values}.")
            margin = float(values[0])
            if not math.isfinite(margin):
                raise RuntimeError(f"vLLM returned a non-finite margin: {margin}.")
            margins.append(margin)
        return margins

    def predict(
        self,
        pairs: Sequence[tuple[str, str]],
        *,
        instruction: Optional[str] = None,
        return_margin: bool = False,
    ) -> list[float] | list[dict[str, float]]:
        validated_pairs = self._validate_pairs(pairs)
        if not validated_pairs:
            return []
        effective_instruction = self.instruction if instruction is None else instruction
        if not isinstance(effective_instruction, str):
            raise TypeError("instruction must be a string or None.")

        margins: list[float] = []
        for start in range(0, len(validated_pairs), self.batch_size):
            batch = validated_pairs[start : start + self.batch_size]
            prompts = [
                self._prompt(query, document, effective_instruction)
                for query, document in batch
            ]
            if self.llm is None:
                raise RuntimeError("The reranker has been closed.")
            outputs = self.llm.classify(
                prompts,
                pooling_params=self.pooling_params,
                use_tqdm=False,
            )
            margins.extend(self._margins_from_outputs(outputs))

        scores = [_sigmoid(margin) for margin in margins]
        if return_margin:
            return [
                {"score": score, "margin": margin}
                for score, margin in zip(scores, margins)
            ]
        return scores

    def rank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        instruction: Optional[str] = None,
        top_k: Optional[int] = None,
        return_margin: bool = False,
    ) -> list[dict[str, float | int]]:
        if not isinstance(query, str):
            raise TypeError("query must be a string.")
        if isinstance(documents, (str, bytes)) or not isinstance(documents, Sequence):
            raise TypeError("documents must be a sequence of strings.")
        if any(not isinstance(document, str) for document in documents):
            raise TypeError("every document must be a string.")
        if top_k is not None:
            top_k = int(top_k)
            if top_k < 0:
                raise ValueError("top_k must be non-negative or None.")

        predictions = self.predict(
            [(query, document) for document in documents],
            instruction=instruction,
            return_margin=return_margin,
        )
        rankings: list[dict[str, float | int]] = []
        for corpus_id, prediction in enumerate(predictions):
            if return_margin:
                assert isinstance(prediction, dict)
                item: dict[str, float | int] = {
                    "corpus_id": corpus_id,
                    "score": prediction["score"],
                    "margin": prediction["margin"],
                }
            else:
                assert isinstance(prediction, float)
                item = {"corpus_id": corpus_id, "score": prediction}
            rankings.append(item)
        rankings.sort(key=lambda item: float(item["score"]), reverse=True)
        return rankings if top_k is None else rankings[:top_k]


KaLMVLLMOfflineReranker = KaLMVLLMReranker

__all__ = [
    "KaLMVLLMOfflineReranker",
    "KaLMVLLMReranker",
    "SUPPORTED_ENCODER_CHUNK_SIZES",
    "build_hf_overrides",
    "check_runtime",
    "parse_encoder_chunk_size",
]
