# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""KV-cache slicing, concatenation, and rotary position alignment.

Cache inputs may be tuples or objects exposing key_cache and value_cache.
All token intervals are half-open: [start, end). UnitKVSpan references a
region of a source cache without copying the underlying tensors.
"""

from __future__ import annotations
import copy
import math
from dataclasses import dataclass
from functools import reduce
from operator import mul
from typing import Any, Iterable, Sequence

CacheLike = Any
LayerKV = tuple[Any, Any]


@dataclass(frozen=True)
class UnitKVSpan:
    """Immutable location of one logical media unit in a source KV cache."""

    unit_id: str
    start: int
    end: int
    timestamp_seconds: float
    kind: str

    def __post_init__(self) -> None:
        if not isinstance(self.unit_id, str) or not self.unit_id.strip():
            raise ValueError("unit_id must be a non-empty string")
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise TypeError("span start must be an integer")
        if isinstance(self.end, bool) or not isinstance(self.end, int):
            raise TypeError("span end must be an integer")
        if self.start < 0 or self.end <= self.start:
            raise ValueError(
                f"unit {self.unit_id!r} has invalid half-open span [{self.start}, {self.end})"
            )
        if not math.isfinite(float(self.timestamp_seconds)):
            raise ValueError("timestamp_seconds must be finite")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("kind must be a non-empty string")

    @property
    def token_count(self) -> int:
        """Number of cache tokens referenced by this unit."""
        return self.end - self.start


@dataclass(frozen=True)
class AssembledKVCache:
    """Immutable description of an assembled cache and its selected units."""

    cache: CacheLike
    unit_ids: tuple[str, ...]
    token_count: int
    estimated_bytes: int
    source_positions: tuple[int, ...]


def _cache_layers(cache: CacheLike) -> tuple[tuple[LayerKV, ...], str]:
    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        keys = tuple(cache.key_cache)
        values = tuple(cache.value_cache)
        if len(keys) != len(values):
            raise ValueError(
                "DynamicCache-like key_cache and value_cache have different layer counts"
            )
        style = "dynamic"
        layers = tuple(zip(keys, values))
    elif isinstance(cache, (tuple, list)):
        style = "tuple" if isinstance(cache, tuple) else "list"
        parsed: list[LayerKV] = []
        for layer_index, layer in enumerate(cache):
            if not isinstance(layer, (tuple, list)) or len(layer) != 2:
                raise TypeError(
                    f"legacy cache layers must be two-item (key, value) sequences; layer {layer_index} is invalid"
                )
            parsed.append((layer[0], layer[1]))
        layers = tuple(parsed)
    else:
        raise TypeError(
            "cache must be a legacy tuple/list or expose key_cache and value_cache"
        )
    if not layers:
        raise ValueError("cache must contain at least one initialized layer")
    for layer_index, (key, value) in enumerate(layers):
        _validate_layer_pair(key, value, layer_index)
    return (layers, style)


def _prevalidated_cache_layers(cache: CacheLike) -> tuple[tuple[LayerKV, ...], str]:
    """Expose layers already validated when captured by the model adapter."""
    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        keys = tuple(cache.key_cache)
        values = tuple(cache.value_cache)
        if len(keys) != len(values):
            raise ValueError(
                "DynamicCache-like key_cache and value_cache have different layer counts"
            )
        return (tuple(zip(keys, values)), "dynamic")
    if isinstance(cache, tuple):
        return (tuple(cache), "tuple")
    if isinstance(cache, list):
        return (tuple(cache), "list")
    raise TypeError(
        "cache must be a legacy tuple/list or expose key_cache and value_cache"
    )


def _normalise_axis(axis: int, rank: int) -> int:
    resolved = axis + rank if axis < 0 else axis
    if resolved < 0 or resolved >= rank:
        raise ValueError(f"sequence_dim {axis} is invalid for a rank-{rank} tensor")
    return resolved


def _validate_layer_pair(key: Any, value: Any, layer_index: int) -> None:
    if not hasattr(key, "shape") or not hasattr(value, "shape"):
        raise TypeError(f"cache layer {layer_index} key/value must expose shape")
    key_shape = tuple((int(size) for size in key.shape))
    value_shape = tuple((int(size) for size in value.shape))
    if len(key_shape) < 2 or len(value_shape) < 2:
        raise ValueError(f"cache layer {layer_index} tensors must have rank >= 2")
    if key_shape != value_shape:
        raise ValueError(
            f"cache layer {layer_index} key/value shapes differ: {key_shape} != {value_shape}"
        )


def _cache_sequence_length(layers: Sequence[LayerKV], sequence_dim: int) -> int:
    lengths: list[int] = []
    for layer_index, (key, _) in enumerate(layers):
        axis = _normalise_axis(sequence_dim, len(key.shape))
        length = int(key.shape[axis])
        lengths.append(length)
        if length != lengths[0]:
            raise ValueError(
                f"all initialized cache layers must have the same sequence length; layer 0 has {lengths[0]}, layer {layer_index} has {length}"
            )
    return lengths[0]


def _slice_tensor(tensor: Any, start: int, end: int, sequence_dim: int) -> Any:
    axis = _normalise_axis(sequence_dim, len(tensor.shape))
    index = [slice(None)] * len(tensor.shape)
    index[axis] = slice(start, end)
    return tensor[tuple(index)]


def _clone_tensor(tensor: Any) -> Any:
    clone = getattr(tensor, "clone", None)
    if callable(clone):
        return clone()
    copy_method = getattr(tensor, "copy", None)
    if callable(copy_method):
        return copy_method()
    raise TypeError("cache tensor must support clone() or copy()")


def _tensor_backend_name(tensor: Any) -> str:
    return type(tensor).__module__.split(".", maxsplit=1)[0]


def _concatenate_tensors(tensors: Sequence[Any], sequence_dim: int) -> Any:
    if not tensors:
        raise ValueError("cannot concatenate an empty tensor sequence")
    axis = _normalise_axis(sequence_dim, len(tensors[0].shape))
    backend = _tensor_backend_name(tensors[0])
    if any((_tensor_backend_name(tensor) != backend for tensor in tensors)):
        raise TypeError("all cache tensors being concatenated must use one backend")
    if backend == "torch":
        import torch

        return torch.cat(tuple(tensors), dim=axis)
    if backend == "numpy":
        import numpy

        return numpy.concatenate(tuple(tensors), axis=axis)
    concatenate = getattr(type(tensors[0]), "concatenate", None)
    if concatenate is None:
        raise TypeError(
            f"unsupported tensor backend {backend!r}; expected PyTorch or NumPy"
        )
    return concatenate(tuple(tensors), axis=axis)


def _preallocate_and_copy_tensors(tensors: Sequence[Any], sequence_dim: int) -> Any:
    """Allocate the joined tensor once and copy every source into its slice."""
    if not tensors:
        raise ValueError("cannot concatenate an empty tensor sequence")
    axis = _normalise_axis(sequence_dim, len(tensors[0].shape))
    backend = _tensor_backend_name(tensors[0])
    if any((_tensor_backend_name(tensor) != backend for tensor in tensors)):
        raise TypeError("all cache tensors being concatenated must use one backend")
    reference_dtype = getattr(tensors[0], "dtype", None)
    reference_device = getattr(tensors[0], "device", None)
    for tensor in tensors[1:]:
        if getattr(tensor, "dtype", None) != reference_dtype:
            raise TypeError("preallocated cache concatenation requires one dtype")
        if str(getattr(tensor, "device", None)) != str(reference_device):
            raise TypeError("preallocated cache concatenation requires one device")
    output_shape = list((int(size) for size in tensors[0].shape))
    output_shape[axis] = sum((int(tensor.shape[axis]) for tensor in tensors))
    if backend == "torch":
        import torch

        output = tensors[0].new_empty(tuple(output_shape))
        torch.cat(tuple(tensors), dim=axis, out=output)
        return output
    if backend == "numpy":
        import numpy

        output = numpy.empty(tuple(output_shape), dtype=tensors[0].dtype)
        numpy.concatenate(tuple(tensors), axis=axis, out=output)
        return output
    return _concatenate_tensors(tensors, sequence_dim)


def _preallocate_and_copy_prevalidated_tensors(
    tensors: Sequence[Any], sequence_dim: int
) -> Any:
    """Join model-validated tensors without repeating dtype/device scans."""
    if not tensors:
        raise ValueError("cannot concatenate an empty tensor sequence")
    axis = _normalise_axis(sequence_dim, len(tensors[0].shape))
    backend = _tensor_backend_name(tensors[0])
    output_shape = list((int(size) for size in tensors[0].shape))
    output_shape[axis] = sum((int(tensor.shape[axis]) for tensor in tensors))
    if backend == "torch":
        import torch

        output = tensors[0].new_empty(tuple(output_shape))
        torch.cat(tuple(tensors), dim=axis, out=output)
        return output
    if backend == "numpy":
        import numpy

        output = numpy.empty(tuple(output_shape), dtype=tensors[0].dtype)
        numpy.concatenate(tuple(tensors), axis=axis, out=output)
        return output
    return _preallocate_and_copy_tensors(tensors, sequence_dim)


def _reshape_tensor(tensor: Any, shape: Sequence[int]) -> Any:
    reshape = getattr(tensor, "reshape", None)
    if reshape is None:
        raise TypeError("RoPE cosine/sine tensors must support reshape")
    return reshape(tuple(shape))


def _align_tensor_like(tensor: Any, reference: Any) -> Any:
    """Keep RoPE arithmetic on the key tensor's device and dtype."""
    backend = _tensor_backend_name(reference)
    if _tensor_backend_name(tensor) != backend:
        raise TypeError("RoPE tables and keys must use the same tensor backend")
    if backend == "torch":
        return tensor.to(device=reference.device, dtype=reference.dtype)
    if backend == "numpy":
        return tensor.astype(reference.dtype, copy=False)
    return tensor


