# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Self-contained predictive-cost matching and online KEEP/DROP decisions."""

from __future__ import annotations
import math
from dataclasses import dataclass
from typing import Literal
import numpy as np

_HEX_DIRECTIONS = ((-2, 0), (-1, -2), (1, -2), (2, 0), (1, 2), (-1, 2))
_LOCAL_DIRECTIONS = tuple(((dx, dy) for dy in (-1, 0, 1) for dx in (-1, 0, 1)))


@dataclass(frozen=True)
class PCostMetrics:
    """Question-independent statistics for one adjacent RGB pair."""

    pcost: float
    residual_mean: float
    residual_p99: float
    changed_block_fraction: float
    motion_mean: float
    block_count: int


@dataclass(frozen=True)
class PCostDecision:
    """State-machine decision recorded when a frame arrives."""

    role: Literal["I", "P"]
    keep_after_hot_window: bool
    reasons: tuple[str, ...]
    metrics: PCostMetrics | None


@dataclass(frozen=True)
class PCostConfig:
    """Matching geometry and decision thresholds for adjacent visual samples."""

    i_threshold: float = 0.1
    skip_threshold: float = 0.04
    residual_p99_guard: float = 0.3
    changed_block_fraction_guard: float = 0.3
    changed_block_residual_threshold: float = 0.03
    motion_penalty_weight: float = 0.01
    max_p_frames_per_gop: int = 32
    max_consecutive_drops: int = 4
    block_size: int = 16
    search_radius_ratio: float = 0.08
    search_radius_min: int = 32
    search_radius_max: int = 96
    analysis_width: int = 512
    analysis_height: int = 512
    residual_quantile: float = 0.99

    def validate(self) -> None:
        if not 0 <= self.skip_threshold <= self.i_threshold:
            raise ValueError("skip_threshold must be between zero and i_threshold")
        for name in (
            "residual_p99_guard",
            "changed_block_fraction_guard",
            "changed_block_residual_threshold",
            "motion_penalty_weight",
        ):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if self.max_p_frames_per_gop <= 0 or self.max_consecutive_drops < 0:
            raise ValueError("invalid GOP/drop limits")
        if self.block_size <= 0:
            raise ValueError("block_size must be positive")
        if self.analysis_width <= 0 or self.analysis_height <= 0:
            raise ValueError("analysis dimensions must be positive")
        if (
            self.analysis_width % self.block_size
            or self.analysis_height % self.block_size
        ):
            raise ValueError("analysis dimensions must be divisible by block_size")
        if not math.isfinite(self.search_radius_ratio) or self.search_radius_ratio < 0:
            raise ValueError("search_radius_ratio must be finite and nonnegative")
        if not 0 < self.search_radius_min <= self.search_radius_max:
            raise ValueError("invalid search-radius bounds")
        if not 0 < self.residual_quantile <= 1:
            raise ValueError("residual_quantile must be in (0, 1]")


class PCostGate:
    """Online PCost state machine; physical deletion is deferred by memory."""

    def __init__(self, config: PCostConfig | None = None) -> None:
        self.config = config or PCostConfig()
        self.config.validate()
        self._p_frames = 0
        self._consecutive_drops = 0
        self._seen = 0

    def decide(self, metrics: PCostMetrics | None) -> PCostDecision:
        """Classify the next frame without deleting recent live state."""
        cfg = self.config
        if self._seen == 0:
            decision = PCostDecision("I", True, ("first_frame",), metrics)
        elif metrics is None:
            decision = PCostDecision("I", True, ("frame_size_changed",), None)
        elif metrics.pcost > cfg.i_threshold:
            decision = PCostDecision("I", True, ("pcost_above_i_threshold",), metrics)
        elif self._p_frames >= cfg.max_p_frames_per_gop:
            decision = PCostDecision("I", True, ("max_p_frames_reached",), metrics)
        elif metrics.pcost > cfg.skip_threshold:
            decision = PCostDecision("I", True, ("pcost_drop_guard",), metrics)
        elif metrics.residual_p99 > cfg.residual_p99_guard:
            decision = PCostDecision("I", True, ("residual_p99_guard",), metrics)
        elif metrics.changed_block_fraction > cfg.changed_block_fraction_guard:
            decision = PCostDecision(
                "I", True, ("changed_block_fraction_guard",), metrics
            )
        elif self._consecutive_drops >= cfg.max_consecutive_drops:
            decision = PCostDecision("I", True, ("consecutive_drop_limit",), metrics)
        else:
            decision = PCostDecision("P", False, ("hard_drop",), metrics)
        self._seen += 1
        if decision.role == "I":
            self._p_frames = 0
            self._consecutive_drops = 0
        else:
            self._p_frames += 1
            self._consecutive_drops = (
                0 if decision.keep_after_hot_window else self._consecutive_drops + 1
            )
        return decision


