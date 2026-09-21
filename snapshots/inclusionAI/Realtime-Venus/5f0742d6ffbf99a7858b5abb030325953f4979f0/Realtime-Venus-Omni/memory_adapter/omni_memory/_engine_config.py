# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Internal configuration for Chat and Duplex memory engines."""

from __future__ import annotations
from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path
from typing import Mapping, TypeVar

DEFAULT_SYSTEM_PROMPT = "Streaming Omni Conversation."


@dataclass(frozen=True)
class PCostMatchingConfig:
    backend: str = "torch_cuda"
    resize_width: int = 512
    resize_height: int = 512
    block_size: int = 16
    search_radius_ratio: float = 0.08
    search_radius_min: int = 32
    search_radius_max: int = 96
    motion_penalty_weight: float = 0.01
    changed_block_residual_threshold: float = 0.03
    pair_batch_size: int = 8
    block_batch_size: int = 8192

    def to_engine_mapping(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "input_resize": {
                "enabled": True,
                "width": self.resize_width,
                "height": self.resize_height,
                "mode": "stretch",
                "interpolation": "bicubic",
            },
            "block_size": self.block_size,
            "search_algorithm": "hexagonal_local_refine",
            "search_radius_ratio": self.search_radius_ratio,
            "search_radius_min": self.search_radius_min,
            "search_radius_max": self.search_radius_max,
            "motion_penalty_weight": self.motion_penalty_weight,
            "changed_block_residual_threshold": self.changed_block_residual_threshold,
            "decode_chunk_frames": 16,
            "pair_batch_size": self.pair_batch_size,
            "block_batch_size": self.block_batch_size,
        }


@dataclass(frozen=True)
class PCostDecisionConfig:
    i_frame_pcost_threshold: float = 0.1
    max_p_frames_per_gop: int = 32
    skip_pcost_threshold: float = 0.04
    residual_quantile: float = 0.99
    residual_guard_threshold: float = 0.3
    changed_block_fraction_guard: float = 0.3
    max_consecutive_drops: int = 4
    protect_recent_frames: int = 4

    def to_engine_mapping(self) -> dict[str, object]:
        return {
            "i_frame_pcost_threshold": self.i_frame_pcost_threshold,
            "max_p_frames_per_gop": self.max_p_frames_per_gop,
            "skip_pcost_threshold": self.skip_pcost_threshold,
            "residual_p99_guard": {
                "enabled": True,
                "quantile": self.residual_quantile,
                "threshold": self.residual_guard_threshold,
            },
            "changed_block_fraction_guard": {
                "enabled": True,
                "threshold": self.changed_block_fraction_guard,
            },
            "max_consecutive_drops": self.max_consecutive_drops,
            "protect_first_frame": True,
            "protect_recent_frames": self.protect_recent_frames,
        }


@dataclass(frozen=True)
class ChatMemoryConfig:
    chunk_seconds: float = 1.0
    visual_chunk_frames: int = 16
    recent_frames: int = 4
    candidate_pool_size: int = 128
    history_top_k: int = 64
    dense_frame_chunk_size: int = 256
    relevance_weight: float = 0.5
    audio_context_seconds: float = 2.0
    max_new_tokens: int = 64
    pcost_matching: PCostMatchingConfig = field(default_factory=PCostMatchingConfig)
    pcost_decision: PCostDecisionConfig = field(default_factory=PCostDecisionConfig)


@dataclass(frozen=True)
class DuplexMemoryConfig:
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    chunk_seconds: float = 1.0
    online_context_seconds: float = 120.0
    recent_seconds: float = 4.0
    candidate_pool_size: int = 128
    history_top_k: int = 64
    retrieval_score_batch_size: int = 128
    archive_retention_seconds: float = 1800.0
    archive_memory_budget_mb: int | None = None
    archive_device: str = "cuda"
    max_archived_units: int | None = None
    audio_context_seconds: float = 2.0
    max_pending_queries: int = 16
    max_active_queries: int = 4
    max_new_tokens: int = 20
    decode_mode: str = "sampling"
    proactive_output_policy: str = "suppress_during_answer"
    audio_sample_rate: int = 16000
    max_answer_tail_chunks: int = 16
    no_memory_empty_turn_eos_grace_chunks: int = 1
    answer_step_timeout_seconds: float = 300.0
    require_explicit_turn_eos: bool = True
    pcost_enabled: bool = True
    pcost_i_threshold: float = 0.1
    pcost_skip_threshold: float = 0.04
    pcost_residual_guard: float = 0.3
    pcost_changed_fraction_guard: float = 0.3
    pcost_max_consecutive_drops: int = 4
    pcost_max_pending_commits: int = 8
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


