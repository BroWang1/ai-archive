"""Image loading and Qwen2-VL style patching without torch.

The numbers produced here match ``Qwen2VLImageProcessor`` (PIL backend) as used by
the PyTorch runtime: bicubic PIL resize, ``x / 255`` rescale, ``(x - 0.5) / 0.5``
normalization, and patchification into ``[C, T, P, P]`` rows ordered by merged
2x2 spatial blocks so that the vision merger can fold every four rows.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .image_geometry import prepare_model_image

try:  # optional HEIC/HEIF support, mirrors the PyTorch runtime
    from pillow_heif import register_heif_opener
except ImportError:  # pragma: no cover - optional dependency
    register_heif_opener = None
else:  # pragma: no cover - optional dependency
    register_heif_opener()

PATCH_SIZE = 16
TEMPORAL_PATCH_SIZE = 2
IMAGE_MEAN = 0.5
IMAGE_STD = 0.5
MIN_PIXELS = 65536
MAX_PIXELS = 2250000
MAX_LONG_EDGE = 1500


def smart_resize(
    height: int,
    width: int,
    factor: int,
    min_pixels: int = MIN_PIXELS,
    max_pixels: int = MAX_PIXELS,
) -> tuple[int, int]:
    """Rescale so both sides are multiples of ``factor`` and pixels stay in range."""
    if max(height, width) / min(height, width) > 200:
        raise ValueError(
            "absolute aspect ratio must be smaller than 200, got "
            f"{max(height, width) / min(height, width)}"
        )
    h_bar = round(height / factor) * factor
    w_bar = round(width / factor) * factor
    if h_bar * w_bar > max_pixels:
        beta = math.sqrt((height * width) / max_pixels)
        h_bar = max(factor, math.floor(height / beta / factor) * factor)
        w_bar = max(factor, math.floor(width / beta / factor) * factor)
    elif h_bar * w_bar < min_pixels:
        beta = math.sqrt(min_pixels / (height * width))
        h_bar = math.ceil(height * beta / factor) * factor
        w_bar = math.ceil(width * beta / factor) * factor
    return h_bar, w_bar


def load_image(item) -> Image.Image:
    """Open one content item and return the prepared RGB model image."""
    if isinstance(item, dict):
        source = item.get("path", item.get("bytes", item.get("image")))
    else:
        source = item
    if source is None:
        raise ValueError("image content requires path, bytes or an open PIL image")
    if isinstance(source, Image.Image):
        return prepare_model_image(source.convert("RGB"), MAX_LONG_EDGE)
    if (
        register_heif_opener is None
        and not isinstance(source, (bytes, bytearray))
        and Path(source).suffix.lower() in {".heic", ".heif"}
    ):
        raise RuntimeError("HEIC input requires pillow-heif; install requirements-mlx.txt")
    with Image.open(
        io.BytesIO(source) if isinstance(source, (bytes, bytearray)) else source
    ) as original:
        return prepare_model_image(original.convert("RGB"), MAX_LONG_EDGE)


def patchify(image: Image.Image, merge_size: int) -> tuple[np.ndarray, list[int]]:
    """Return ``(rows, grid_thw)`` for one prepared image.

    ``rows`` has shape ``(grid_t * grid_h * grid_w, C * T * P * P)`` with the
    merged-block ordering of the reference processor.
    """
    height, width = image.size[1], image.size[0]
    factor = PATCH_SIZE * merge_size
    resized_height, resized_width = smart_resize(height, width, factor)
    if (resized_width, resized_height) != image.size:
        image = image.resize((resized_width, resized_height), resample=Image.Resampling.BICUBIC)

    pixels = np.asarray(image, dtype=np.uint8)
    pixels = pixels.astype(np.float32) * np.float32(1.0 / 255.0)
    pixels = (pixels - np.float32(IMAGE_MEAN)) / np.float32(IMAGE_STD)
    # (H, W, C) -> (T=single frame, C, H, W); Qwen2-VL duplicates the frame when
    # temporal_patch_size > 1 so that a still image has grid_t == 1.
    frame = np.ascontiguousarray(pixels.transpose(2, 0, 1))[None]
    frames = np.repeat(frame, TEMPORAL_PATCH_SIZE, axis=0)

    channel = frames.shape[1]
    grid_t = frames.shape[0] // TEMPORAL_PATCH_SIZE
    grid_h, grid_w = resized_height // PATCH_SIZE, resized_width // PATCH_SIZE
    if grid_h % merge_size or grid_w % merge_size:
        raise ValueError(f"grid {(grid_h, grid_w)} is not divisible by merge size {merge_size}")

    patches = frames.reshape(
        1,
        grid_t,
        TEMPORAL_PATCH_SIZE,
        channel,
        grid_h // merge_size,
        merge_size,
        PATCH_SIZE,
        grid_w // merge_size,
        merge_size,
        PATCH_SIZE,
    )
    patches = patches.transpose(0, 1, 4, 7, 5, 8, 3, 2, 6, 9)
    rows = patches.reshape(
        grid_t * grid_h * grid_w, channel * TEMPORAL_PATCH_SIZE * PATCH_SIZE * PATCH_SIZE
    )
    return rows, [grid_t, grid_h, grid_w]


def prepare_images(items, merge_size: int) -> tuple[np.ndarray, np.ndarray]:
    """Patchify an ordered image list; returns ``(pixel_values, grid_thw)``."""
    rows = []
    grids = []
    for item in items:
        image = load_image(item)
        patched, grid = patchify(image, merge_size)
        rows.append(patched)
        grids.append(grid)
    if not rows:
        raise ValueError("expected at least one image")
    return np.concatenate(rows, axis=0), np.asarray(grids, dtype=np.int32)