def _set_seen_tokens(cache: Any, token_count: int) -> None:
    try:
        setattr(cache, "_seen_tokens", token_count)
    except (AttributeError, TypeError):
        pass
    try:
        setattr(cache, "seen_tokens", token_count)
    except (AttributeError, TypeError):
        pass


def _rebuild_cache(
    source_cache: CacheLike, layers: Sequence[LayerKV], style: str, token_count: int
) -> CacheLike:
    if style == "tuple":
        return tuple(((key, value) for (key, value) in layers))
    if style == "list":
        return [(key, value) for (key, value) in layers]
    try:
        rebuilt = copy.copy(source_cache)
    except (TypeError, copy.Error):
        try:
            rebuilt = type(source_cache)()
        except TypeError as exc:
            raise TypeError(
                "DynamicCache-like input must support shallow copy or a no-argument constructor"
            ) from exc
    try:
        rebuilt.key_cache = [key for (key, _) in layers]
        rebuilt.value_cache = [value for (_, value) in layers]
    except (AttributeError, TypeError) as exc:
        raise TypeError(
            "DynamicCache-like key_cache/value_cache attributes must be writable"
        ) from exc
    _set_seen_tokens(rebuilt, token_count)
    return rebuilt


def capture_unit_kv_span(
    source_cache: CacheLike,
    *,
    unit_id: str,
    start: int,
    end: int,
    timestamp_seconds: float,
    kind: str,
    sequence_dim: int = -2,
) -> UnitKVSpan:
    """Validate and capture an immutable logical-unit reference."""
    span = UnitKVSpan(
        unit_id=unit_id,
        start=start,
        end=end,
        timestamp_seconds=timestamp_seconds,
        kind=kind,
    )
    (layers, _) = _cache_layers(source_cache)
    cache_length = _cache_sequence_length(layers, sequence_dim)
    if span.end > cache_length:
        raise ValueError(
            f"unit {unit_id!r} ends at token {span.end}, beyond cache length {cache_length}"
        )
    return span


