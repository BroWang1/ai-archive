# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Typed configuration for the deliverable memory integration package.

Defaults are defined by the dataclasses below. ``load_memory_config`` also
accepts explicit mappings and JSON/YAML paths; the Hugging Face controller
loads defaults with an optional archive-duration override. Conversion methods map these settings to the
internal Chat and Duplex engines.
"""

from __future__ import annotations
from dataclasses import asdict, dataclass, field, fields
import json
import math
from pathlib import Path
from typing import Mapping, TypeVar
from . import _engine_config


@dataclass(frozen=True)
class MemorySelectionConfig:
    """Configure the media selected for a memory-backed answer."""

    recent_visual_frames: int = 4
    candidate_pool_size: int = 128
    history_top_k: int = 96
    audio_context_seconds: float = 1.0


@dataclass(frozen=True)
class ArchiveConfig:
    """Configure retention of completed Duplex media units."""

    retention_seconds: float = 600.0
    device: str = "cuda"
    memory_budget_mb: int | None = None
    max_units: int | None = None


@dataclass(frozen=True)
class AnswerCompletionConfig:
    """Configure how a Duplex answer is completed at stream boundaries."""

    retry_empty_first_answer_chunk: bool = True
    max_answer_chunks_after_media_end: int = 16


@dataclass(frozen=True)
class ChatConfig:
    """Configure offline complete-media question answering."""

    max_new_tokens: int = 64
    retrieval_relevance_weight: float = 0.5


@dataclass(frozen=True)
class DuplexConfig:
    """Configure online Duplex processing and memory-backed answers."""

    system_prompt: str = _engine_config.DEFAULT_SYSTEM_PROMPT
    live_context_seconds: float = 120.0
    archive: ArchiveConfig = field(default_factory=ArchiveConfig)
    max_new_tokens_per_chunk: int = 6
    decode_mode: str = "sampling"
    proactive_output: str = "pause_during_answer"
    answer_completion: AnswerCompletionConfig = field(
        default_factory=AnswerCompletionConfig
    )


@dataclass(frozen=True)
class ChatResourceConfig:
    """Bound Chat visual encoding and retrieval working sets."""

    visual_encoding_frames_per_batch: int = 16
    retrieval_frames_per_batch: int = 256


@dataclass(frozen=True)
class DuplexResourceConfig:
    """Bound Duplex retrieval and unfinished background updates."""

    retrieval_units_per_batch: int = 128
    max_unfinished_memory_updates: int = 8


@dataclass(frozen=True)
class ResourceConfig:
    """Group resource-only settings that do not change memory semantics."""

    chat: ChatResourceConfig = field(default_factory=ChatResourceConfig)
    duplex: DuplexResourceConfig = field(default_factory=DuplexResourceConfig)


@dataclass(frozen=True)
class PCostBackendConfig:
    """Select execution backends without changing PCost mathematics."""

    chat_name: str = "torch_cuda"
    duplex_name: str = "cpu"
    pair_batch_size: int = 8
    block_batch_size: int = 8192


@dataclass(frozen=True)
class PCostMatchingConfig:
    """Configure block matching used by both Chat and Duplex."""

    resize_width: int = 512
    resize_height: int = 512
    block_size: int = 16
    search_radius_ratio: float = 0.08
    search_radius_min: int = 32
    search_radius_max: int = 96
    motion_penalty_weight: float = 0.01
    changed_block_residual_threshold: float = 0.03


@dataclass(frozen=True)
class PCostDecisionConfig:
    """Convert PCost matching measurements into visual KEEP/DROP decisions."""

    i_frame_pcost_threshold: float = 0.1
    max_p_frames_per_gop: int = 32
    skip_pcost_threshold: float = 0.04
    residual_quantile: float = 0.99
    residual_guard_threshold: float = 0.3
    changed_block_fraction_guard: float = 0.3
    max_consecutive_drops: int = 4


@dataclass(frozen=True)
class PCostConfig:
    """Group PCost enablement, implementation, matching, and decisions."""

    enabled: bool = True
    backend: PCostBackendConfig = field(default_factory=PCostBackendConfig)
    matching: PCostMatchingConfig = field(default_factory=PCostMatchingConfig)
    decision: PCostDecisionConfig = field(default_factory=PCostDecisionConfig)


@dataclass(frozen=True)
class MemoryConfig:
    """Validated settings for memory-enabled model calls and media sessions."""

    seed: int = 42
    memory: MemorySelectionConfig = field(default_factory=MemorySelectionConfig)
    chat: ChatConfig = field(default_factory=ChatConfig)
    duplex: DuplexConfig = field(default_factory=DuplexConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    pcost: PCostConfig = field(default_factory=PCostConfig)

    def to_dict(self) -> dict[str, object]:
        """Return a JSON/YAML-serializable mapping of every resolved field."""
        value = asdict(self)
        pcost = value["pcost"]
        assert isinstance(pcost, dict)
        backend = pcost["backend"]
        assert isinstance(backend, dict)
        pcost["backend"] = {
            "chat": {
                "name": backend["chat_name"],
                "pair_batch_size": backend["pair_batch_size"],
                "block_batch_size": backend["block_batch_size"],
            },
            "duplex": {"name": backend["duplex_name"]},
        }
        return value

    def validate(self) -> None:
        """Raise a precise exception when fields form an invalid configuration."""
        _positive_int(self.memory.recent_visual_frames, "memory.recent_visual_frames")
        _positive_int(self.memory.candidate_pool_size, "memory.candidate_pool_size")
        _positive_int(self.memory.history_top_k, "memory.history_top_k")
        if self.memory.history_top_k > self.memory.candidate_pool_size:
            raise ValueError("memory.history_top_k must not exceed candidate_pool_size")
        _positive(self.memory.audio_context_seconds, "memory.audio_context_seconds")
        _positive_int(self.chat.max_new_tokens, "chat.max_new_tokens")
        _weight(self.chat.retrieval_relevance_weight, "chat.retrieval_relevance_weight")
        if not self.duplex.system_prompt.strip():
            raise ValueError("duplex.system_prompt must be non-empty")
        _positive(self.duplex.live_context_seconds, "duplex.live_context_seconds")
        _positive(
            self.duplex.archive.retention_seconds, "duplex.archive.retention_seconds"
        )
        if self.duplex.archive.device not in {"cpu", "cuda"}:
            raise ValueError("duplex.archive.device must be cpu or cuda")
        for name, value in (
            ("duplex.archive.memory_budget_mb", self.duplex.archive.memory_budget_mb),
            ("duplex.archive.max_units", self.duplex.archive.max_units),
        ):
            if value is not None:
                _positive_int(value, name)
        _positive_int(
            self.duplex.max_new_tokens_per_chunk, "duplex.max_new_tokens_per_chunk"
        )
        if self.duplex.decode_mode not in {"sampling", "greedy"}:
            raise ValueError("duplex.decode_mode must be sampling or greedy")
        if self.duplex.proactive_output not in {
            "always",
            "pause_during_answer",
            "disabled",
        }:
            raise ValueError(
                "duplex.proactive_output must be always, pause_during_answer, or disabled"
            )
        if not isinstance(
            self.duplex.answer_completion.retry_empty_first_answer_chunk, bool
        ):
            raise TypeError("retry_empty_first_answer_chunk must be boolean")
        _positive_int(
            self.duplex.answer_completion.max_answer_chunks_after_media_end,
            "duplex.answer_completion.max_answer_chunks_after_media_end",
        )
        for name, value in (
            (
                "resources.chat.visual_encoding_frames_per_batch",
                self.resources.chat.visual_encoding_frames_per_batch,
            ),
            (
                "resources.chat.retrieval_frames_per_batch",
                self.resources.chat.retrieval_frames_per_batch,
            ),
            (
                "resources.duplex.retrieval_units_per_batch",
                self.resources.duplex.retrieval_units_per_batch,
            ),
            (
                "resources.duplex.max_unfinished_memory_updates",
                self.resources.duplex.max_unfinished_memory_updates,
            ),
        ):
            _positive_int(value, name)
        if not isinstance(self.pcost.enabled, bool):
            raise TypeError("pcost.enabled must be boolean")
        if self.pcost.backend.chat_name not in {
            "torch_cuda",
            "triton_cuda",
            "numpy_cpu",
        }:
            raise ValueError("pcost.backend.chat_name is unsupported")
        if self.pcost.backend.duplex_name != "cpu":
            raise ValueError("pcost.backend.duplex_name must be cpu in this release")
        _positive_int(
            self.pcost.backend.pair_batch_size, "pcost.backend.pair_batch_size"
        )
        _positive_int(
            self.pcost.backend.block_batch_size, "pcost.backend.block_batch_size"
        )
        matching = self.pcost.matching
        for name in (
            "resize_width",
            "resize_height",
            "block_size",
            "search_radius_min",
            "search_radius_max",
        ):
            _positive_int(getattr(matching, name), f"pcost.matching.{name}")
        if matching.search_radius_min > matching.search_radius_max:
            raise ValueError("search_radius_min must not exceed search_radius_max")
        for name in (
            "search_radius_ratio",
            "motion_penalty_weight",
            "changed_block_residual_threshold",
        ):
            _nonnegative(getattr(matching, name), f"pcost.matching.{name}")
        decision = self.pcost.decision
        _positive_int(
            decision.max_p_frames_per_gop, "pcost.decision.max_p_frames_per_gop"
        )
        for name in (
            "i_frame_pcost_threshold",
            "skip_pcost_threshold",
            "residual_guard_threshold",
            "changed_block_fraction_guard",
        ):
            _nonnegative(getattr(decision, name), f"pcost.decision.{name}")
        _weight(decision.residual_quantile, "pcost.decision.residual_quantile")
        if decision.residual_quantile == 0:
            raise ValueError("pcost.decision.residual_quantile must be positive")
        if decision.skip_pcost_threshold > decision.i_frame_pcost_threshold:
            raise ValueError("PCost skip threshold must not exceed I-frame threshold")
        if decision.max_consecutive_drops < 0:
            raise ValueError("pcost.decision.max_consecutive_drops must be nonnegative")

    def to_chat_engine_config(self) -> _engine_config.ChatMemoryConfig:
        """Build the configuration for the Chat memory engine."""
        matching = self.pcost.matching
        decision = self.pcost.decision
        return _engine_config.ChatMemoryConfig(
            chunk_seconds=1.0,
            visual_chunk_frames=self.resources.chat.visual_encoding_frames_per_batch,
            recent_frames=self.memory.recent_visual_frames,
            candidate_pool_size=self.memory.candidate_pool_size,
            history_top_k=self.memory.history_top_k,
            dense_frame_chunk_size=self.resources.chat.retrieval_frames_per_batch,
            relevance_weight=self.chat.retrieval_relevance_weight,
            audio_context_seconds=self.memory.audio_context_seconds,
            max_new_tokens=self.chat.max_new_tokens,
            pcost_matching=_engine_config.PCostMatchingConfig(
                backend=self.pcost.backend.chat_name,
                resize_width=matching.resize_width,
                resize_height=matching.resize_height,
                block_size=matching.block_size,
                search_radius_ratio=matching.search_radius_ratio,
                search_radius_min=matching.search_radius_min,
                search_radius_max=matching.search_radius_max,
                motion_penalty_weight=matching.motion_penalty_weight,
                changed_block_residual_threshold=matching.changed_block_residual_threshold,
                pair_batch_size=self.pcost.backend.pair_batch_size,
                block_batch_size=self.pcost.backend.block_batch_size,
            ),
            pcost_decision=_engine_config.PCostDecisionConfig(
                i_frame_pcost_threshold=decision.i_frame_pcost_threshold,
                max_p_frames_per_gop=decision.max_p_frames_per_gop,
                skip_pcost_threshold=decision.skip_pcost_threshold,
                residual_quantile=decision.residual_quantile,
                residual_guard_threshold=decision.residual_guard_threshold,
                changed_block_fraction_guard=decision.changed_block_fraction_guard,
                max_consecutive_drops=decision.max_consecutive_drops,
                protect_recent_frames=self.memory.recent_visual_frames,
            ),
        )

    def to_duplex_engine_config(self) -> _engine_config.DuplexMemoryConfig:
        """Build the configuration for the Duplex memory engine."""
        policy = {
            "always": "official",
            "pause_during_answer": "suppress_during_answer",
            "disabled": "disabled",
        }[self.duplex.proactive_output]
        decision = self.pcost.decision
        matching = self.pcost.matching
        return _engine_config.DuplexMemoryConfig(
            system_prompt=self.duplex.system_prompt,
            chunk_seconds=1.0,
            online_context_seconds=self.duplex.live_context_seconds,
            recent_seconds=float(self.memory.recent_visual_frames),
            candidate_pool_size=self.memory.candidate_pool_size,
            history_top_k=self.memory.history_top_k,
            retrieval_score_batch_size=self.resources.duplex.retrieval_units_per_batch,
            archive_retention_seconds=self.duplex.archive.retention_seconds,
            archive_memory_budget_mb=self.duplex.archive.memory_budget_mb,
            archive_device=self.duplex.archive.device,
            max_archived_units=self.duplex.archive.max_units,
            audio_context_seconds=self.memory.audio_context_seconds,
            max_pending_queries=16,
            max_active_queries=4,
            max_new_tokens=self.duplex.max_new_tokens_per_chunk,
            decode_mode=self.duplex.decode_mode,
            proactive_output_policy=policy,
            audio_sample_rate=16000,
            max_answer_tail_chunks=self.duplex.answer_completion.max_answer_chunks_after_media_end,
            no_memory_empty_turn_eos_grace_chunks=int(
                self.duplex.answer_completion.retry_empty_first_answer_chunk
            ),
            answer_step_timeout_seconds=300.0,
            require_explicit_turn_eos=False,
            pcost_enabled=self.pcost.enabled,
            pcost_i_threshold=decision.i_frame_pcost_threshold,
            pcost_skip_threshold=decision.skip_pcost_threshold,
            pcost_residual_guard=decision.residual_guard_threshold,
            pcost_changed_fraction_guard=decision.changed_block_fraction_guard,
            pcost_max_consecutive_drops=decision.max_consecutive_drops,
            pcost_max_pending_commits=self.resources.duplex.max_unfinished_memory_updates,
            pcost_resize_width=matching.resize_width,
            pcost_resize_height=matching.resize_height,
            pcost_block_size=matching.block_size,
            pcost_search_radius_ratio=matching.search_radius_ratio,
            pcost_search_radius_min=matching.search_radius_min,
            pcost_search_radius_max=matching.search_radius_max,
            pcost_motion_penalty_weight=matching.motion_penalty_weight,
            pcost_changed_block_residual_threshold=matching.changed_block_residual_threshold,
            pcost_residual_quantile=decision.residual_quantile,
            pcost_max_p_frames_per_gop=decision.max_p_frames_per_gop,
        )


ChatMemoryConfig = _engine_config.ChatMemoryConfig
DuplexMemoryConfig = _engine_config.DuplexMemoryConfig
T = TypeVar("T")


def _build_dataclass(cls: type[T], value: Mapping[str, object], path: str) -> T:
    """Construct one dataclass recursively while rejecting unknown keys."""
    known = {item.name for item in fields(cls)}
    unknown = sorted(set(value) - known)
    if unknown:
        raise ValueError(f"unknown {path} keys: {', '.join(unknown)}")
    return cls(**dict(value))


def memory_config_from_mapping(value: Mapping[str, object]) -> MemoryConfig:
    """Build and validate ``MemoryConfig`` from a nested mapping."""
    known = {"seed", "memory", "chat", "duplex", "resources", "pcost"}
    unknown = sorted(set(value) - known)
    if unknown:
        raise ValueError("unknown memory config keys: " + ", ".join(unknown))
    memory = _mapping(value.get("memory", {}), "memory")
    chat = _mapping(value.get("chat", {}), "chat")
    duplex = dict(_mapping(value.get("duplex", {}), "duplex"))
    archive = _mapping(duplex.pop("archive", {}), "duplex.archive")
    completion = _mapping(
        duplex.pop("answer_completion", {}), "duplex.answer_completion"
    )
    resources = dict(_mapping(value.get("resources", {}), "resources"))
    chat_resources = _mapping(resources.pop("chat", {}), "resources.chat")
    duplex_resources = _mapping(resources.pop("duplex", {}), "resources.duplex")
    if resources:
        raise ValueError("unknown resources keys: " + ", ".join(sorted(resources)))
    pcost = dict(_mapping(value.get("pcost", {}), "pcost"))
    backend_raw = dict(_mapping(pcost.pop("backend", {}), "pcost.backend"))
    chat_backend = dict(_mapping(backend_raw.pop("chat", {}), "pcost.backend.chat"))
    duplex_backend = dict(
        _mapping(backend_raw.pop("duplex", {}), "pcost.backend.duplex")
    )
    if backend_raw:
        raise ValueError(
            "unknown pcost.backend keys: " + ", ".join(sorted(backend_raw))
        )
    backend = PCostBackendConfig(
        chat_name=str(chat_backend.pop("name", "torch_cuda")),
        duplex_name=str(duplex_backend.pop("name", "cpu")),
        pair_batch_size=int(chat_backend.pop("pair_batch_size", 8)),
        block_batch_size=int(chat_backend.pop("block_batch_size", 8192)),
    )
    if chat_backend or duplex_backend:
        unknown_backend = sorted((*chat_backend, *duplex_backend))
        raise ValueError("unknown PCost backend keys: " + ", ".join(unknown_backend))
    matching = _build_dataclass(
        PCostMatchingConfig,
        _mapping(pcost.pop("matching", {}), "pcost.matching"),
        "pcost.matching",
    )
    decision = _build_dataclass(
        PCostDecisionConfig,
        _mapping(pcost.pop("decision", {}), "pcost.decision"),
        "pcost.decision",
    )
    config = MemoryConfig(
        seed=int(value.get("seed", 42)),
        memory=_build_dataclass(MemorySelectionConfig, memory, "memory"),
        chat=_build_dataclass(ChatConfig, chat, "chat"),
        duplex=_build_dataclass(
            DuplexConfig,
            {
                **duplex,
                "archive": _build_dataclass(ArchiveConfig, archive, "duplex.archive"),
                "answer_completion": _build_dataclass(
                    AnswerCompletionConfig, completion, "duplex.answer_completion"
                ),
            },
            "duplex",
        ),
        resources=ResourceConfig(
            chat=_build_dataclass(ChatResourceConfig, chat_resources, "resources.chat"),
            duplex=_build_dataclass(
                DuplexResourceConfig, duplex_resources, "resources.duplex"
            ),
        ),
        pcost=PCostConfig(
            enabled=_boolean(pcost.pop("enabled", True), "pcost.enabled"),
            backend=backend,
            matching=matching,
            decision=decision,
        ),
    )
    if pcost:
        raise ValueError("unknown pcost keys: " + ", ".join(sorted(pcost)))
    config.validate()
    return config


def load_memory_config(source: object | None) -> MemoryConfig:
    """Load configuration from ``None``, a mapping, JSON/YAML path, or object."""
    if source is None:
        config = MemoryConfig()
        config.validate()
        return config
    if isinstance(source, MemoryConfig):
        source.validate()
        return source
    if isinstance(source, Mapping):
        return memory_config_from_mapping(source)
    if not isinstance(source, (str, Path)):
        raise TypeError("config must be None, MemoryConfig, mapping, or JSON/YAML path")
    path = Path(source).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"memory config does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        try:
            import yaml
        except ImportError as error:
            raise RuntimeError("reading YAML config requires PyYAML") from error
        value = yaml.safe_load(text)
    if not isinstance(value, Mapping):
        raise ValueError("memory config root must be a mapping")
    return memory_config_from_mapping(value)


def _mapping(value: object, path: str) -> Mapping[str, object]:
    """Require a mapping at one configuration path."""
    if not isinstance(value, Mapping):
        raise TypeError(f"{path} must be a mapping")
    return value


def _boolean(value: object, name: str) -> bool:
    """Require a real boolean instead of coercing strings or integers."""
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be boolean")
    return value


def _positive(value: object, name: str) -> None:
    """Validate a finite positive real number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise ValueError(f"{name} must be finite and positive")


def _nonnegative(value: object, name: str) -> None:
    """Validate a finite nonnegative real number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a real number")
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def _positive_int(value: object, name: str) -> None:
    """Validate a positive integer."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _weight(value: object, name: str) -> None:
    """Validate a scalar in the closed interval from zero to one."""
    _nonnegative(value, name)
    if float(value) > 1:
        raise ValueError(f"{name} must be at most one")


__all__ = [
    "AnswerCompletionConfig",
    "ArchiveConfig",
    "ChatConfig",
    "DuplexConfig",
    "MemoryConfig",
    "MemorySelectionConfig",
    "PCostConfig",
    "ResourceConfig",
    "load_memory_config",
    "memory_config_from_mapping",
]
