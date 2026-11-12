"""Serve Sing VL S1 text and image decisions with FastAPI."""
import argparse
import asyncio
import base64
from io import BytesIO
import json
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from PIL import Image
import uvicorn

from model import MODEL_ID, PUBLIC_IMAGE_MAX_PIXELS, SingVLS1, Unsupported

MAX_BODY_BYTES = 64 * 1024 * 1024
logger = logging.getLogger(__name__)


def decode_image(encoded, image_root):
    if not isinstance(encoded, str):
        raise ValueError("images must be base64 strings, image data URLs, or file paths")
    is_data_url = encoded.startswith("data:")
    if is_data_url:
        header, delimiter, encoded = encoded.partition(",")
        if not delimiter or not header.startswith("data:image/") or not header.endswith(";base64"):
            raise ValueError("expected a base64 image data URI")
    try:
        with Image.open(BytesIO(base64.b64decode(encoded, validate=True))) as image:
            return image.copy()
    except (ValueError, Image.UnidentifiedImageError):
        if is_data_url or len(encoded) > 4096:
            raise
        if image_root is None:
            raise ValueError("expected base64 image data; file paths require --image-root") from None

    try:
        path = (image_root / encoded).resolve()
    except (OSError, RuntimeError) as exc:
        raise ValueError("invalid image file path") from exc
    if not path.is_relative_to(image_root):
        raise ValueError("image path is outside the configured image root")
    if not path.is_file() or path.stat().st_size > MAX_BODY_BYTES:
        raise ValueError("image path must name a file no larger than 64 MiB")
    with Image.open(path) as image:
        return image.copy()


def predict(engine, body, image_root):
    payload = json.loads(body)
    if not isinstance(payload, dict) or "state" not in payload:
        raise ValueError("expected an object with a state")
    images = payload.get("images", [])
    if not isinstance(images, list):
        raise ValueError("images must be a list")
    if len(images) > 4:
        raise Unsupported("the canvas holds at most four images per request")
    result, details = engine.predict(
        payload["state"], payload.get("questions"), [decode_image(image, image_root) for image in images],
    )
    if images:
        result["image_tokens"] = next(iter(details.values()))["image_tokens"]
    if payload.get("return_details") is True:
        result["evaluation_trace"] = details
    return result


def create_app(engine, image_root=None):
    app = FastAPI(title="Sing VL S1", redirect_slashes=False)
    inference_lock = asyncio.Lock()

    @app.get("/health")
    async def health():
        return {"status": "ready", "model": MODEL_ID, **engine.runtime()}

    @app.get("/v1/models")
    async def models():
        return {"object": "list", "data": [{"id": MODEL_ID, "object": "model"}]}

    @app.post("/v1/systemone", openapi_extra={
        "requestBody": {"required": True, "content": {"application/json": {
            "schema": {"type": "object", "required": ["state", "questions"]},
            "example": {
                "state": "The color is red.",
                "questions": {"color": {"type": "choice", "instructions": "Which color is named?",
                                        "criteria": {"red": "Red", "blue": "Blue"}}},
            },
        }}},
    })
    async def systemone(request: Request):
        try:
            size = int(request.headers.get("content-length", "0"))
            if not 0 < size <= MAX_BODY_BYTES:
                return JSONResponse({"error": "invalid request body size"}, status_code=413)
            async with inference_lock:
                body = bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body) > MAX_BODY_BYTES:
                        return JSONResponse({"error": "invalid request body size"}, status_code=413)
                result = await run_in_threadpool(predict, engine, body, image_root)
            return JSONResponse(result)
        except Unsupported as exc:
            return JSONResponse({"error": str(exc)}, status_code=422)
        except (ValueError, OSError, Image.DecompressionBombError) as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)
        except Exception:
            logger.exception("Inference failed")
            return JSONResponse({"error": "inference failed"}, status_code=500)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--port", type=int, default=8173)
    parser.add_argument("--image-max-pixels", type=int, default=PUBLIC_IMAGE_MAX_PIXELS)
    parser.add_argument("--image-root", type=Path, help="allow image file paths under this directory")
    args = parser.parse_args()
    if args.image_root is not None:
        if not args.image_root.is_dir():
            parser.error("--image-root must name an existing directory")
        args.image_root = args.image_root.resolve()
    engine = SingVLS1(args.model, args.device, args.image_max_pixels)
    print(json.dumps(engine.runtime()), flush=True)
    uvicorn.run(create_app(engine, args.image_root), host="127.0.0.1", port=args.port, workers=1)


if __name__ == "__main__":
    main()