def slice_kv_cache(
    cache: CacheLike,
    start: int,
    end: int,
    *,
    clone: bool = True,
    sequence_dim: int = -2,
) -> CacheLike:
    """Extract one half-open token interval from every cache layer.

    ``clone=True`` is the safe archive default: the returned unit cache owns its
    tensor storage and will not change when the live cache is mutated or freed.
    ``clone=False`` may return backend views and is intended only for transient
    assembly paths.
    """
    if isinstance(start, bool) or not isinstance(start, int):
        raise TypeError("start must be an integer")
    if isinstance(end, bool) or not isinstance(end, int):
        raise TypeError("end must be an integer")
    if not isinstance(clone, bool):
        raise TypeError("clone must be a boolean")
    (layers, style) = _cache_layers(cache)
    cache_length = _cache_sequence_length(layers, sequence_dim)
    if start < 0 or end < start or end > cache_length:
        raise ValueError(
            f"invalid cache slice [{start}, {end}) for length {cache_length}"
        )
    sliced_layers: list[LayerKV] = []
    for key, value in layers:
        sliced_key = _slice_tensor(key, start, end, sequence_dim)
        sliced_value = _slice_tensor(value, start, end, sequence_dim)
        if clone:
            sliced_key = _clone_tensor(sliced_key)
            sliced_value = _clone_tensor(sliced_value)
        sliced_layers.append((sliced_key, sliced_value))
    sliced = tuple(sliced_layers)
    return _rebuild_cache(cache, sliced, style, end - start)


