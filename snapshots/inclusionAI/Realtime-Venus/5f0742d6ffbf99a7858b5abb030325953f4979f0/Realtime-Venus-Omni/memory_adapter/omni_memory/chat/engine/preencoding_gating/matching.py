# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""512x512 analysis-RGB block matching for predictive-cost gating."""

from __future__ import annotations
import math
from collections.abc import Mapping, Sequence
import numpy as np
import torch
from .types import GatingMetrics

_HEX_DIRECTIONS = ((-2, 0), (-1, -2), (1, -2), (2, 0), (1, 2), (-1, 2))
_LOCAL_DIRECTIONS = tuple(((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)))


def match_rgb_pair(
    current: np.ndarray, reference: np.ndarray, matching: Mapping[str, object]
) -> GatingMetrics:
    """Return predictive-cost statistics for two aligned uint8 RGB frames."""
    return match_rgb_pairs(((current, reference),), matching)[0]


def match_rgb_pairs(
    pairs: Sequence[tuple[np.ndarray, np.ndarray]], matching: Mapping[str, object]
) -> tuple[GatingMetrics, ...]:
    """Match adjacent pairs and return the aggregate statistics used by gating."""
    aligned = tuple(pairs)
    if not aligned:
        return ()
    prepared = _prepare_matching_pairs(aligned, matching)
    backend = matching.get("backend")
    if backend in {"torch_cuda", "triton_cuda"}:
        results: list[GatingMetrics] = []
        pair_batch_size = _positive_int(
            matching.get("pair_batch_size", 1), "matching.pair_batch_size"
        )
        for offset in range(0, len(prepared), pair_batch_size):
            batch = prepared[offset : offset + pair_batch_size]
            for group in _group_pairs_by_geometry(batch):
                matcher = (
                    _match_rgb_pairs_triton
                    if backend == "triton_cuda"
                    else _match_rgb_pairs_torch
                )
                results.extend(matcher(group, matching))
        return tuple(results)
    if backend != "numpy_cpu":
        raise ValueError(
            "preencoding_gating.matching.backend must be numpy_cpu, torch_cuda, or triton_cuda"
        )
    return tuple(
        _match_rgb_pair_numpy_detailed(current, reference, matching)
        for current, reference in prepared
    )


