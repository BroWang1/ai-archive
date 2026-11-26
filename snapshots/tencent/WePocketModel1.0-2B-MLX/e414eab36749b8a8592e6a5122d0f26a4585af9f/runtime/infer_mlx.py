#!/usr/bin/env python3
"""Run G/E/J inference with MLX on Apple silicon and write a JSON result."""

import argparse
import json
import sys
import time
from pathlib import Path

from wepm_mlx.common import write_json
from wepm_mlx.runtime import WePMRuntime
from wepm_mlx.weights import resolve_model_dir

BUNDLED_MODEL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = (
    str(BUNDLED_MODEL_DIR)
    if (BUNDLED_MODEL_DIR / "wepm_mlx.json").is_file()
    else "tencent/WePocketModel1.0-4B"
)


def load_content(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    content = payload.get("content") if isinstance(payload, dict) else None
    if not isinstance(content, list) or not content:
        raise ValueError(f"{path} must contain a nonempty content array")
    resolved = []
    for index, item in enumerate(content):
        if not isinstance(item, dict) or item.get("type") not in {"text", "image"}:
            raise ValueError(f"content[{index}] must be a text or image object")
        if item["type"] == "text":
            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError(f"content[{index}].text must be nonempty")
            resolved.append({"type": "text", "text": text})
            continue
        value = item.get("path")
        if not isinstance(value, str) or not value:
            raise ValueError(f"content[{index}].path must be nonempty")
        image = Path(value).expanduser()
        if not image.is_absolute():
            image = path.parent / image
        image = image.resolve()
        if not image.is_file():
            raise FileNotFoundError(image)
        resolved.append({"type": "image", "path": image})
    return resolved


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=f"{__doc__} Runs on the Apple silicon GPU through MLX."
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help="Hugging Face model repo ID or a local WePM export",
    )
    parser.add_argument("--revision", help="Hub branch, tag or commit to download")
    parser.add_argument(
        "--task", choices=["generate", "embed", "both", "decision"], default="generate"
    )
    parser.add_argument("--prompt", help="text input; images are placed before it")
    parser.add_argument("--image", type=Path, action="append", default=[])
    parser.add_argument(
        "--content-json",
        type=Path,
        help="ordered content array for text/image interleaving",
    )
    parser.add_argument(
        "--decision-json",
        type=Path,
        help="SystemOne request with state and questions.q",
    )
    parser.add_argument("--max-new-tokens", type=int, default=64)
    parser.add_argument(
        "--embedding-dim",
        type=int,
        help="embedding dimension supported by the checkpoint (default: its full dimension)",
    )
    parser.add_argument(
        "--dtype",
        choices=["bfloat16", "float32"],
        default="bfloat16",
        help="weight dtype; float32 is only useful for numerical checks",
    )
    parser.add_argument(
        "--quantize-bits",
        type=int,
        choices=[4, 8],
        help="quantize linear weights to 4 or 8 bits (smaller resident memory)",
    )
    parser.add_argument("--quantize-group-size", type=int, default=64)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    if not 1 <= args.max_new_tokens <= 512:
        parser.error("max-new-tokens must be in [1, 512]")
    if args.embedding_dim is not None and args.embedding_dim < 1:
        parser.error("embedding-dim must be positive")
    if (args.task == "decision") != (args.decision_json is not None):
        parser.error("--decision-json is required only with --task decision")
    if args.content_json and (args.prompt is not None or args.image):
        parser.error("--content-json cannot be combined with --prompt or --image")
    if args.task == "decision" and args.content_json:
        parser.error("decision input is defined by --decision-json")
    if args.output.exists() or args.output.is_symlink():
        parser.error(f"output already exists: {args.output}")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    decision_request = (
        json.loads(args.decision_json.read_text(encoding="utf-8"))
        if args.decision_json
        else None
    )
    if args.content_json:
        content = load_content(args.content_json.resolve())
    else:
        content = [{"type": "image", "path": image.expanduser().resolve()} for image in args.image]
        prompt = args.prompt
        if prompt is None and not content and args.task != "decision":
            prompt = "请用一句话介绍你自己。"
        if prompt:
            content.append({"type": "text", "text": prompt})

    import mlx.core as mx

    dtype = mx.bfloat16 if args.dtype == "bfloat16" else mx.float32
    model_dir = resolve_model_dir(args.model, revision=args.revision)
    started = time.monotonic()
    runtime = WePMRuntime(
        model_dir,
        dtype=dtype,
        quantize_bits=args.quantize_bits,
        quantize_group_size=args.quantize_group_size,
    )
    load_seconds = time.monotonic() - started

    result = {}
    try:
        if args.task in ("generate", "both"):
            result["generation"] = runtime.generate(content, args.max_new_tokens)
        if args.task in ("embed", "both"):
            dims = (
                [args.embedding_dim]
                if args.embedding_dim is not None
                else list(runtime.task.embedding_mrl_dims)
            )
            result["embedding"] = runtime.embed(content, dims=dims)
        if args.task == "decision":
            images = [image.expanduser().resolve() for image in args.image]
            result["decision"] = runtime.decide(decision_request, images)
    finally:
        runtime.close()

    result["runtime"] = {
        "backend": "mlx",
        "device": "apple-silicon-gpu",
        "dtype": args.dtype,
        "quantize_bits": args.quantize_bits,
        "model_dir": str(model_dir),
        "load_seconds": round(load_seconds, 3),
        "peak_memory_gib": round(mx.get_peak_memory() / 2**30, 3),
    }
    write_json(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "backend": "mlx",
                "dtype": args.dtype,
                "load_seconds": round(load_seconds, 3),
                "generation": result.get("generation", {}).get("text"),
                "decision": result.get("decision", {}).get("answers"),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