def _concat_kv_caches_impl(
    caches: Iterable[CacheLike], *, sequence_dim: int = -2, preallocate: bool
) -> CacheLike:
    cache_items = tuple(caches)
    if not cache_items:
        raise ValueError("at least one cache is required for concatenation")
    parsed = tuple((_cache_layers(cache) for cache in cache_items))
    layer_count = len(parsed[0][0])
    if any((len(layers) != layer_count for (layers, _) in parsed)):
        raise ValueError("all caches must contain the same number of layers")
    lengths = tuple(
        (_cache_sequence_length(layers, sequence_dim) for (layers, _) in parsed)
    )
    output_layers: list[LayerKV] = []
    for layer_index in range(layer_count):
        keys = tuple((layers[layer_index][0] for (layers, _) in parsed))
        values = tuple((layers[layer_index][1] for (layers, _) in parsed))
        reference_key_shape = tuple(keys[0].shape)
        reference_value_shape = tuple(values[0].shape)
        key_axis = _normalise_axis(sequence_dim, len(reference_key_shape))
        value_axis = _normalise_axis(sequence_dim, len(reference_value_shape))
        for cache_index, (key, value) in enumerate(zip(keys[1:], values[1:]), 1):
            key_shape = tuple(key.shape)
            value_shape = tuple(value.shape)
            if (
                key_shape[:key_axis] + key_shape[key_axis + 1 :]
                != reference_key_shape[:key_axis] + reference_key_shape[key_axis + 1 :]
                or value_shape[:value_axis] + value_shape[value_axis + 1 :]
                != reference_value_shape[:value_axis]
                + reference_value_shape[value_axis + 1 :]
            ):
                raise ValueError(
                    f"cache {cache_index} layer {layer_index} has incompatible shape"
                )
        output_layers.append(
            (
                (
                    _preallocate_and_copy_tensors(keys, sequence_dim)
                    if preallocate
                    else _concatenate_tensors(keys, sequence_dim)
                ),
                (
                    _preallocate_and_copy_tensors(values, sequence_dim)
                    if preallocate
                    else _concatenate_tensors(values, sequence_dim)
                ),
            )
        )
    (first_layers, first_style) = parsed[0]
    del first_layers
    return _rebuild_cache(cache_items[0], output_layers, first_style, sum(lengths))


def concat_kv_caches(
    caches: Iterable[CacheLike], *, sequence_dim: int = -2
) -> CacheLike:
    """Concatenate compatible caches layer by layer with the backend join op."""
    return _concat_kv_caches_impl(caches, sequence_dim=sequence_dim, preallocate=False)


def concat_kv_caches_preallocated(
    caches: Iterable[CacheLike], *, sequence_dim: int = -2
) -> CacheLike:
    """Concatenate layerwise using one output allocation per key/value tensor.

    This is intended for transient query assembly: input views are copied once
    into an independently owned result without constructing per-unit clones.
    """
    return _concat_kv_caches_impl(caches, sequence_dim=sequence_dim, preallocate=True)


def concat_prevalidated_kv_caches(
    caches: Iterable[CacheLike], *, sequence_dim: int = -2
) -> CacheLike:
    """Join model-captured caches after their layout was validated once.

    The adapter validates every unit through byte accounting at capture time.
    This query-only path therefore checks representation and layer count, but
    deliberately avoids rescanning dtype, device and non-sequence dimensions
    for every selected unit and every layer.
    """
    cache_items = tuple(caches)
    if not cache_items:
        raise ValueError("at least one cache is required for concatenation")
    parsed = tuple((_prevalidated_cache_layers(cache) for cache in cache_items))
    layer_count = len(parsed[0][0])
    if layer_count == 0:
        raise ValueError("cache must contain at least one initialized layer")
    if any((len(layers) != layer_count for (layers, _) in parsed)):
        raise ValueError("all caches must contain the same number of layers")
    axis = _normalise_axis(sequence_dim, len(parsed[0][0][0][0].shape))
    lengths = tuple((int(layers[0][0].shape[axis]) for (layers, _) in parsed))
    output_layers: list[LayerKV] = []
    for layer_index in range(layer_count):
        keys = tuple((layers[layer_index][0] for (layers, _) in parsed))
        values = tuple((layers[layer_index][1] for (layers, _) in parsed))
        output_layers.append(
            (
                _preallocate_and_copy_prevalidated_tensors(keys, sequence_dim),
                _preallocate_and_copy_prevalidated_tensors(values, sequence_dim),
            )
        )
    return _rebuild_cache(cache_items[0], output_layers, parsed[0][1], sum(lengths))