@dataclass(frozen=True)
class MemoryConfig:
    """Mode-separated defaults; Chat and Duplex semantics stay independent."""

    seed: int = 42
    chat: ChatMemoryConfig = field(default_factory=ChatMemoryConfig)
    duplex: DuplexMemoryConfig = field(default_factory=DuplexMemoryConfig)

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def validate(self) -> None:
        _validate_positive(self.chat.chunk_seconds, "chat.chunk_seconds")
        _validate_positive_int(
            self.chat.visual_chunk_frames, "chat.visual_chunk_frames"
        )
        _validate_positive_int(self.chat.recent_frames, "chat.recent_frames")
        _validate_topk(self.chat.candidate_pool_size, self.chat.history_top_k, "chat")
        _validate_positive_int(
            self.chat.dense_frame_chunk_size, "chat.dense_frame_chunk_size"
        )
        _validate_weight(self.chat.relevance_weight, "chat.relevance_weight")
        _validate_positive(
            self.chat.audio_context_seconds, "chat.audio_context_seconds"
        )
        _validate_positive_int(self.chat.max_new_tokens, "chat.max_new_tokens")
        if self.chat.pcost_decision.protect_recent_frames != self.chat.recent_frames:
            raise ValueError(
                "chat.pcost_decision.protect_recent_frames must equal chat.recent_frames"
            )
        matching = self.chat.pcost_matching
        if matching.backend not in {"numpy_cpu", "torch_cuda", "triton_cuda"}:
            raise ValueError("chat.pcost_matching.backend is unsupported")
        for name in (
            "resize_width",
            "resize_height",
            "block_size",
            "search_radius_min",
            "search_radius_max",
            "pair_batch_size",
            "block_batch_size",
        ):
            _validate_positive_int(
                getattr(matching, name), f"chat.pcost_matching.{name}"
            )
        if matching.search_radius_min > matching.search_radius_max:
            raise ValueError(
                "chat.pcost_matching.search_radius_min must not exceed search_radius_max"
            )
        for name in (
            "search_radius_ratio",
            "motion_penalty_weight",
            "changed_block_residual_threshold",
        ):
            _validate_nonnegative(
                getattr(matching, name), f"chat.pcost_matching.{name}"
            )
        decision = self.chat.pcost_decision
        _validate_positive_int(decision.max_p_frames_per_gop, "max_p_frames_per_gop")
        _validate_nonnegative(
            decision.i_frame_pcost_threshold,
            "chat.pcost_decision.i_frame_pcost_threshold",
        )
        _validate_nonnegative(
            decision.skip_pcost_threshold, "chat.pcost_decision.skip_pcost_threshold"
        )
        if decision.skip_pcost_threshold > decision.i_frame_pcost_threshold:
            raise ValueError("Chat PCost skip threshold must not exceed I threshold")
        _validate_weight(
            decision.residual_quantile, "chat.pcost_decision.residual_quantile"
        )
        if decision.residual_quantile <= 0:
            raise ValueError("chat.pcost_decision.residual_quantile must be positive")
        _validate_nonnegative(
            decision.residual_guard_threshold,
            "chat.pcost_decision.residual_guard_threshold",
        )
        _validate_nonnegative(
            decision.changed_block_fraction_guard,
            "chat.pcost_decision.changed_block_fraction_guard",
        )
        _validate_nonnegative_int(
            decision.max_consecutive_drops, "chat.pcost_decision.max_consecutive_drops"
        )
        _validate_topk(
            self.duplex.candidate_pool_size, self.duplex.history_top_k, "duplex"
        )
        for name in (
            "chunk_seconds",
            "online_context_seconds",
            "recent_seconds",
            "archive_retention_seconds",
            "audio_context_seconds",
        ):
            _validate_positive(getattr(self.duplex, name), f"duplex.{name}")
        if not isinstance(
            self.duplex.archive_device, str
        ) or self.duplex.archive_device not in {"cpu", "cuda"}:
            raise ValueError("duplex.archive_device must be cpu or cuda")
        if not isinstance(self.duplex.pcost_enabled, bool):
            raise ValueError("duplex.pcost_enabled must be boolean")
        if not isinstance(self.duplex.require_explicit_turn_eos, bool):
            raise ValueError("duplex.require_explicit_turn_eos must be boolean")
        if (
            not isinstance(self.duplex.system_prompt, str)
            or not self.duplex.system_prompt.strip()
        ):
            raise ValueError("duplex.system_prompt must be a non-empty string")
        if self.duplex.decode_mode not in {"sampling", "greedy"}:
            raise ValueError("duplex.decode_mode must be sampling or greedy")
        if self.duplex.proactive_output_policy not in {
            "official",
            "suppress_during_answer",
            "disabled",
        }:
            raise ValueError(
                "duplex.proactive_output_policy must be official, suppress_during_answer, or disabled"
            )
        if self.duplex.recent_seconds > self.duplex.online_context_seconds:
            raise ValueError(
                "duplex.recent_seconds must not exceed online_context_seconds"
            )
        if self.duplex.archive_memory_budget_mb is not None:
            _validate_positive_int(
                self.duplex.archive_memory_budget_mb, "duplex.archive_memory_budget_mb"
            )
        if self.duplex.max_archived_units is not None:
            _validate_positive_int(
                self.duplex.max_archived_units, "duplex.max_archived_units"
            )
        for name in (
            "retrieval_score_batch_size",
            "max_pending_queries",
            "max_active_queries",
            "max_new_tokens",
            "audio_sample_rate",
            "max_answer_tail_chunks",
            "pcost_max_pending_commits",
            "pcost_resize_width",
            "pcost_resize_height",
            "pcost_block_size",
            "pcost_search_radius_min",
            "pcost_search_radius_max",
            "pcost_max_p_frames_per_gop",
        ):
            _validate_positive_int(getattr(self.duplex, name), f"duplex.{name}")
        _validate_nonnegative_int(
            self.duplex.no_memory_empty_turn_eos_grace_chunks,
            "duplex.no_memory_empty_turn_eos_grace_chunks",
        )
        if self.duplex.max_active_queries > self.duplex.max_pending_queries:
            raise ValueError(
                "duplex.max_active_queries must not exceed max_pending_queries"
            )
        for name in (
            "pcost_i_threshold",
            "pcost_skip_threshold",
            "pcost_residual_guard",
            "pcost_changed_fraction_guard",
            "pcost_search_radius_ratio",
            "pcost_motion_penalty_weight",
            "pcost_changed_block_residual_threshold",
        ):
            _validate_nonnegative(getattr(self.duplex, name), f"duplex.{name}")
        _validate_weight(
            self.duplex.pcost_residual_quantile, "duplex.pcost_residual_quantile"
        )
        if self.duplex.pcost_residual_quantile <= 0:
            raise ValueError("duplex.pcost_residual_quantile must be positive")
        if self.duplex.pcost_search_radius_min > self.duplex.pcost_search_radius_max:
            raise ValueError("Duplex PCost search-radius bounds are invalid")
        if (
            self.duplex.pcost_resize_width % self.duplex.pcost_block_size
            or self.duplex.pcost_resize_height % self.duplex.pcost_block_size
        ):
            raise ValueError("Duplex PCost resize dimensions must be block aligned")
        if self.duplex.pcost_skip_threshold > self.duplex.pcost_i_threshold:
            raise ValueError("Duplex PCost skip threshold must not exceed I threshold")
        _validate_nonnegative_int(
            self.duplex.pcost_max_consecutive_drops,
            "duplex.pcost_max_consecutive_drops",
        )
        _validate_positive(
            self.duplex.answer_step_timeout_seconds,
            "duplex.answer_step_timeout_seconds",
        )
        if round(self.duplex.chunk_seconds * self.duplex.audio_sample_rate) <= 0:
            raise ValueError("duplex.chunk_seconds is too small for audio_sample_rate")


