# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""SAVEMem pseudo-question embeddings and visual semantic relevance."""

from __future__ import annotations
from collections.abc import Mapping, Sequence
import torch


def embed_pseudo_questions(
    questions: Sequence[str],
    tokenizer: object,
    embedding_layer: torch.nn.Module,
    *,
    exclude_added_special_tokens: bool = False,
) -> torch.Tensor:
    """Tokenize text and return selected LLM input-embedding rows.

    Existing SAVEMem pseudo-question callers retain the historical padding-only
    behavior.  Question-time retrieval can additionally remove tokenizer-added
    control tokens while preserving ordinary text tokens, including unknown
    tokens originating from the question itself.
    """
    if not questions or any(
        (not isinstance(question, str) or not question for question in questions)
    ):
        raise ValueError("pseudo questions must be non-empty strings")
    if not callable(tokenizer):
        raise TypeError("tokenizer must be callable")
    tokenizer_kwargs = {
        "padding": True,
        "return_tensors": "pt",
        "add_special_tokens": True,
    }
    if exclude_added_special_tokens:
        tokenizer_kwargs["return_special_tokens_mask"] = True
    encoded = tokenizer(list(questions), **tokenizer_kwargs)
    if not isinstance(encoded, Mapping):
        raise TypeError("tokenizer output must be a mapping")
    input_ids = encoded.get("input_ids")
    attention_mask = encoded.get("attention_mask")
    if not isinstance(input_ids, torch.Tensor) or not isinstance(
        attention_mask, torch.Tensor
    ):
        raise ValueError(
            "tokenizer output must contain tensor input_ids and attention_mask"
        )
    if input_ids.shape != attention_mask.shape or input_ids.ndim != 2:
        raise ValueError("input_ids and attention_mask must have matching [Q,T] shapes")
    parameter = next(embedding_layer.parameters(), None)
    device = parameter.device if parameter is not None else input_ids.device
    embedded = embedding_layer(input_ids.to(device))
    if embedded.ndim != 3 or embedded.shape[:2] != input_ids.shape:
        raise ValueError("embedding layer must return [Q,T,D]")
    kept = attention_mask.to(dtype=torch.bool)
    if exclude_added_special_tokens:
        special_tokens_mask = encoded.get("special_tokens_mask")
        if not isinstance(special_tokens_mask, torch.Tensor):
            raise ValueError(
                "tokenizer output must contain tensor special_tokens_mask when exclude_added_special_tokens=true"
            )
        if special_tokens_mask.shape != input_ids.shape:
            raise ValueError("special_tokens_mask must match input_ids")
        kept &= ~special_tokens_mask.to(dtype=torch.bool)
        if torch.any(kept.sum(dim=1) == 0):
            raise ValueError(
                "every retrieval question must retain at least one non-special token"
            )
    kept = kept.to(device=device)
    return embedded[kept]