def concatenate_kv_caches(
    caches: Iterable[CacheLike], *, sequence_dim: int = -2
) -> CacheLike:
    """Backward-compatible descriptive alias for :func:`concat_kv_caches`."""
    return concat_kv_caches(caches, sequence_dim=sequence_dim)


def _tensor_numel(tensor: Any) -> int:
    numel = getattr(tensor, "numel", None)
    if callable(numel):
        return int(numel())
    return int(reduce(mul, (int(size) for size in tensor.shape), 1))


def _tensor_element_size(tensor: Any) -> int:
    element_size = getattr(tensor, "element_size", None)
    if callable(element_size):
        return int(element_size())
    dtype = getattr(tensor, "dtype", None)
    itemsize = getattr(dtype, "itemsize", None)
    if itemsize is None:
        raise TypeError("cache tensor must expose element_size() or dtype.itemsize")
    return int(itemsize)


def estimate_kv_bytes(cache: CacheLike) -> int:
    """Return the exact tensor payload size, including keys and values.

    For BF16 tensors, PyTorch reports an element size of two bytes; no dtype
    conversion or model-shape assumption is used here.
    """
    (layers, _) = _cache_layers(cache)
    return sum(
        (
            _tensor_numel(tensor) * _tensor_element_size(tensor)
            for layer in layers
            for tensor in layer
        )
    )


def kv_cache_layout_signature(
    cache: CacheLike, *, sequence_dim: int = -2
) -> tuple[Any, ...]:
    """Validate one captured cache and return its device-agnostic layout."""
    (layers, _) = _cache_layers(cache)
    devices: set[str] = set()
    signature: list[Any] = []
    for key, value in layers:
        layer_signature: list[Any] = []
        for tensor in (key, value):
            axis = _normalise_axis(sequence_dim, len(tensor.shape))
            shape = tuple((int(size) for size in tensor.shape))
            devices.add(str(getattr(tensor, "device", None)))
            layer_signature.append(
                (
                    _tensor_backend_name(tensor),
                    str(getattr(tensor, "dtype", None)),
                    shape[:axis] + shape[axis + 1 :],
                )
            )
        signature.append(tuple(layer_signature))
    if len(devices) != 1:
        raise ValueError("all tensors in one captured KV cache must share a device")
    return tuple(signature)


def _validate_rope_table(table: Any, name: str) -> tuple[int, int]:
    if not hasattr(table, "shape") or len(table.shape) != 2:
        raise ValueError(f"{name} must have shape [max_position, rotary_dim]")
    (positions, rotary_dim) = (int(size) for size in table.shape)
    if positions <= 0 or rotary_dim <= 0 or rotary_dim % 2:
        raise ValueError(
            f"{name} must have positive max_position and an even rotary_dim"
        )
    return (positions, rotary_dim)


def _position_rows(table: Any, positions: Sequence[int]) -> Any:
    backend = _tensor_backend_name(table)
    if backend == "torch":
        import torch

        index = torch.tensor(positions, dtype=torch.long, device=table.device)
        return table.index_select(0, index)
    return table[list(positions)]


def _rotate_half(tensor: Any) -> Any:
    half = int(tensor.shape[-1]) // 2
    return _concatenate_tensors(
        (-tensor[..., half:], tensor[..., :half]), sequence_dim=-1
    )


