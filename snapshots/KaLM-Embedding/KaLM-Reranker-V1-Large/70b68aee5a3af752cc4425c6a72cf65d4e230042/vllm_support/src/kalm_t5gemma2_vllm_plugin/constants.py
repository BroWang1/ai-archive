from __future__ import annotations

from typing import Iterable


MODEL_ID = "KaLM-Embedding/KaLM-Reranker-V1-Large"
PLUGIN_NAME = "kalm_t5gemma2"
ARCHITECTURE = "T5Gemma2VllmScoreClassification"
TEXT_MODALITY = "text"

DEFAULT_INSTRUCTION = "Given a query, retrieve documents that answer the query."
DEFAULT_SYSTEM_INSTRUCTION = (
    "Judge whether the Document meets the requirements based on the Query and "
    'the Instruct provided. Note that the answer can only be "yes" or "no".'
)

DEFAULT_QUERY_MAX_LENGTH = 512
DEFAULT_DOCUMENT_MAX_LENGTH = 1024
DEFAULT_MAX_MODEL_LEN = 2048
DEFAULT_ENCODER_CHUNK_SIZE = 4
DEFAULT_DECODER_PAD_TO_MULTIPLE_OF = 8
SUPPORTED_ENCODER_CHUNK_SIZES = frozenset({1, 2, 4, 8, 16, 32})

YES_TOKEN_TEXT = "yes"
NO_TOKEN_TEXT = "no"
YES_TOKEN_ID = 4443
NO_TOKEN_ID = 1904

SAMPLE_QUERY = "What is the capital of China?"
SAMPLE_DOCUMENTS = (
    "The capital of China is Beijing.",
    "Gravity attracts bodies toward one another.",
)


def parse_encoder_chunk_size(value: object) -> int:
    if value is None:
        return DEFAULT_ENCODER_CHUNK_SIZE
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "none", "null"}:
            return DEFAULT_ENCODER_CHUNK_SIZE
        try:
            parsed = int(normalized)
        except ValueError as error:
            raise ValueError(_chunk_size_error(value)) from error
    else:
        parsed = int(value)
    if parsed not in SUPPORTED_ENCODER_CHUNK_SIZES:
        raise ValueError(_chunk_size_error(value))
    return parsed


def _chunk_size_error(value: object) -> str:
    return (
        "encoder_chunk_size must be one of "
        f"{sorted(SUPPORTED_ENCODER_CHUNK_SIZES)}; got {value!r}."
    )


def encoder_text(document: str) -> str:
    return f"<Document>: {document}"


def decoder_text(
    tokenizer,
    query: str,
    *,
    instruction: str = DEFAULT_INSTRUCTION,
    system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION,
    query_max_length: int = DEFAULT_QUERY_MAX_LENGTH,
) -> str:
    query_ids = tokenizer(
        query,
        add_special_tokens=False,
        truncation=True,
        max_length=query_max_length,
    )["input_ids"]
    truncated_query = tokenizer.decode(
        query_ids,
        skip_special_tokens=False,
        clean_up_tokenization_spaces=False,
    )
    return (
        "<bos><start_of_turn>user\n"
        f"{system_instruction}\n\n"
        f"<Instruct>: {instruction}\n"
        f"<Query>: {truncated_query}<end_of_turn>\n"
        "<start_of_turn>model\n\n\n\n"
    )


def validate_answer_tokens(tokenizer) -> None:
    expected: Iterable[tuple[str, int]] = (
        (YES_TOKEN_TEXT, YES_TOKEN_ID),
        (NO_TOKEN_TEXT, NO_TOKEN_ID),
    )
    for text, token_id in expected:
        actual = tokenizer.encode(text, add_special_tokens=False)
        if actual != [token_id]:
            raise RuntimeError(
                f"Unexpected tokenization for {text!r}: expected {[token_id]}, "
                f"got {actual}."
            )

