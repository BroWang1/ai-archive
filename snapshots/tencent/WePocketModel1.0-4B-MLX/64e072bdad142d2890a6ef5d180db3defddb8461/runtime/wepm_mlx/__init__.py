"""WePM MLX runtime: generation, multimodal embedding and JEV decision on Apple silicon.

The package reuses the Qwen3.5 backbone (hybrid gated-delta / full attention) and
the Qwen3-VL vision tower from ``mlx-vlm`` and adds the WePM-specific task modules:

* MGVB (multi-granularity visual bottleneck) that compacts native visual tokens,
* the learned E/J soft slots and their task heads,
* the multimodal RoPE index that supports explicit (compacted) visual positions.

Runtime imports are lazy so that preprocessing helpers stay usable in
environments without MLX or the model weights.
"""

from __future__ import annotations

__all__ = ["WePMRuntime", "load_runtime"]


def __getattr__(name):
    if name in __all__:
        from . import runtime

        return getattr(runtime, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