def relocate_rope_keys(
    keys: Any,
    source_positions: Sequence[int],
    target_positions: Sequence[int],
    *,
    cos_table: Any,
    sin_table: Any,
    sequence_dim: int = -2,
) -> Any:
    """Move already-rotated keys from source positions to target positions.

    This applies ``R(target - source)`` to the rotary part of a standard
    half-split RoPE key tensor.  ``cos_table`` and ``sin_table`` must contain the
    same duplicated-frequency layout used by the model and have shape
    ``[max_position, rotary_dim]``.  Non-rotary trailing dimensions are copied.
    """
    if not hasattr(keys, "shape") or len(keys.shape) < 2:
        raise ValueError("keys must be a rank >= 2 tensor")
    axis = _normalise_axis(sequence_dim, len(keys.shape))
    sequence_length = int(keys.shape[axis])
    source = tuple((int(position) for position in source_positions))
    target = tuple((int(position) for position in target_positions))
    if len(source) != sequence_length or len(target) != sequence_length:
        raise ValueError(
            "source_positions and target_positions must match the key sequence length"
        )
    if any((position < 0 for position in source + target)):
        raise ValueError("RoPE positions must be non-negative")
    cos_shape = _validate_rope_table(cos_table, "cos_table")
    sin_shape = _validate_rope_table(sin_table, "sin_table")
    if cos_shape != sin_shape:
        raise ValueError("cos_table and sin_table must have identical shapes")
    (max_position, rotary_dim) = cos_shape
    if source or target:
        greatest_position = max(source + target)
        if greatest_position >= max_position:
            raise ValueError(
                f"RoPE position {greatest_position} exceeds table length {max_position}"
            )
    if rotary_dim > int(keys.shape[-1]):
        raise ValueError("rotary_dim cannot exceed the key head dimension")
    (cos_delta, sin_delta) = _rope_relocation_deltas(
        source, target, cos_table=cos_table, sin_table=sin_table
    )
    return _apply_rope_relocation_deltas(
        keys,
        cos_delta=cos_delta,
        sin_delta=sin_delta,
        rotary_dim=rotary_dim,
        sequence_dim=sequence_dim,
    )


def _rope_relocation_deltas(
    source_positions: Sequence[int],
    target_positions: Sequence[int],
    *,
    cos_table: Any,
    sin_table: Any,
) -> tuple[Any, Any]:
    """Build position-dependent factors once for all cache layers."""
    source_cos = _position_rows(cos_table, source_positions)
    source_sin = _position_rows(sin_table, source_positions)
    target_cos = _position_rows(cos_table, target_positions)
    target_sin = _position_rows(sin_table, target_positions)
    return _rope_relocation_deltas_from_rows(
        source_positions,
        target_positions,
        source_cos=source_cos,
        source_sin=source_sin,
        target_cos=target_cos,
        target_sin=target_sin,
    )


def _rope_relocation_deltas_from_rows(
    source_positions: Sequence[int],
    target_positions: Sequence[int],
    *,
    source_cos: Any,
    source_sin: Any,
    target_cos: Any,
    target_sin: Any,
) -> tuple[Any, Any]:
    expected_rows = len(source_positions)
    row_shapes = {
        tuple((int(size) for size in table.shape))
        for table in (source_cos, source_sin, target_cos, target_sin)
    }
    if len(row_shapes) != 1:
        raise ValueError("source/target RoPE rows must have identical shapes")
    row_shape = next(iter(row_shapes))
    if len(row_shape) != 2 or row_shape[0] != expected_rows:
        raise ValueError(
            "source/target RoPE rows must have shape [sequence_length, rotary_dim]"
        )
    cos_delta = target_cos * source_cos + target_sin * source_sin
    sin_delta = target_sin * source_cos - target_cos * source_sin
    identity_rows = tuple(
        (
            index
            for (index, (source, target)) in enumerate(
                zip(source_positions, target_positions)
            )
            if int(source) == int(target)
        )
    )
    if identity_rows:
        backend = _tensor_backend_name(cos_delta)
        if backend == "torch":
            import torch

            index = torch.tensor(
                identity_rows, dtype=torch.long, device=cos_delta.device
            )
            cos_delta.index_fill_(0, index, 1.0)
            sin_delta.index_fill_(0, index, 0.0)
        elif backend == "numpy":
            cos_delta[list(identity_rows)] = 1.0
            sin_delta[list(identity_rows)] = 0.0
        else:
            raise TypeError(
                f"unsupported RoPE table backend {backend!r}; expected PyTorch or NumPy"
            )
    return (cos_delta, sin_delta)


def _apply_rope_relocation_deltas(
    keys: Any, *, cos_delta: Any, sin_delta: Any, rotary_dim: int, sequence_dim: int
) -> Any:
    """Apply precomputed RoPE position deltas to one cache layer."""
    axis = _normalise_axis(sequence_dim, len(keys.shape))
    sequence_length = int(keys.shape[axis])
    if int(cos_delta.shape[0]) != sequence_length:
        raise ValueError("RoPE delta rows must match the key sequence length")
    if rotary_dim > int(keys.shape[-1]):
        raise ValueError("rotary_dim cannot exceed the key head dimension")
    broadcast_shape = [1] * len(keys.shape)
    broadcast_shape[axis] = sequence_length
    broadcast_shape[-1] = rotary_dim
    cos_delta = _reshape_tensor(cos_delta, broadcast_shape)
    sin_delta = _reshape_tensor(sin_delta, broadcast_shape)
    rotary_keys = keys[..., :rotary_dim]
    cos_delta = _align_tensor_like(cos_delta, rotary_keys)
    sin_delta = _align_tensor_like(sin_delta, rotary_keys)
    moved_rotary = rotary_keys * cos_delta + _rotate_half(rotary_keys) * sin_delta
    if rotary_dim == int(keys.shape[-1]):
        return moved_rotary
    return _concatenate_tensors((moved_rotary, keys[..., rotary_dim:]), sequence_dim=-1)


