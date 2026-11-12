#!/usr/bin/env python3
"""Expand a short text-to-image prompt with MiniMax-H3-Image-PE.

Sends the supplied release request (system prompt, user template,
sampling parameters and JSON schema from ../prompt/t2i/) to an OpenAI-compatible
chat endpoint, checks the answer and prints
{"expanded_caption": ..., "aspect_ratio": ...}.

    python3 scripts/expand_prompt.py --url http://127.0.0.1:30000 "a lighthouse on a cliff at sunset"
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

# absolute(), not resolve(): in the Hugging Face cache this file is a symlink into blobs/.
PROMPT_DIR = Path(__file__).absolute().parent.parent / "prompt" / "t2i"


def build_request(prompt: str, model: str) -> dict:
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a non-empty string")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    system_prompt = (PROMPT_DIR / "system_prompt.txt").read_text(encoding="utf-8").rstrip("\n")
    template = (PROMPT_DIR / "task_prompt.txt").read_text(encoding="utf-8")
    body = json.loads((PROMPT_DIR / "request_params.json").read_text(encoding="utf-8"))
    body.update(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": template.format(prompt)},
        ],
        stream=False,
    )
    return body


def parse_response(response: dict, allowed_ratios: list) -> dict:
    choices = response.get("choices") if isinstance(response, dict) else None
    if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
        raise ValueError("expected exactly one response choice")
    choice = choices[0]
    if choice.get("finish_reason") != "stop":
        raise ValueError(f"generation did not finish: finish_reason={choice.get('finish_reason')!r}")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("expected a response message")
    thinking = message.get("reasoning_content")
    if not isinstance(thinking, str) or not thinking.strip():
        raise ValueError("no thinking section; start the server with --reasoning-parser qwen3")
    if not isinstance(message.get("content"), str):
        raise ValueError("expected JSON text in message.content")
    result = json.loads(message["content"])
    if not isinstance(result, dict) or set(result) != {"expanded_caption", "aspect_ratio"}:
        raise ValueError("expected exactly expanded_caption and aspect_ratio")
    if not isinstance(result["aspect_ratio"], str) or result["aspect_ratio"] not in allowed_ratios:
        raise ValueError(f"unsupported aspect ratio: {result['aspect_ratio']!r}")
    if not isinstance(result["expanded_caption"], str) or not result["expanded_caption"].strip():
        raise ValueError("expanded_caption must be a non-empty string")
    return {"expanded_caption": result["expanded_caption"].strip(), "aspect_ratio": result["aspect_ratio"]}


def select_model(response: dict) -> str:
    models = response.get("data") if isinstance(response, dict) else None
    if not isinstance(models, list) or len(models) != 1:
        raise ValueError("server must expose exactly one model; specify --model explicitly")
    model = models[0].get("id") if isinstance(models[0], dict) else None
    if not isinstance(model, str) or not model.strip():
        raise ValueError("server returned an invalid model ID; specify --model explicitly")
    return model


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("prompt", help="short prompt, any language")
    ap.add_argument("--url", default="http://127.0.0.1:30000", help="server base URL")
    ap.add_argument("--model", default=None, help="served model name (default: the server's only model)")
    ap.add_argument("--timeout", type=float, default=1200)
    ap.add_argument("--save-response", type=Path, default=None, help="also write the raw chat response here")
    ap.add_argument("--dry-run", action="store_true", help="print the request without network access; requires --model")
    ap.add_argument("--api-key-env", default="OPENAI_API_KEY", help="optional environment variable holding a bearer token")
    args = ap.parse_args()

    if args.dry_run:
        if not args.model:
            ap.error("--dry-run requires --model")
        print(json.dumps(build_request(args.prompt, args.model), ensure_ascii=False, indent=2))
        return 0
    base = args.url.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    headers = {"Content-Type": "application/json"}
    api_key = os.environ.get(args.api_key_env)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    model = args.model
    if model is None:
        request = urllib.request.Request(f"{base}/models", headers=headers)
        with urllib.request.urlopen(request, timeout=args.timeout) as r:
            model = select_model(json.load(r))
    body = build_request(args.prompt, model)
    req = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(),
                                 headers=headers)
    with urllib.request.urlopen(req, timeout=args.timeout) as r:
        response = json.load(r)
    if args.save_response:
        args.save_response.write_text(json.dumps(response, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    ratios = body["response_format"]["json_schema"]["schema"]["properties"]["aspect_ratio"]["enum"]
    print(json.dumps(parse_response(response, ratios), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
