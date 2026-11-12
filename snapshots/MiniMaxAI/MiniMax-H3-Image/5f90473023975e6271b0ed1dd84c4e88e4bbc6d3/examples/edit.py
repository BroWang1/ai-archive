#!/usr/bin/env python3
"""Send reference1.png and prompt.edit.txt to a MiniMax-H3-Image server and write the PNG.

    python3 edit.py [--url http://127.0.0.1:30000] [--out edit.png]

The images are sent in --image order, which defines <Picture 1>, <Picture 2>, ... in the
prompt. Uses only the Python standard library.
"""

import argparse
import base64
import json
import mimetypes
import urllib.request
import uuid
from pathlib import Path

# absolute(), not resolve(): in the Hugging Face cache this file is a symlink into blobs/.
HERE = Path(__file__).absolute().parent


def multipart(fields: dict, images: list) -> tuple:
    boundary = f"minimax-h3-image-{uuid.uuid4().hex}"
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    for path in images:
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n".encode()
        )
        parts.append(path.read_bytes() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:30000", help="server base URL")
    parser.add_argument("--image", action="append", type=Path,
                        help="reference image; repeat for <Picture 2>, ... (default: reference1.png)")
    parser.add_argument("--prompt", type=Path, default=HERE / "prompt.edit.txt", help="prompt file")
    parser.add_argument("--size", default="4096x4096", help="WIDTHxHEIGHT")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--out", default="edit.png")
    args = parser.parse_args()

    fields = {
        "prompt": args.prompt.read_text(),
        "size": args.size,
        "seed": str(args.seed),
        "generator_device": "cpu",
        "response_format": "b64_json",
        "output_format": "png",
    }
    body, content_type = multipart(fields, args.image or [HERE / "reference1.png"])
    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/v1/images/edits", data=body, headers={"Content-Type": content_type}
    )
    with urllib.request.urlopen(request, timeout=1800) as response:
        payload = json.load(response)
    with open(args.out, "wb") as image:
        image.write(base64.b64decode(payload["data"][0]["b64_json"]))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