def relocate_kv_cache_keys(
    cache: CacheLike,
    source_positions: Sequence[int],
    target_positions: Sequence[int],
    *,
    cos_table: Any,
    sin_table: Any,
    sequence_dim: int = -2,
) -> CacheLike:
    """Relocate every selected key with one arbitrary position-map batch.

    The cache is already dense when this function is called.  Physical holes in
    its source timeline are represented only by ``source_positions``; therefore
    the number of RoPE batches is independent of the number of selected spans.
    Values are position-independent and retain their assembled storage.
    """
    (layers, style) = _cache_layers(cache)
    sequence_length = _cache_sequence_length(layers, sequence_dim)
    source = tuple((int(position) for position in source_positions))
    target = tuple((int(position) for position in target_positions))
    if len(source) != sequence_length or len(target) != sequence_length:
        raise ValueError(
            "source_positions and target_positions must match the cache sequence length"
        )
    if any((position < 0 for position in source + target)):
        raise ValueError("RoPE positions must be non-negative")
    cos_shape = _validate_rope_table(cos_table, "cos_table")
    sin_shape = _validate_rope_table(sin_table, "sin_table")
    if cos_shape != sin_shape:
        raise ValueError("cos_table and sin_table must have identical shapes")
    (max_position, rotary_dim) = cos_shape
    if source or target:
        greatest_position = max(source + target)
        if greatest_position >= max_position:
            raise ValueError(
                f"RoPE position {greatest_position} exceeds table length {max_position}"
            )
    (cos_delta, sin_delta) = _rope_relocation_deltas(
        source, target, cos_table=cos_table, sin_table=sin_table
    )
    relocated_layers = tuple(
        (
            (
                _apply_rope_relocation_deltas(
                    key,
                    cos_delta=cos_delta,
                    sin_delta=sin_delta,
                    rotary_dim=rotary_dim,
                    sequence_dim=sequence_dim,
                ),
                value,
            )
            for (key, value) in layers
        )
    )
    return _rebuild_cache(cache, relocated_layers, style, sequence_length)


def relocate_kv_cache_keys_from_position_rows(
    cache: CacheLike,
    source_positions: Sequence[int],
    target_positions: Sequence[int],
    *,
    source_cos: Any,
    source_sin: Any,
    target_cos: Any,
    target_sin: Any,
    sequence_dim: int = -2,
) -> CacheLike:
    """Relocate dense keys from rotary rows gathered only for selected tokens.

    Unlike a full absolute-position table, these four inputs contain exactly one
    row per assembled token.  Runtime and temporary table memory therefore scale
    with selected context length, not with the largest historical timestamp.
    """
    (layers, style) = _cache_layers(cache)
    sequence_length = _cache_sequence_length(layers, sequence_dim)
    source = tuple((int(position) for position in source_positions))
    target = tuple((int(position) for position in target_positions))
    if len(source) != sequence_length or len(target) != sequence_length:
        raise ValueError(
            "source_positions and target_positions must match the cache sequence length"
        )
    if any((position < 0 for position in source + target)):
        raise ValueError("RoPE positions must be non-negative")
    (cos_delta, sin_delta) = _rope_relocation_deltas_from_rows(
        source,
        target,
        source_cos=source_cos,
        source_sin=source_sin,
        target_cos=target_cos,
        target_sin=target_sin,
    )
    rotary_dim = int(cos_delta.shape[-1])
    relocated_layers = tuple(
        (
            (
                _apply_rope_relocation_deltas(
                    key,
                    cos_delta=cos_delta,
                    sin_delta=sin_delta,
                    rotary_dim=rotary_dim,
                    sequence_dim=sequence_dim,
                ),
                value,
            )
            for (key, value) in layers
        )
    )
    return _rebuild_cache(cache, relocated_layers, style, sequence_length)