def _prepare_matching_pairs(
    pairs: Sequence[tuple[np.ndarray, np.ndarray]], matching: Mapping[str, object]
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    """Resize only the matching branch while retaining original RGB elsewhere."""
    resize = matching.get("input_resize")
    if not isinstance(resize, Mapping):
        raise ValueError("matching.input_resize must be a mapping")
    if (
        resize.get("enabled") is not True
        or resize.get("width") != 512
        or resize.get("height") != 512
        or (resize.get("mode") != "stretch")
        or (resize.get("interpolation") != "bicubic")
    ):
        raise ValueError(
            "matching.input_resize must select enabled 512x512 stretch bicubic"
        )
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError(
            "512x512 predictive-cost matching requires Pillow"
        ) from error
    resized_by_identity: dict[int, np.ndarray] = {}

    def resized(frame: np.ndarray, name: str) -> np.ndarray:
        rgb = _validate_rgb(frame, name)
        cached = resized_by_identity.get(id(rgb))
        if cached is not None:
            return cached
        if rgb.shape[:2] == (512, 512):
            result = np.ascontiguousarray(rgb)
        else:
            result = np.ascontiguousarray(
                np.asarray(
                    Image.fromarray(rgb).resize(
                        (512, 512), resample=Image.Resampling.BICUBIC
                    )
                )
            )
        if result.dtype != np.uint8 or result.shape != (512, 512, 3):
            raise RuntimeError("matching resize did not produce uint8 512x512 RGB")
        resized_by_identity[id(rgb)] = result
        return result

    prepared: list[tuple[np.ndarray, np.ndarray]] = []
    for current, reference in pairs:
        current_rgb = _validate_rgb(current, "current")
        reference_rgb = _validate_rgb(reference, "reference")
        if current_rgb.shape != reference_rgb.shape:
            raise ValueError(
                "current and reference RGB frames must have identical shape"
            )
        prepared.append(
            (resized(current_rgb, "current"), resized(reference_rgb, "reference"))
        )
    return tuple(prepared)


def _group_pairs_by_geometry(
    pairs: Sequence[tuple[np.ndarray, np.ndarray]],
) -> tuple[tuple[tuple[np.ndarray, np.ndarray], ...], ...]:
    """Validate and split a batch at RGB geometry boundaries."""
    groups: list[list[tuple[np.ndarray, np.ndarray]]] = []
    for pair in pairs:
        current_rgb = _validate_rgb(pair[0], "current")
        reference_rgb = _validate_rgb(pair[1], "reference")
        if current_rgb.shape != reference_rgb.shape:
            raise ValueError(
                "current and reference RGB frames must have identical shape"
            )
        if not groups or groups[-1][0][0].shape != current_rgb.shape:
            groups.append([])
        groups[-1].append((current_rgb, reference_rgb))
    return tuple((tuple(group) for group in groups))


def _match_rgb_pair_numpy_detailed(
    current: np.ndarray, reference: np.ndarray, matching: Mapping[str, object]
) -> GatingMetrics:
    """Run one NumPy reference match."""
    current_rgb = _validate_rgb(current, "current")
    reference_rgb = _validate_rgb(reference, "reference")
    if current_rgb.shape != reference_rgb.shape:
        raise ValueError("current and reference RGB frames must have identical shape")
    block_size = _positive_int(matching.get("block_size"), "matching.block_size")
    if block_size != 16:
        raise ValueError("predictive-cost matching requires block_size=16")
    ratio = _positive_number(matching.get("search_radius_ratio"), "search_radius_ratio")
    radius = _search_radius(
        current_rgb.shape[0],
        current_rgb.shape[1],
        ratio=ratio,
        minimum=_positive_int(matching.get("search_radius_min"), "search_radius_min"),
        maximum=_positive_int(matching.get("search_radius_max"), "search_radius_max"),
        alignment=block_size,
    )
    motion_weight = _nonnegative_number(
        matching.get("motion_penalty_weight"), "motion_penalty_weight"
    )
    changed_threshold = _nonnegative_number(
        matching.get("changed_block_residual_threshold"),
        "changed_block_residual_threshold",
    )
    residual_quantile = _positive_unit_interval(
        matching.get("residual_quantile", 0.99), "residual_quantile"
    )
    current_i16 = current_rgb.astype(np.int16, copy=False)
    reference_i16 = reference_rgb.astype(np.int16, copy=False)
    appearances: list[float] = []
    motions: list[float] = []
    candidates: list[float] = []
    areas: list[int] = []
    height, width, _ = current_i16.shape
    for y in range(0, height, block_size):
        block_height = min(block_size, height - y)
        for x in range(0, width, block_size):
            block_width = min(block_size, width - x)
            appearance, motion, candidate, dx, dy = _match_block(
                current_i16,
                reference_i16,
                x=x,
                y=y,
                width=block_width,
                height=block_height,
                radius=radius,
                motion_weight=motion_weight,
            )
            appearances.append(appearance)
            motions.append(motion)
            candidates.append(candidate)
            areas.append(block_width * block_height)
    weights = np.asarray(areas, dtype=np.float64)
    appearance_values = np.asarray(appearances, dtype=np.float64)
    motion_values = np.asarray(motions, dtype=np.float64)
    candidate_values = np.asarray(candidates, dtype=np.float64)
    total_area = float(weights.sum())
    residual_mean = float(np.dot(weights, appearance_values) / total_area)
    motion_mean = float(np.dot(weights, motion_values) / total_area)
    pcost = float(np.dot(weights, candidate_values) / total_area)
    if not math.isclose(
        pcost, residual_mean + motion_weight * motion_mean, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise RuntimeError("PCost aggregation invariant failed")
    return GatingMetrics(
        search_radius=radius,
        pcost=pcost,
        residual_mean=residual_mean,
        residual_p99=_weighted_nearest_rank(
            appearance_values, weights, residual_quantile
        ),
        residual_max=float(appearance_values.max(initial=0.0)),
        changed_block_fraction=float(
            weights[appearance_values > changed_threshold].sum() / total_area
        ),
        motion_mean=motion_mean,
        block_count=len(areas),
        residual_quantile=residual_quantile,
    )


def _match_rgb_pairs_torch(
    pairs: Sequence[tuple[np.ndarray, np.ndarray]], matching: Mapping[str, object]
) -> tuple[GatingMetrics, ...]:
    """Run the CPU-reference search on the already-resized analysis RGB.

    The implementation evaluates each block's independent hexagonal search
    centre in bounded block batches.  Integer SAD is accumulated before the
    float64 normalization, and the staged argmin implements the reference
    tie-break ``cost -> L1 motion -> dy -> dx`` exactly.
    """
    aligned = tuple(pairs)
    if not aligned:
        return ()
    current_frames = tuple((_validate_rgb(pair[0], "current") for pair in aligned))
    reference_frames = tuple((_validate_rgb(pair[1], "reference") for pair in aligned))
    shape = current_frames[0].shape
    if any(
        (
            current.shape != reference.shape or current.shape != shape
            for current, reference in zip(current_frames, reference_frames, strict=True)
        )
    ):
        raise ValueError("one CUDA pair batch must use one identical RGB geometry")
    if not torch.cuda.is_available():
        raise RuntimeError(
            "preencoding_gating.matching.backend=torch_cuda requires an available CUDA device"
        )
    block_size = _positive_int(matching.get("block_size"), "matching.block_size")
    if block_size != 16:
        raise ValueError("predictive-cost matching requires block_size=16")
    ratio = _positive_number(
        matching.get("search_radius_ratio"), "matching.search_radius_ratio"
    )
    radius = _search_radius(
        shape[0],
        shape[1],
        ratio=ratio,
        minimum=_positive_int(
            matching.get("search_radius_min"), "matching.search_radius_min"
        ),
        maximum=_positive_int(
            matching.get("search_radius_max"), "matching.search_radius_max"
        ),
        alignment=block_size,
    )
    motion_weight = _nonnegative_number(
        matching.get("motion_penalty_weight"), "matching.motion_penalty_weight"
    )
    changed_threshold = _nonnegative_number(
        matching.get("changed_block_residual_threshold"),
        "matching.changed_block_residual_threshold",
    )
    residual_quantile = _positive_unit_interval(
        matching.get("residual_quantile", 0.99), "matching.residual_quantile"
    )
    block_batch_size = _positive_int(
        matching.get("block_batch_size", 256), "matching.block_batch_size"
    )
    device = torch.device("cuda", torch.cuda.current_device())
    current_gpu = torch.from_numpy(
        np.stack([np.ascontiguousarray(frame) for frame in current_frames])
    ).to(device)
    reference_gpu = torch.from_numpy(
        np.stack([np.ascontiguousarray(frame) for frame in reference_frames])
    ).to(device)
    current_i16 = current_gpu.to(torch.int16)
    reference_i16 = reference_gpu.to(torch.int16)
    _, height, width, _ = current_gpu.shape
    grouped_origins: dict[tuple[int, int], list[tuple[int, int, int]]] = {}
    for y in range(0, height, block_size):
        for x in range(0, width, block_size):
            shape = (min(block_size, height - y), min(block_size, width - x))
            for pair_index in range(len(aligned)):
                grouped_origins.setdefault(shape, []).append((pair_index, x, y))
    appearances: list[torch.Tensor] = []
    motions: list[torch.Tensor] = []
    candidates: list[torch.Tensor] = []
    areas: list[torch.Tensor] = []
    pair_id_chunks: list[torch.Tensor] = []
    for (block_height, block_width), origins in grouped_origins.items():
        offset = 0
        effective_block_batch_size = min(block_batch_size, len(origins))
        while offset < len(origins):
            chunk = origins[offset : offset + effective_block_batch_size]
            pair_ids = torch.tensor([item[0] for item in chunk], device=device)
            xs = torch.tensor([item[1] for item in chunk], device=device)
            ys = torch.tensor([item[2] for item in chunk], device=device)
            try:
                appearance, motion, candidate = _match_block_batch_torch(
                    current_i16,
                    reference_i16,
                    pair_ids=pair_ids,
                    xs=xs,
                    ys=ys,
                    block_width=block_width,
                    block_height=block_height,
                    radius=radius,
                    motion_weight=motion_weight,
                )
            except torch.cuda.OutOfMemoryError:
                del pair_ids, xs, ys
                if effective_block_batch_size <= 1:
                    raise
                torch.cuda.empty_cache()
                effective_block_batch_size = max(1, effective_block_batch_size // 2)
                continue
            appearances.append(appearance)
            motions.append(motion)
            candidates.append(candidate)
            areas.append(
                torch.full(
                    (len(chunk),),
                    block_width * block_height,
                    device=device,
                    dtype=torch.float64,
                )
            )
            pair_id_chunks.append(pair_ids)
            offset += len(chunk)
    appearance_values = torch.cat(appearances)
    motion_values = torch.cat(motions)
    candidate_values = torch.cat(candidates)
    weights = torch.cat(areas)
    flattened_pair_ids = torch.cat(pair_id_chunks)
    per_pair_values: list[tuple[torch.Tensor, ...]] = []
    for pair_index in range(len(aligned)):
        mask = flattened_pair_ids == pair_index
        pair_weights = weights[mask]
        pair_appearance = appearance_values[mask]
        pair_motion = motion_values[mask]
        pair_candidate = candidate_values[mask]
        total_area = pair_weights.sum()
        residual_mean = torch.dot(pair_weights, pair_appearance) / total_area
        motion_mean = torch.dot(pair_weights, pair_motion) / total_area
        pcost = torch.dot(pair_weights, pair_candidate) / total_area
        expected = residual_mean + motion_weight * motion_mean
        if not torch.isclose(pcost, expected, rtol=1e-12, atol=1e-12):
            raise RuntimeError("CUDA PCost aggregation invariant failed")
        residual_value = _weighted_nearest_rank_torch(
            pair_appearance, pair_weights, residual_quantile
        )
        changed_fraction = (
            pair_weights[pair_appearance > changed_threshold].sum() / total_area
        )
        per_pair_values.append(
            (
                pcost,
                residual_mean,
                residual_value,
                pair_appearance.max(),
                changed_fraction,
                motion_mean,
                mask.sum(),
            )
        )
    return tuple(
        (
            GatingMetrics(
                search_radius=radius,
                pcost=float(values[0].item()),
                residual_mean=float(values[1].item()),
                residual_p99=float(values[2].item()),
                residual_max=float(values[3].item()),
                changed_block_fraction=float(values[4].item()),
                motion_mean=float(values[5].item()),
                block_count=int(values[6].item()),
                residual_quantile=residual_quantile,
            )
            for values in per_pair_values
        )
    )


def _match_rgb_pairs_triton(
    pairs: Sequence[tuple[np.ndarray, np.ndarray]], matching: Mapping[str, object]
) -> tuple[GatingMetrics, ...]:
    """Run one fused, independently converging GPU program per 16x16 block."""
    aligned = tuple(pairs)
    if not aligned:
        return ()
    current_frames = tuple((_validate_rgb(pair[0], "current") for pair in aligned))
    reference_frames = tuple((_validate_rgb(pair[1], "reference") for pair in aligned))
    if any(
        (
            current.shape != (512, 512, 3) or reference.shape != current.shape
            for current, reference in zip(current_frames, reference_frames, strict=True)
        )
    ):
        raise ValueError("Triton matching requires resized 512x512 RGB pairs")
    if not torch.cuda.is_available():
        raise RuntimeError(
            "preencoding_gating.matching.backend=triton_cuda requires an available CUDA device"
        )
    block_size = _positive_int(matching.get("block_size"), "matching.block_size")
    if block_size != 16:
        raise ValueError("predictive-cost matching requires block_size=16")
    radius = _search_radius(
        512,
        512,
        ratio=_positive_number(
            matching.get("search_radius_ratio"), "matching.search_radius_ratio"
        ),
        minimum=_positive_int(
            matching.get("search_radius_min"), "matching.search_radius_min"
        ),
        maximum=_positive_int(
            matching.get("search_radius_max"), "matching.search_radius_max"
        ),
        alignment=block_size,
    )
    motion_weight = _nonnegative_number(
        matching.get("motion_penalty_weight"), "matching.motion_penalty_weight"
    )
    changed_threshold = _nonnegative_number(
        matching.get("changed_block_residual_threshold"),
        "matching.changed_block_residual_threshold",
    )
    residual_quantile = _positive_unit_interval(
        matching.get("residual_quantile", 0.99), "matching.residual_quantile"
    )
    program_batch_size = _positive_int(
        matching.get("block_batch_size", 8192), "matching.block_batch_size"
    )
    device = torch.device("cuda", torch.cuda.current_device())
    current_gpu = torch.from_numpy(
        np.stack([np.ascontiguousarray(frame) for frame in current_frames])
    ).to(device)
    reference_gpu = torch.from_numpy(
        np.stack([np.ascontiguousarray(frame) for frame in reference_frames])
    ).to(device)
    from .triton_matching import fused_hex_search_512

    appearance, motion, candidate = fused_hex_search_512(
        current_gpu,
        reference_gpu,
        radius=radius,
        motion_weight=motion_weight,
        program_batch_size=program_batch_size,
    )
    pair_count = len(aligned)
    blocks_per_pair = 32 * 32
    appearance = appearance.reshape(pair_count, blocks_per_pair)
    motion = motion.reshape(pair_count, blocks_per_pair)
    candidate = candidate.reshape(pair_count, blocks_per_pair)
    weights = torch.full(
        (blocks_per_pair,), 16 * 16, device=device, dtype=torch.float64
    )
    total_area = weights.sum()
    values_by_pair: list[tuple[torch.Tensor, ...]] = []
    for pair_index in range(pair_count):
        pair_appearance = appearance[pair_index]
        pair_motion = motion[pair_index]
        pair_candidate = candidate[pair_index]
        residual_mean = torch.dot(weights, pair_appearance) / total_area
        motion_mean = torch.dot(weights, pair_motion) / total_area
        pcost = torch.dot(weights, pair_candidate) / total_area
        expected = residual_mean + motion_weight * motion_mean
        if not torch.isclose(pcost, expected, rtol=1e-12, atol=1e-12):
            raise RuntimeError("Triton PCost aggregation invariant failed")
        residual_value = _weighted_nearest_rank_torch(
            pair_appearance, weights, residual_quantile
        )
        changed_fraction = (
            weights[pair_appearance > changed_threshold].sum() / total_area
        )
        values_by_pair.append(
            (
                pcost,
                residual_mean,
                residual_value,
                pair_appearance.max(),
                changed_fraction,
                motion_mean,
            )
        )
    return tuple(
        (
            GatingMetrics(
                search_radius=radius,
                pcost=float(values[0].item()),
                residual_mean=float(values[1].item()),
                residual_p99=float(values[2].item()),
                residual_max=float(values[3].item()),
                changed_block_fraction=float(values[4].item()),
                motion_mean=float(values[5].item()),
                block_count=blocks_per_pair,
                residual_quantile=residual_quantile,
            )
            for values in values_by_pair
        )
    )


def _match_block_batch_torch(
    current: torch.Tensor,
    reference: torch.Tensor,
    *,
    pair_ids: torch.Tensor,
    xs: torch.Tensor,
    ys: torch.Tensor,
    block_width: int,
    block_height: int,
    radius: int,
    motion_weight: float,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Return matched appearance, normalized motion, and cost for one block batch."""
    batch_size = int(xs.numel())
    device = current.device
    _, frame_height, frame_width, _ = current.shape
    rows = torch.arange(block_height, device=device)
    columns = torch.arange(block_width, device=device)
    current_values = current[
        pair_ids[:, None, None],
        ys[:, None, None] + rows[None, :, None],
        xs[:, None, None] + columns[None, None, :],
    ]
    centers_dx = torch.zeros(batch_size, device=device, dtype=torch.long)
    centers_dy = torch.zeros(batch_size, device=device, dtype=torch.long)
    hex_offsets = torch.tensor(
        ((0, 0), *_HEX_DIRECTIONS), device=device, dtype=torch.long
    )
    for _ in range(2 * radius + 4):
        cost, _, _, dx, dy = _evaluate_offsets_torch(
            current_values,
            reference,
            pair_ids=pair_ids,
            xs=xs,
            ys=ys,
            block_width=block_width,
            block_height=block_height,
            center_dx=centers_dx,
            center_dy=centers_dy,
            offsets=hex_offsets,
            radius=radius,
            motion_weight=motion_weight,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        best = _lexicographic_argmin_torch(cost, dx, dy)
        next_dx = dx.gather(1, best[:, None]).squeeze(1)
        next_dy = dy.gather(1, best[:, None]).squeeze(1)
        if not bool(((next_dx != centers_dx) | (next_dy != centers_dy)).any().item()):
            break
        centers_dx = next_dx
        centers_dy = next_dy
    local_offsets = torch.tensor(_LOCAL_DIRECTIONS, device=device, dtype=torch.long)
    cost, appearance, motion, dx, dy = _evaluate_offsets_torch(
        current_values,
        reference,
        pair_ids=pair_ids,
        xs=xs,
        ys=ys,
        block_width=block_width,
        block_height=block_height,
        center_dx=centers_dx,
        center_dy=centers_dy,
        offsets=local_offsets,
        radius=radius,
        motion_weight=motion_weight,
        frame_width=frame_width,
        frame_height=frame_height,
    )
    best = _lexicographic_argmin_torch(cost, dx, dy)
    return (
        appearance.gather(1, best[:, None]).squeeze(1),
        motion.gather(1, best[:, None]).squeeze(1),
        cost.gather(1, best[:, None]).squeeze(1),
    )


def _evaluate_offsets_torch(
    current_values: torch.Tensor,
    reference: torch.Tensor,
    *,
    pair_ids: torch.Tensor,
    xs: torch.Tensor,
    ys: torch.Tensor,
    block_width: int,
    block_height: int,
    center_dx: torch.Tensor,
    center_dy: torch.Tensor,
    offsets: torch.Tensor,
    radius: int,
    motion_weight: float,
    frame_width: int,
    frame_height: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Evaluate a fixed offset set with invalid reference positions masked out."""
    dx = center_dx[:, None] + offsets[None, :, 0]
    dy = center_dy[:, None] + offsets[None, :, 1]
    valid = (
        (dx >= -xs[:, None])
        & (dx <= frame_width - (xs[:, None] + block_width))
        & (dy >= -ys[:, None])
        & (dy <= frame_height - (ys[:, None] + block_height))
    )
    rows = torch.arange(block_height, device=reference.device)
    columns = torch.arange(block_width, device=reference.device)
    reference_y = (
        ys[:, None, None, None] + dy[:, :, None, None] + rows[None, None, :, None]
    ).clamp_(0, frame_height - 1)
    reference_x = (
        xs[:, None, None, None] + dx[:, :, None, None] + columns[None, None, None, :]
    ).clamp_(0, frame_width - 1)
    reference_values = reference[
        pair_ids[:, None, None, None], reference_y, reference_x
    ]
    sad = torch.abs(reference_values - current_values[:, None]).sum(
        dim=(2, 3, 4), dtype=torch.int64
    )
    denominator = float(255 * 3 * block_width * block_height)
    appearance = sad.to(torch.float64) / denominator
    motion_l1 = dx.abs() + dy.abs()
    motion = motion_l1.to(torch.float64) / float(2 * radius)
    cost = appearance + motion_weight * motion
    cost = torch.where(valid, cost, torch.full_like(cost, float("inf")))
    return (cost, appearance, motion, dx, dy)


def _lexicographic_argmin_torch(
    cost: torch.Tensor, dx: torch.Tensor, dy: torch.Tensor
) -> torch.Tensor:
    """Select per-row by the exact CPU reference tie-break order."""
    minimum_cost = cost.min(dim=1, keepdim=True).values
    mask = cost == minimum_cost
    motion_l1 = dx.abs() + dy.abs()
    max_int = torch.iinfo(torch.long).max
    minimum_motion = (
        torch.where(mask, motion_l1, max_int).min(dim=1, keepdim=True).values
    )
    mask &= motion_l1 == minimum_motion
    minimum_dy = torch.where(mask, dy, max_int).min(dim=1, keepdim=True).values
    mask &= dy == minimum_dy
    minimum_dx = torch.where(mask, dx, max_int).min(dim=1, keepdim=True).values
    mask &= dx == minimum_dx
    indices = torch.arange(cost.shape[1], device=cost.device).expand_as(cost)
    return torch.where(mask, indices, cost.shape[1]).min(dim=1).values


def _weighted_nearest_rank_torch(
    values: torch.Tensor, weights: torch.Tensor, quantile: float
) -> torch.Tensor:
    order = torch.argsort(values, stable=True)
    sorted_weights = weights.index_select(0, order)
    cumulative = torch.cumsum(sorted_weights, dim=0)
    position = quantile * cumulative[-1]
    index = torch.searchsorted(cumulative, position, right=False)
    return values.index_select(0, order).index_select(0, index.reshape(1))[0]


def _match_block(
    current: np.ndarray,
    reference: np.ndarray,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
    radius: int,
    motion_weight: float,
) -> tuple[float, float, float, int, int]:
    frame_height, frame_width, _ = current.shape
    dx_min = max(-radius, -x)
    dx_max = min(radius, frame_width - (x + width))
    dy_min = max(-radius, -y)
    dy_max = min(radius, frame_height - (y + height))
    current_block = current[y : y + height, x : x + width]
    denominator = float(255 * 3 * width * height)
    cache: dict[tuple[int, int], tuple[tuple[float, int, int, int], float, float]] = {}

    def evaluate(dx: int, dy: int) -> tuple[tuple[float, int, int, int], float, float]:
        cached = cache.get((dx, dy))
        if cached is not None:
            return cached
        reference_block = reference[y + dy : y + dy + height, x + dx : x + dx + width]
        appearance = float(np.abs(current_block - reference_block).sum(dtype=np.int64))
        appearance /= denominator
        motion = (abs(dx) + abs(dy)) / float(2 * radius)
        candidate = appearance + motion_weight * motion
        result = ((candidate, abs(dx) + abs(dy), dy, dx), appearance, motion)
        cache[dx, dy] = result
        return result

    center = (0, 0)
    if evaluate(*center)[0][0] != 0.0:
        for _ in range(2 * radius + 4):
            candidates = [center]
            candidates.extend(
                (
                    (center[0] + dx, center[1] + dy)
                    for dx, dy in _HEX_DIRECTIONS
                    if dx_min <= center[0] + dx <= dx_max
                    and dy_min <= center[1] + dy <= dy_max
                )
            )
            best = min(candidates, key=lambda offset: evaluate(*offset)[0])
            if best == center:
                break
            center = best
    local = [
        (center[0] + dx, center[1] + dy)
        for dx, dy in _LOCAL_DIRECTIONS
        if dx_min <= center[0] + dx <= dx_max and dy_min <= center[1] + dy <= dy_max
    ]
    best_dx, best_dy = min(local, key=lambda offset: evaluate(*offset)[0])
    key, appearance, motion = evaluate(best_dx, best_dy)
    return (appearance, motion, key[0], best_dx, best_dy)


def _search_radius(
    height: int, width: int, *, ratio: float, minimum: int, maximum: int, alignment: int
) -> int:
    if height <= 0 or width <= 0 or maximum < minimum:
        raise ValueError("invalid frame geometry or search-radius bounds")
    raw = ratio * min(height, width)
    return min(max(math.ceil(raw / alignment) * alignment, minimum), maximum)


def _weighted_nearest_rank(
    values: np.ndarray, weights: np.ndarray, quantile: float
) -> float:
    order = np.argsort(values, kind="stable")
    cumulative = np.cumsum(weights[order], dtype=np.float64)
    index = int(
        np.searchsorted(cumulative, quantile * float(cumulative[-1]), side="left")
    )
    return float(values[order][min(index, len(values) - 1)])


def _validate_rgb(value: np.ndarray, name: str) -> np.ndarray:
    frame = np.asarray(value)
    if frame.dtype != np.uint8 or frame.ndim != 3 or frame.shape[-1] != 3:
        raise ValueError(f"{name} must be uint8 RGB with shape [H,W,3]")
    if frame.shape[0] <= 0 or frame.shape[1] <= 0:
        raise ValueError(f"{name} frame cannot be empty")
    return frame


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _positive_number(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(value))
        or (value <= 0)
    ):
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _nonnegative_number(value: object, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(value))
        or (value < 0)
    ):
        raise ValueError(f"{name} must be finite and nonnegative")
    return float(value)


def _unit_interval(value: object, name: str) -> float:
    result = _nonnegative_number(value, name)
    if result > 1.0:
        raise ValueError(f"{name} must be at most one")
    return result


def _positive_unit_interval(value: object, name: str) -> float:
    result = _unit_interval(value, name)
    if result <= 0.0:
        raise ValueError(f"{name} must be greater than zero")
    return result
