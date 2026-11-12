#!/usr/bin/env python3
"""Send request.t2i.json to a MiniMax-H3-Image server and write the PNG.

    python3 t2i.py [--url http://127.0.0.1:30000] [--prompt FILE] [--size WxH] [--out t2i.png]

--prompt and --size replace the prompt and the size in the request.

Uses only the Python standard library.
"""

import argparse
import base64
import json
import urllib.request
from pathlib import Path

# absolute(), not resolve(): in the Hugging Face cache this file is a symlink into blobs/.
HERE = Path(__file__).absolute().parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:30000", help="server base URL")
    parser.add_argument("--request", type=Path, default=HERE / "request.t2i.json", help="JSON request body")
    parser.add_argument("--prompt", type=Path, help="prompt file; replaces the prompt in the request")
    parser.add_argument("--size", help="WIDTHxHEIGHT; replaces the size in the request")
    parser.add_argument("--out", default="t2i.png")
    args = parser.parse_args()

    body = json.loads(args.request.read_text())
    if args.prompt:
        body["prompt"] = args.prompt.read_text()
    if args.size:
        body["size"] = args.size

    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/v1/images/generations",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=1800) as response:
        payload = json.load(response)
    with open(args.out, "wb") as image:
        image.write(base64.b64decode(payload["data"][0]["b64_json"]))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