def _normalise_spans(
    spans: Iterable[UnitKVSpan], *, prefix_length: int, cache_length: int
) -> tuple[UnitKVSpan, ...]:
    by_unit_id: dict[str, UnitKVSpan] = {}
    for span in spans:
        if not isinstance(span, UnitKVSpan):
            raise TypeError("spans must contain UnitKVSpan instances")
        previous = by_unit_id.get(span.unit_id)
        if previous is not None and previous != span:
            raise ValueError(
                f"unit_id {span.unit_id!r} refers to conflicting cache spans"
            )
        by_unit_id[span.unit_id] = span
    ordered = tuple(
        sorted(
            by_unit_id.values(),
            key=lambda item: (
                float(item.timestamp_seconds),
                item.start,
                item.end,
                item.unit_id,
            ),
        )
    )
    for span in ordered:
        if span.start < prefix_length:
            raise ValueError(
                f"unit {span.unit_id!r} overlaps protected prefix [0, {prefix_length})"
            )
        if span.end > cache_length:
            raise ValueError(
                f"unit {span.unit_id!r} ends at {span.end}, beyond cache length {cache_length}"
            )
    source_order = sorted(ordered, key=lambda item: (item.start, item.end))
    for left, right in zip(source_order, source_order[1:]):
        if left.end > right.start:
            raise ValueError(
                f"unit spans {left.unit_id!r} and {right.unit_id!r} overlap"
            )
    return ordered


def assemble_kv_cache(
    source_cache: CacheLike,
    spans: Iterable[UnitKVSpan],
    *,
    prefix_length: int,
    cos_table: Any | None = None,
    sin_table: Any | None = None,
    sequence_dim: int = -2,
) -> AssembledKVCache:
    """Assemble the prefix and deduplicated units in timestamp order.

    When RoPE tables are supplied, relocate each selected key slice to its new
    contiguous positions. Slice and concatenate values without rotation.
    When both tables are omitted, preserve the keys' existing rotary positions.
    """
    if isinstance(prefix_length, bool) or not isinstance(prefix_length, int):
        raise TypeError("prefix_length must be an integer")
    (layers, style) = _cache_layers(source_cache)
    cache_length = _cache_sequence_length(layers, sequence_dim)
    if prefix_length < 0 or prefix_length > cache_length:
        raise ValueError(
            f"prefix_length must be in [0, {cache_length}], got {prefix_length}"
        )
    if (cos_table is None) != (sin_table is None):
        raise ValueError("cos_table and sin_table must be supplied together")
    selected = _normalise_spans(
        spans, prefix_length=prefix_length, cache_length=cache_length
    )
    source_positions = tuple(range(prefix_length)) + tuple(
        (position for span in selected for position in range(span.start, span.end))
    )
    output_length = len(source_positions)
    assembled_layers: list[LayerKV] = []
    for key, value in layers:
        key_parts = [_slice_tensor(key, 0, prefix_length, sequence_dim)]
        value_parts = [_slice_tensor(value, 0, prefix_length, sequence_dim)]
        destination_start = prefix_length
        for span in selected:
            key_part = _slice_tensor(key, span.start, span.end, sequence_dim)
            if cos_table is not None and sin_table is not None:
                key_part = relocate_rope_keys(
                    key_part,
                    range(span.start, span.end),
                    range(destination_start, destination_start + span.token_count),
                    cos_table=cos_table,
                    sin_table=sin_table,
                    sequence_dim=sequence_dim,
                )
            key_parts.append(key_part)
            value_parts.append(_slice_tensor(value, span.start, span.end, sequence_dim))
            destination_start += span.token_count
        assembled_layers.append(
            (
                _concatenate_tensors(key_parts, sequence_dim),
                _concatenate_tensors(value_parts, sequence_dim),
            )
        )
    output_cache = _rebuild_cache(source_cache, assembled_layers, style, output_length)
    return AssembledKVCache(
        cache=output_cache,
        unit_ids=tuple((span.unit_id for span in selected)),
        token_count=output_length,
        estimated_bytes=estimate_kv_bytes(output_cache),
        source_positions=source_positions,
    )


__all__ = [
    "AssembledKVCache",
    "UnitKVSpan",
    "assemble_kv_cache",
    "capture_unit_kv_span",
    "concat_kv_caches",
    "concat_kv_caches_preallocated",
    "concat_prevalidated_kv_caches",
    "concatenate_kv_caches",
    "estimate_kv_bytes",
    "kv_cache_layout_signature",
    "relocate_kv_cache_keys",
    "relocate_kv_cache_keys_from_position_rows",
    "relocate_rope_keys",
    "slice_kv_cache",
]
