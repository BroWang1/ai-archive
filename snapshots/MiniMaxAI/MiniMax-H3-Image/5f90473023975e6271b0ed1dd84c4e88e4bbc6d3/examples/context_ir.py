#!/usr/bin/env python3
"""Enhance a prompt with the MiniMax H3-Image-Context-IR API.

    export MINIMAX_API_BASE=https://api.minimax.cn   # CN; Global: https://api.minimax.io
    export MINIMAX_API_KEY=<API key>
    python3 context_ir.py t2i    # instruction.t2i.txt
    python3 context_ir.py edit   # instruction.edit.txt with reference1.png

Sends the instruction (and, for edit, the reference images) to POST /v1/h3_image_context_ir
and writes the enhanced prompt to revised_prompt.txt. Unless --size is given, the API also
picks the aspect ratio; the matching size of about 16 megapixels is written to
revised_size.txt. Pass the files to t2i.py / edit.py with --prompt and --size. Uses only the
Python standard library.
"""

import argparse
import base64
import json
import math
import mimetypes
import os
import urllib.request
from pathlib import Path

# absolute(), not resolve(): in the Hugging Face cache this file is a symlink into blobs/.
HERE = Path(__file__).absolute().parent
AREA = 4096 * 4096


def data_uri(path: Path) -> str:
    content_type = mimetypes.guess_type(path.name)[0]
    if content_type is None:
        raise ValueError(f"unknown image type: {path}")
    return f"data:{content_type};base64,{base64.b64encode(path.read_bytes()).decode()}"


def size_for(aspect_ratio: str) -> str:
    """About 16 megapixels at the ratio, both sides multiples of 32 (matches the README Sizes table)."""
    x, y = (int(v) for v in aspect_ratio.split(":"))
    width = round(math.sqrt(AREA * x / y) / 32) * 32
    height = round(math.sqrt(AREA * y / x) / 32) * 32
    return f"{width}x{height}"


def post(path: str, body: dict) -> dict:
    request = urllib.request.Request(
        f"{os.environ['MINIMAX_API_BASE'].rstrip('/')}{path}",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {os.environ['MINIMAX_API_KEY']}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)


def request_body(task: str, instruction: Path, images: list, size) -> dict:
    body = {"model": "MiniMax-H3-Image", "prompt": instruction.read_text().strip()}
    if task == "edit":
        body["images"] = [{"image_url": data_uri(path)} for path in images or [HERE / "reference1.png"]]
    if size:
        body["size"] = size
    return body


def add_task_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("task", choices=["t2i", "edit"])
    parser.add_argument("--instruction", type=Path, help="default: instruction.<task>.txt")
    parser.add_argument("--image", action="append", type=Path,
                        help="edit only: reference image; repeat for <Picture 2>, ... (default: reference1.png)")
    parser.add_argument("--size", help="WIDTHxHEIGHT of the image you will generate (default: chosen by the API)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_task_arguments(parser)
    parser.add_argument("--out", default="revised_prompt.txt")
    parser.add_argument("--size-out", default="revised_size.txt", help="written when the API picks the aspect ratio")
    args = parser.parse_args()

    instruction = args.instruction or HERE / f"instruction.{args.task}.txt"
    result = post("/v1/h3_image_context_ir", request_body(args.task, instruction, args.image, args.size))
    Path(args.out).write_text(result["revised_prompt"])
    summary = {"request_id": result.get("request_id"), "usage": result.get("usage")}
    if "aspect_ratio" in result:
        summary["aspect_ratio"] = result["aspect_ratio"]
        summary["size"] = size_for(result["aspect_ratio"])
        Path(args.size_out).write_text(summary["size"])
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