T = TypeVar("T")


def _strict_dataclass(cls: type[T], value: Mapping[str, object], path: str) -> T:
    known = {item.name for item in fields(cls)}
    unknown = sorted(set(value) - known)
    if unknown:
        raise ValueError(f"unknown {path} keys: {', '.join(unknown)}")
    return cls(**dict(value))


def memory_config_from_mapping(value: Mapping[str, object]) -> MemoryConfig:
    """Build a validated config without accepting silently ignored keys."""
    known = {"seed", "chat", "duplex"}
    unknown = sorted(set(value) - known)
    if unknown:
        raise ValueError("unknown memory config keys: " + ", ".join(unknown))
    chat_raw = value.get("chat", {})
    duplex_raw = value.get("duplex", {})
    if not isinstance(chat_raw, Mapping) or not isinstance(duplex_raw, Mapping):
        raise TypeError("chat and duplex config sections must be mappings")
    chat_values = dict(chat_raw)
    matching_raw = chat_values.pop("pcost_matching", {})
    decision_raw = chat_values.pop("pcost_decision", {})
    if not isinstance(matching_raw, Mapping) or not isinstance(decision_raw, Mapping):
        raise TypeError("Chat PCost sections must be mappings")
    chat = _strict_dataclass(
        ChatMemoryConfig,
        {
            **chat_values,
            "pcost_matching": _strict_dataclass(
                PCostMatchingConfig, matching_raw, "chat.pcost_matching"
            ),
            "pcost_decision": _strict_dataclass(
                PCostDecisionConfig, decision_raw, "chat.pcost_decision"
            ),
        },
        "chat",
    )
    duplex = _strict_dataclass(DuplexMemoryConfig, duplex_raw, "duplex")
    seed = value.get("seed", 42)
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    result = MemoryConfig(seed=seed, chat=chat, duplex=duplex)
    result.validate()
    return result


