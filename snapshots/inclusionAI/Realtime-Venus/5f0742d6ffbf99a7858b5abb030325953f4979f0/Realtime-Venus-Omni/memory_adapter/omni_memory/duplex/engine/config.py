# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Serializable configuration for the Realtime-Venus-Omni retrieval runtime."""

from __future__ import annotations
import math
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Mapping
from ..._engine_config import DEFAULT_SYSTEM_PROMPT

OFFLINE_MODE = "offline_embedding_retrieval"
ONLINE_MODE = "online_duplex_kv_retrieval"
INFERENCE_MODES = (OFFLINE_MODE, ONLINE_MODE)
OUTPUT_LANGUAGES = ("auto", "zh", "en")


@dataclass(frozen=True)
class RuntimeConfig:
    """Resolved settings for the attached Duplex memory runtime."""

    inference_mode: str = OFFLINE_MODE
    use_memory: bool = True
    ref_audio_path: Path | None = None
    device: str = "cuda:0"
    seed: int = 42
    generate_audio: bool = True
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    output_language: str = "auto"
    max_new_tokens: int = 6
    decode_mode: str = "sampling"
    chunk_seconds: float = 1.0
    online_context_seconds: float = 120.0
    retrieval_recent_seconds: float = 4.0
    candidate_pool_size: int = 128
    history_top_k: int = 64
    retrieval_score_batch_size: int = 128
    archive_retention_seconds: float = 1800.0
    archive_memory_budget_mb: int | None = None
    kv_archive_device: str = "cuda"
    max_archived_units: int | None = None
    max_pending_queries: int = 16
    max_active_queries: int = 4
    retrieval_audio_context_seconds: float = 2.0
    pcost_enabled: bool = True
    pcost_i_threshold: float = 0.1
    pcost_skip_threshold: float = 0.04
    pcost_residual_p99_guard: float = 0.3
    pcost_changed_block_fraction_guard: float = 0.3
    pcost_max_consecutive_drops: int = 4
    pcost_resize_width: int = 512
    pcost_resize_height: int = 512
    pcost_block_size: int = 16
    pcost_search_radius_ratio: float = 0.08
    pcost_search_radius_min: int = 32
    pcost_search_radius_max: int = 96
    pcost_motion_penalty_weight: float = 0.01
    pcost_changed_block_residual_threshold: float = 0.03
    pcost_residual_quantile: float = 0.99
    pcost_max_p_frames_per_gop: int = 32

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "RuntimeConfig":
        """Build a validated config from a flat, serializable mapping."""
        if not isinstance(value, Mapping):
            raise TypeError("runtime configuration must be a mapping")
        known = {item.name for item in fields(cls)}
        unknown = sorted(set(value) - known)
        if unknown:
            raise ValueError(
                "unknown runtime configuration keys: " + ", ".join(unknown)
            )
        converted = dict(value)
        for name in _PATH_FIELDS:
            raw = converted.get(name)
            if raw is not None:
                if not isinstance(raw, (str, Path)) or not str(raw).strip():
                    raise ValueError(f"{name} must be null or a non-empty path")
                converted[name] = Path(raw).expanduser()
        config = cls(**converted)
        config.validate()
        return config

    def to_dict(self) -> dict[str, object]:
        """Return a YAML/JSON-safe flat mapping."""
        value = asdict(self)
        for name in _PATH_FIELDS:
            path = value[name]
            value[name] = None if path is None else str(path)
        return value

    def with_overrides(self, overrides: Mapping[str, object]) -> "RuntimeConfig":
        """Return a validated copy with explicit non-``None`` overrides."""
        values = self.to_dict()
        for key, value in overrides.items():
            if value is not None:
                values[key] = value
        return self.from_mapping(values)

    def validate(self) -> None:
        """Validate types, ranges, and cross-field contracts."""
        if self.inference_mode not in INFERENCE_MODES:
            raise ValueError(
                f"inference_mode must be one of {', '.join(INFERENCE_MODES)}"
            )
        for name in ("use_memory", "generate_audio", "pcost_enabled"):
            if not isinstance(getattr(self, name), bool):
                raise ValueError(f"{name} must be boolean")
        if not isinstance(self.device, str) or not self.device.strip():
            raise ValueError("device must be a non-empty string")
        if not isinstance(self.system_prompt, str) or not self.system_prompt.strip():
            raise ValueError("system_prompt must be a non-empty string")
        if self.output_language not in OUTPUT_LANGUAGES:
            raise ValueError(
                f"output_language must be one of {', '.join(OUTPUT_LANGUAGES)}"
            )
        if self.decode_mode not in {"sampling", "greedy"}:
            raise ValueError("decode_mode must be sampling or greedy")
        if self.kv_archive_device not in {"cpu", "cuda"}:
            raise ValueError("kv_archive_device must be cpu or cuda")
        _integer(self.seed, "seed", minimum=0)
        for name in (
            "max_new_tokens",
            "candidate_pool_size",
            "history_top_k",
            "retrieval_score_batch_size",
            "max_pending_queries",
            "max_active_queries",
            "pcost_resize_width",
            "pcost_resize_height",
            "pcost_block_size",
            "pcost_search_radius_min",
            "pcost_search_radius_max",
            "pcost_max_p_frames_per_gop",
        ):
            _integer(getattr(self, name), name, minimum=1)
        for name in ("archive_memory_budget_mb", "max_archived_units"):
            value = getattr(self, name)
            if value is not None:
                _integer(value, name, minimum=1)
        _integer(
            self.pcost_max_consecutive_drops, "pcost_max_consecutive_drops", minimum=0
        )
        for name in (
            "chunk_seconds",
            "online_context_seconds",
            "retrieval_recent_seconds",
            "archive_retention_seconds",
        ):
            minimum = float.fromhex("0x0.0000000000001p-1022")
            _number(getattr(self, name), name, minimum=minimum)
        _number(
            self.retrieval_audio_context_seconds,
            "retrieval_audio_context_seconds",
            minimum=0.0,
        )
        for name in (
            "pcost_i_threshold",
            "pcost_skip_threshold",
            "pcost_residual_p99_guard",
            "pcost_changed_block_fraction_guard",
            "pcost_search_radius_ratio",
            "pcost_motion_penalty_weight",
            "pcost_changed_block_residual_threshold",
            "pcost_residual_quantile",
        ):
            _number(getattr(self, name), name, minimum=0.0, maximum=1.0)
        if self.pcost_residual_quantile <= 0:
            raise ValueError("pcost_residual_quantile must be positive")
        if self.pcost_search_radius_min > self.pcost_search_radius_max:
            raise ValueError("pcost search-radius minimum cannot exceed maximum")
        if (
            self.pcost_resize_width % self.pcost_block_size
            or self.pcost_resize_height % self.pcost_block_size
        ):
            raise ValueError("PCost resize dimensions must be block aligned")
        if self.pcost_skip_threshold > self.pcost_i_threshold:
            raise ValueError("pcost_skip_threshold cannot exceed pcost_i_threshold")
        if self.retrieval_recent_seconds > self.online_context_seconds:
            raise ValueError(
                "retrieval_recent_seconds cannot exceed online_context_seconds"
            )
        if self.history_top_k > self.candidate_pool_size:
            raise ValueError("history_top_k cannot exceed candidate_pool_size")


def _integer(value: object, name: str, *, minimum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _number(
    value: object, name: str, *, minimum: float, maximum: float | None = None
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"{name} must be a finite number >= {minimum}")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return result


_PATH_FIELDS = ("ref_audio_path",)
