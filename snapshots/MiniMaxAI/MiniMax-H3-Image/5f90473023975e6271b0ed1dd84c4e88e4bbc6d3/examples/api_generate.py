#!/usr/bin/env python3
"""Generate the same image with the MiniMax API, as a reference for the local result.

    export MINIMAX_API_BASE=https://api.minimax.cn   # CN; Global: https://api.minimax.io
    export MINIMAX_API_KEY=<API key>
    python3 api_generate.py t2i    # POST /v1/images/generations with instruction.t2i.txt
    python3 api_generate.py edit   # POST /v1/images/edits with instruction.edit.txt and reference1.png

The API applies the same prompt enhancement internally. Writes the image (api_<task>.png) and
the prompt the API used (api_<task>_revised_prompt.txt). Uses only the Python standard library.
"""

import argparse
import base64
import json
from pathlib import Path

from context_ir import HERE, add_task_arguments, post, request_body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_task_arguments(parser)
    args = parser.parse_args()

    instruction = args.instruction or HERE / f"instruction.{args.task}.txt"
    body = request_body(args.task, instruction, args.image, args.size)
    body.update({"n": 1, "response_format": "b64_json", "output_format": "png"})
    path = "/v1/images/generations" if args.task == "t2i" else "/v1/images/edits"
    result = post(path, body)
    item = result["data"][0]
    if "error" in item:
        raise RuntimeError(f"image failed: {item['error']} (request_id {result.get('request_id')})")
    Path(f"api_{args.task}.png").write_bytes(base64.b64decode(item["b64_json"]))
    Path(f"api_{args.task}_revised_prompt.txt").write_text(item["revised_prompt"])
    print(json.dumps({"request_id": result.get("request_id"), "size": item.get("size"), "usage": result.get("usage")}))


if __name__ == "__main__":
    main()
