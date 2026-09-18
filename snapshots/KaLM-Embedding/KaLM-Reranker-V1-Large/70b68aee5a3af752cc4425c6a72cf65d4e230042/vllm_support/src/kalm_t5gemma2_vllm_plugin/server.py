from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .constants import (
    DEFAULT_DOCUMENT_MAX_LENGTH,
    DEFAULT_ENCODER_CHUNK_SIZE,
    DEFAULT_MAX_MODEL_LEN,
    DEFAULT_QUERY_MAX_LENGTH,
    MODEL_ID,
    SUPPORTED_ENCODER_CHUNK_SIZES,
    parse_encoder_chunk_size,
)
from .reranker import KaLMVLLMReranker


class RerankRequest(BaseModel):
    query: str
    documents: list[str] = Field(min_length=1)
    instruction: Optional[str] = None
    top_k: Optional[int] = None
    return_margin: bool = False


class ScorePair(BaseModel):
    query: str
    document: str
    id: Optional[Any] = None


class ScoreRequest(BaseModel):
    pairs: list[ScorePair] = Field(min_length=1)
    instruction: Optional[str] = None
    return_margin: bool = False


class OnlineRerankerService:
    def __init__(self, args: argparse.Namespace) -> None:
        self.model = str(args.model)
        self.query_max_length = int(args.query_max_length)
        self.document_max_length = int(args.document_max_length)
        self.encoder_chunk_size = parse_encoder_chunk_size(args.encoder_chunk_size)
        self.max_model_len = int(args.max_model_len)
        self.batch_size = int(args.batch_size)
        self.dtype = str(args.dtype)
        self.gpu_memory_utilization = float(args.gpu_memory_utilization)
        self.started_at = time.time()
        self.lock = threading.Lock()
        self.reranker = KaLMVLLMReranker(
            self.model,
            query_max_length=self.query_max_length,
            document_max_length=self.document_max_length,
            encoder_chunk_size=self.encoder_chunk_size,
            max_model_len=self.max_model_len,
            batch_size=self.batch_size,
            dtype=self.dtype,
            gpu_memory_utilization=self.gpu_memory_utilization,
            tensor_parallel_size=args.tensor_parallel_size,
        )

    def config(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "query_max_length": self.query_max_length,
            "document_max_length": self.document_max_length,
            "encoder_chunk_size": self.encoder_chunk_size,
            "max_model_len": self.max_model_len,
            "batch_size": self.batch_size,
            "dtype": self.dtype,
            "gpu_memory_utilization": self.gpu_memory_utilization,
            "tensor_parallel_size": 1,
            "supported_encoder_chunk_sizes": sorted(
                SUPPORTED_ENCODER_CHUNK_SIZES
            ),
        }

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "uptime_seconds": round(time.time() - self.started_at, 3),
            **self.config(),
        }

    def close(self) -> None:
        self.reranker.close()

    def rerank(self, request: RerankRequest) -> dict[str, Any]:
        if request.top_k is not None and request.top_k < 0:
            raise ValueError("top_k must be non-negative or null.")
        with self.lock:
            rankings = self.reranker.rank(
                request.query,
                request.documents,
                instruction=request.instruction,
                top_k=request.top_k,
                return_margin=request.return_margin,
            )
        results: list[dict[str, Any]] = []
        for item in rankings:
            result = {
                "index": int(item["corpus_id"]),
                "score": float(item["score"]),
            }
            if request.return_margin:
                result["margin"] = float(item["margin"])
            results.append(result)
        return {"object": "rerank", "results": results}

    def score(self, request: ScoreRequest) -> dict[str, Any]:
        pairs = [(item.query, item.document) for item in request.pairs]
        with self.lock:
            predictions = self.reranker.predict(
                pairs,
                instruction=request.instruction,
                return_margin=True,
            )
        results: list[dict[str, Any]] = []
        for index, (pair, prediction) in enumerate(zip(request.pairs, predictions)):
            assert isinstance(prediction, dict)
            result = {
                "index": index,
                "score": float(prediction["score"]),
            }
            if pair.id is not None:
                result["id"] = pair.id
            if request.return_margin:
                result["margin"] = float(prediction["margin"])
            results.append(result)
        return {"object": "score", "results": results}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="FastAPI server for the KaLM vLLM adapter.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--query-max-length", type=int, default=DEFAULT_QUERY_MAX_LENGTH)
    parser.add_argument(
        "--document-max-length", type=int, default=DEFAULT_DOCUMENT_MAX_LENGTH
    )
    parser.add_argument(
        "--encoder-chunk-size", default=str(DEFAULT_ENCODER_CHUNK_SIZE)
    )
    parser.add_argument("--max-model-len", type=int, default=DEFAULT_MAX_MODEL_LEN)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--dtype", default="bfloat16")
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.85)
    parser.add_argument("--tensor-parallel-size", type=int, default=1)
    parser.add_argument("--log-level", default="info")
    return parser


def create_app(service: OnlineRerankerService) -> FastAPI:
    app = FastAPI(title="KaLM vLLM Online Reranker", version="0.1.0")
    app.state.service = service
    app.router.add_event_handler("shutdown", service.close)

    @app.get("/health")
    def health():
        return app.state.service.health()

    @app.post("/rerank")
    def rerank(request: RerankRequest):
        try:
            return app.state.service.rerank(request)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    @app.post("/score")
    def score(request: ScoreRequest):
        try:
            return app.state.service.score(request)
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error

    return app


def main() -> int:
    args = build_parser().parse_args()
    args.encoder_chunk_size = parse_encoder_chunk_size(args.encoder_chunk_size)
    print("=== KaLM vLLM Online Reranker ===", flush=True)
    print(f"model: {args.model}", flush=True)
    print(f"query_max_length: {args.query_max_length}", flush=True)
    print(f"document_max_length: {args.document_max_length}", flush=True)
    print(f"encoder_chunk_size: {args.encoder_chunk_size}", flush=True)
    print(f"max_model_len: {args.max_model_len}", flush=True)
    print(f"listen: http://{args.host}:{args.port}", flush=True)

    service = OnlineRerankerService(args)
    app = create_app(service)
    import uvicorn

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        workers=1,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
