"""Shared model-input geometry; preserve all pixels in extreme-aspect images.

Synced from ``inference/runtime_sources/image_geometry.py`` of the WePM release so
that the MLX runtime preprocesses images exactly like the PyTorch runtime.
"""
import math


def prepared_sizes(width, height, max_long_edge=1500):
    if width < 1 or height < 1:
        raise ValueError('image dimensions must be positive')
    scale = min(1.0, max_long_edge / max(width, height)) if max_long_edge > 0 else 1.0
    resized = (max(1, round(width * scale)), max(1, round(height * scale)))
    w, h = resized
    # Padding only on the right/bottom preserves the origin and existing pixels.
    # Apply after rounding: a legal original aspect ratio can become illegal
    # when a narrow dimension rounds down during long-edge resizing.
    padded = (max(w, math.ceil(h / 200)), max(h, math.ceil(w / 200)))
    return resized, padded


def prepare_model_image(image, max_long_edge=1500):
    from PIL import Image
    resized, padded = prepared_sizes(*image.size, max_long_edge)
    if image.size != resized:
        image = image.resize(resized, resample=Image.Resampling.BICUBIC)
    if resized != padded:
        result = Image.new(image.mode, padded, 'white')
        result.paste(image, (0, 0))
        image = result
    return image
