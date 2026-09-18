from __future__ import annotations

import argparse
import json
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Iterable, TextIO

from .constants import (
    DEFAULT_DOCUMENT_MAX_LENGTH,
    DEFAULT_ENCODER_CHUNK_SIZE,
    DEFAULT_MAX_MODEL_LEN,
    DEFAULT_QUERY_MAX_LENGTH,
    MODEL_ID,
    SAMPLE_DOCUMENTS,
    SAMPLE_QUERY,
    SUPPORTED_ENCODER_CHUNK_SIZES,
    parse_encoder_chunk_size,
)
from .reranker import KaLMVLLMReranker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline KaLM-Reranker-V1-Nano scoring with vLLM 0.19.1.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--input-jsonl", type=Path)
    parser.add_argument("--output-jsonl", type=Path)
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--query-max-length", type=int, default=DEFAULT_QUERY_MAX_LENGTH)
    parser.add_argument(
        "--document-max-length", type=int, default=DEFAULT_DOCUMENT_MAX_LENGTH
    )
    parser.add_argument(
        "--encoder-chunk-size",
        default=str(DEFAULT_ENCODER_CHUNK_SIZE),
        help=f"One of {sorted(SUPPORTED_ENCODER_CHUNK_SIZES)}.",
    )
    parser.add_argument("--max-model-len", type=int, default=DEFAULT_MAX_MODEL_LEN)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--return-margin", action="store_true")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    return parser


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}:{line_no}: invalid JSON.") from error
            if not isinstance(row, dict):
                raise ValueError(f"{path}:{line_no}: expected a JSON object.")
            if not isinstance(row.get("query"), str):
                raise ValueError(f"{path}:{line_no}: 'query' must be a string.")
            if not isinstance(row.get("document"), str):
                raise ValueError(f"{path}:{line_no}: 'document' must be a string.")
            if "instruction" in row and not isinstance(row["instruction"], str):
                raise ValueError(f"{path}:{line_no}: 'instruction' must be a string.")
            rows.append(row)
    return rows


def _write_jsonl(rows: Iterable[dict[str, Any]], output: TextIO) -> None:
    for row in rows:
        output.write(json.dumps(row, ensure_ascii=False) + "\n")
    output.flush()


def _score_rows(
    reranker: KaLMVLLMReranker,
    rows: list[dict[str, Any]],
    *,
    return_margin: bool,
    top_k: int | None,
) -> list[dict[str, Any]]:
    grouped: OrderedDict[str | None, list[tuple[int, dict[str, Any]]]] = OrderedDict()
    for index, row in enumerate(rows):
        grouped.setdefault(row.get("instruction"), []).append((index, row))

    scored: dict[int, dict[str, Any]] = {}
    for instruction, items in grouped.items():
        predictions = reranker.predict(
            [(row["query"], row["document"]) for _, row in items],
            instruction=instruction,
            return_margin=True,
        )
        for (index, row), prediction in zip(items, predictions):
            assert isinstance(prediction, dict)
            result = {
                "id": row.get("id", index),
                "query": row["query"],
                "document": row["document"],
                "score": prediction["score"],
            }
            if "instruction" in row:
                result["instruction"] = row["instruction"]
            if return_margin:
                result["margin"] = prediction["margin"]
            scored[index] = result

    ordered = [scored[index] for index in range(len(rows))]
    if top_k is None:
        return ordered
    if top_k < 0:
        raise ValueError("--top-k must be non-negative.")
    by_query: OrderedDict[str, list[dict[str, Any]]] = OrderedDict()
    for row in ordered:
        by_query.setdefault(str(row["query"]), []).append(row)
    output: list[dict[str, Any]] = []
    for group in by_query.values():
        group.sort(key=lambda item: float(item["score"]), reverse=True)
        output.extend(group[:top_k])
    return output


def main() -> int:
    args = build_parser().parse_args()
    with KaLMVLLMReranker(
        args.model,
        query_max_length=args.query_max_length,
        document_max_length=args.document_max_length,
        encoder_chunk_size=parse_encoder_chunk_size(args.encoder_chunk_size),
        max_model_len=args.max_model_len,
        batch_size=args.batch_size,
        dtype=args.dtype,
        gpu_memory_utilization=args.gpu_memory_utilization,
        tensor_parallel_size=args.tensor_parallel_size,
    ) as reranker:
        if args.input_jsonl is None:
            rankings = reranker.rank(
                SAMPLE_QUERY,
                SAMPLE_DOCUMENTS,
                top_k=args.top_k,
                return_margin=args.return_margin,
            )
            rows = [
                {
                    "query": SAMPLE_QUERY,
                    "document": SAMPLE_DOCUMENTS[int(item["corpus_id"])],
                    **item,
                }
                for item in rankings
            ]
        else:
            rows = _score_rows(
                reranker,
                _read_jsonl(args.input_jsonl),
                return_margin=args.return_margin,
                top_k=args.top_k,
            )

    if args.output_jsonl is None:
        _write_jsonl(rows, sys.stdout)
    else:
        args.output_jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.output_jsonl.open("w", encoding="utf-8") as handle:
            _write_jsonl(rows, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
