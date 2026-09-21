# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Deterministic predictive-cost I/P and KEEP/DROP state machine."""

from __future__ import annotations
import math
from collections.abc import Mapping
from .types import GatingMetrics


def _choose_action(
    *,
    ordinal: int,
    total_candidates: int,
    recent_start: int,
    metric: GatingMetrics | None,
    p_frames_in_gop: int,
    consecutive_drops: int,
    settings: Mapping[str, object],
) -> tuple[str, str, tuple[str, ...], bool, bool]:
    p99_guard = settings["residual_p99_guard"]
    changed_guard = settings["changed_block_fraction_guard"]
    p99_would_block = bool(
        metric is not None and metric.residual_quantile_value > p99_guard["threshold"]
    )
    changed_would_block = bool(
        metric is not None
        and metric.changed_block_fraction > changed_guard["threshold"]
    )
    if ordinal == 0:
        return ("I", "KEEP", ("first_frame",), p99_would_block, changed_would_block)
    if metric is None:
        return ("I", "KEEP", ("frame_size_changed",), False, False)
    if not math.isclose(
        metric.residual_quantile,
        float(p99_guard["quantile"]),
        rel_tol=0.0,
        abs_tol=1e-12,
    ):
        raise ValueError(
            "matching residual quantile does not match the decision guard quantile"
        )
    if metric.pcost > settings["i_frame_pcost_threshold"]:
        return (
            "I",
            "KEEP",
            ("pcost_above_i_threshold",),
            p99_would_block,
            changed_would_block,
        )
    if p_frames_in_gop >= settings["max_p_frames_per_gop"]:
        return (
            "I",
            "KEEP",
            ("max_p_frames_reached",),
            p99_would_block,
            changed_would_block,
        )
    if ordinal >= recent_start:
        return (
            "P",
            "KEEP",
            ("recent_frame_protected",),
            p99_would_block,
            changed_would_block,
        )
    if metric.pcost > settings["skip_pcost_threshold"]:
        return (
            "P",
            "KEEP",
            ("pcost_drop_guard",),
            p99_would_block,
            changed_would_block,
        )
    if p99_guard["enabled"] and p99_would_block:
        reason = (
            "residual_p99_guard"
            if math.isclose(float(p99_guard["quantile"]), 0.99, abs_tol=1e-12)
            else "residual_quantile_guard"
        )
        return ("P", "KEEP", (reason,), p99_would_block, changed_would_block)
    if changed_guard["enabled"] and changed_would_block:
        return (
            "P",
            "KEEP",
            ("changed_block_fraction_guard",),
            p99_would_block,
            changed_would_block,
        )
    if consecutive_drops >= settings["max_consecutive_drops"]:
        return (
            "P",
            "KEEP",
            ("consecutive_drop_limit",),
            p99_would_block,
            changed_would_block,
        )
    return ("P", "DROP", ("hard_drop",), p99_would_block, changed_would_block)


def _settings(config: Mapping[str, object]) -> dict[str, object]:
    required_positive_int = ("max_p_frames_per_gop",)
    settings: dict[str, object] = {}
    for key in required_positive_int:
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(
                f"preencoding_gating.decision.{key} must be a positive integer"
            )
        settings[key] = value
    for key in ("max_consecutive_drops", "protect_recent_frames"):
        value = config.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                f"preencoding_gating.decision.{key} must be a nonnegative integer"
            )
        settings[key] = value
    if config.get("protect_first_frame", True) is not True:
        raise ValueError("preencoding_gating.decision.protect_first_frame must be true")
    for key in ("i_frame_pcost_threshold", "skip_pcost_threshold"):
        value = _nonnegative_number(
            config.get(key), f"preencoding_gating.decision.{key}"
        )
        settings[key] = value
    if settings["skip_pcost_threshold"] > settings["i_frame_pcost_threshold"]:
        raise ValueError("skip_pcost_threshold must not exceed i_frame_pcost_threshold")
    for key in ("residual_p99_guard", "changed_block_fraction_guard"):
        value = config.get(key)
        if not isinstance(value, Mapping) or not isinstance(value.get("enabled"), bool):
            raise ValueError(f"preencoding_gating.decision.{key} must declare enabled")
        settings[key] = {
            "enabled": value["enabled"],
            "threshold": _nonnegative_number(
                value.get("threshold"), f"preencoding_gating.decision.{key}.threshold"
            ),
            **(
                {
                    "quantile": _positive_unit_interval(
                        value.get("quantile", 0.99),
                        f"preencoding_gating.decision.{key}.quantile",
                    )
                }
                if key == "residual_p99_guard"
                else {}
            ),
        }
    return settings


def _unit_interval(value: object, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(value))
        or (value < 0)
        or (value > 1)
    ):
        raise ValueError(f"{path} must be a finite number in [0, 1]")
    return float(value)


def _positive_unit_interval(value: object, path: str) -> float:
    result = _unit_interval(value, path)
    if result <= 0.0:
        raise ValueError(f"{path} must be greater than zero")
    return result


def _nonnegative_number(value: object, path: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(value))
        or (value < 0)
    ):
        raise ValueError(f"{path} must be finite and nonnegative")
    return float(value)