def match_rgb_pair(
    current: np.ndarray, reference: np.ndarray, config: PCostConfig | None = None
) -> PCostMetrics | None:
    """Compute PCost metrics for two RGB frames on the CPU.

    Return None when frame dimensions differ so the gate retains the current
    frame as an I-frame. The gate also accepts metrics from a CUDA matcher.
    """
    cfg = config or PCostConfig()
    cfg.validate()
    current_rgb = _validate_rgb(current, "current")
    reference_rgb = _validate_rgb(reference, "reference")
    if current_rgb.shape != reference_rgb.shape:
        return None
    current_rgb = _resize_rgb(
        current_rgb, width=cfg.analysis_width, height=cfg.analysis_height
    )
    reference_rgb = _resize_rgb(
        reference_rgb, width=cfg.analysis_width, height=cfg.analysis_height
    )
    appearances: list[float] = []
    motions: list[float] = []
    (height, width, _) = current_rgb.shape
    current_i16 = current_rgb.astype(np.int16, copy=False)
    reference_i16 = reference_rgb.astype(np.int16, copy=False)
    for y in range(0, height, cfg.block_size):
        for x in range(0, width, cfg.block_size):
            (appearance, motion) = _match_block(
                current_i16,
                reference_i16,
                x=x,
                y=y,
                size=cfg.block_size,
                radius=min(
                    _search_radius(cfg),
                    min(cfg.analysis_width, cfg.analysis_height) - cfg.block_size,
                ),
                motion_weight=cfg.motion_penalty_weight,
            )
            appearances.append(appearance)
            motions.append(motion)
    residual = np.asarray(appearances, dtype=np.float64)
    motion = np.asarray(motions, dtype=np.float64)
    residual_mean = float(residual.mean())
    motion_mean = float(motion.mean())
    return PCostMetrics(
        pcost=residual_mean + cfg.motion_penalty_weight * motion_mean,
        residual_mean=residual_mean,
        residual_p99=float(
            np.quantile(residual, cfg.residual_quantile, method="higher")
        ),
        changed_block_fraction=float(
            np.mean(residual > cfg.changed_block_residual_threshold)
        ),
        motion_mean=motion_mean,
        block_count=int(residual.size),
    )


def _match_block(
    current: np.ndarray,
    reference: np.ndarray,
    *,
    x: int,
    y: int,
    size: int,
    radius: int,
    motion_weight: float,
) -> tuple[float, float]:
    (frame_height, frame_width, _) = current.shape
    width = min(size, frame_width - x)
    height = min(size, frame_height - y)
    (dx_min, dx_max) = (max(-radius, -x), min(radius, frame_width - x - width))
    (dy_min, dy_max) = (max(-radius, -y), min(radius, frame_height - y - height))
    block = current[y : y + height, x : x + width]
    denominator = float(255 * 3 * width * height)
    cache: dict[tuple[int, int], tuple[tuple[float, int, int, int], float, float]] = {}

    def evaluate(dx: int, dy: int):
        cached = cache.get((dx, dy))
        if cached is not None:
            return cached
        candidate = reference[y + dy : y + dy + height, x + dx : x + dx + width]
        appearance = float(np.abs(block - candidate).sum(dtype=np.int64)) / denominator
        motion = (abs(dx) + abs(dy)) / float(2 * radius)
        score = appearance + motion_weight * motion
        result = ((score, abs(dx) + abs(dy), dy, dx), appearance, motion)
        cache[dx, dy] = result
        return result

    center = (0, 0)
    if evaluate(*center)[0][0] != 0:
        for _ in range(2 * radius + 4):
            candidates = [center]
            candidates.extend(
                (
                    (center[0] + dx, center[1] + dy)
                    for (dx, dy) in _HEX_DIRECTIONS
                    if dx_min <= center[0] + dx <= dx_max
                    and dy_min <= center[1] + dy <= dy_max
                )
            )
            best = min(candidates, key=lambda item: evaluate(*item)[0])
            if best == center:
                break
            center = best
    local = [
        (center[0] + dx, center[1] + dy)
        for (dx, dy) in _LOCAL_DIRECTIONS
        if dx_min <= center[0] + dx <= dx_max and dy_min <= center[1] + dy <= dy_max
    ]
    best = min(local, key=lambda item: evaluate(*item)[0])
    (_, appearance, motion) = evaluate(*best)
    return (appearance, motion)


def _search_radius(config: PCostConfig) -> int:
    """Return the block-aligned radius derived from the resized short edge."""
    short_edge = min(config.analysis_width, config.analysis_height)
    radius = (
        math.ceil(config.search_radius_ratio * short_edge / config.block_size)
        * config.block_size
    )
    return min(max(radius, config.search_radius_min), config.search_radius_max)


def _resize_rgb(frame: np.ndarray, *, width: int, height: int) -> np.ndarray:
    """Resize one RGB array to the configured matching canvas."""
    if frame.shape[:2] == (height, width):
        return np.ascontiguousarray(frame)
    try:
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("PCost RGB resizing requires Pillow") from error
    return np.ascontiguousarray(
        np.asarray(
            Image.fromarray(frame).resize((width, height), Image.Resampling.BICUBIC)
        )
    )


def _validate_rgb(frame: np.ndarray, name: str) -> np.ndarray:
    value = np.asarray(frame)
    if value.dtype != np.uint8 or value.ndim != 3 or value.shape[-1] != 3:
        raise ValueError(f"{name} must be an HxWx3 uint8 RGB array")
    if not value.shape[0] or not value.shape[1]:
        raise ValueError(f"{name} must be non-empty")
    return value