def load_memory_config(value: object | None) -> MemoryConfig:
    """Resolve a config object, mapping, or YAML path."""
    if value is None:
        result = MemoryConfig()
    elif isinstance(value, MemoryConfig):
        result = value
    elif isinstance(value, Mapping):
        result = memory_config_from_mapping(value)
    elif isinstance(value, (str, Path)):
        path = Path(value).expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"memory config does not exist: {path}")
        payload = path.read_text(encoding="utf-8")
        try:
            import yaml
        except ImportError:
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError as error:
                raise RuntimeError("non-JSON YAML config requires PyYAML") from error
        else:
            parsed = yaml.safe_load(payload)
        if not isinstance(parsed, Mapping):
            raise ValueError("memory config root must be a mapping")
        result = memory_config_from_mapping(parsed)
    else:
        raise TypeError("config must be None, MemoryConfig, mapping, or YAML path")
    result.validate()
    return result


def _validate_positive(value: object, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(float(value)))
        or (value <= 0)
    ):
        raise ValueError(f"{name} must be positive")


def _validate_positive_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


def _validate_nonnegative_int(value: object, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")


def _validate_weight(value: object, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(float(value)))
        or (not 0 <= value <= 1)
    ):
        raise ValueError(f"{name} must be in [0, 1]")


def _validate_nonnegative(value: object, name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or (not math.isfinite(float(value)))
        or (value < 0)
    ):
        raise ValueError(f"{name} must be finite and nonnegative")


def _validate_topk(pool: int, top_k: int, path: str) -> None:
    _validate_positive_int(pool, f"{path}.candidate_pool_size")
    _validate_positive_int(top_k, f"{path}.history_top_k")
    if pool < top_k:
        raise ValueError(f"{path}.candidate_pool_size must be >= history_top_k")
