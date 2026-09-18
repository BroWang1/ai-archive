from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .constants import SAMPLE_DOCUMENTS, SAMPLE_QUERY


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call the KaLM vLLM FastAPI service.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--health", action="store_true")
    parser.add_argument("--endpoint", choices=("rerank", "score"), default="rerank")
    parser.add_argument("--json-file", type=Path)
    parser.add_argument("--return-margin", action="store_true")
    parser.add_argument("--top-k", type=int)
    parser.add_argument("--timeout", type=float, default=600.0)
    return parser


def request_json(
    method: str,
    url: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: float = 600.0,
) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from {url}: {detail}") from error
    return json.loads(raw)


def _demo_payload(
    endpoint: str,
    return_margin: bool,
    top_k: int | None,
) -> dict[str, Any]:
    if endpoint == "rerank":
        return {
            "query": SAMPLE_QUERY,
            "documents": list(SAMPLE_DOCUMENTS),
            "top_k": top_k,
            "return_margin": return_margin,
        }
    return {
        "pairs": [
            {
                "id": "positive",
                "query": SAMPLE_QUERY,
                "document": SAMPLE_DOCUMENTS[0],
            },
            {
                "id": "negative",
                "query": SAMPLE_QUERY,
                "document": SAMPLE_DOCUMENTS[1],
            },
        ],
        "return_margin": return_margin,
    }


def _load_payload(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain one JSON object.")
    return payload


def _request_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = (
        _load_payload(args.json_file)
        if args.json_file is not None
        else _demo_payload(args.endpoint, args.return_margin, args.top_k)
    )
    if args.return_margin:
        payload["return_margin"] = True
    if args.top_k is not None:
        if args.endpoint != "rerank":
            raise ValueError("--top-k is only valid with --endpoint rerank.")
        if args.top_k < 0:
            raise ValueError("--top-k must be non-negative.")
        payload["top_k"] = args.top_k
    return payload

    
def main() -> int:
    args = build_parser().parse_args()
    base_url = args.base_url.rstrip("/")
    if args.health:
        response = request_json("GET", f"{base_url}/health", timeout=args.timeout)
    else:
        payload = _request_payload(args)
        response = request_json(
            "POST",
            f"{base_url}/{args.endpoint}",
            payload=payload,
            timeout=args.timeout,
        )
    json.dump(response, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
