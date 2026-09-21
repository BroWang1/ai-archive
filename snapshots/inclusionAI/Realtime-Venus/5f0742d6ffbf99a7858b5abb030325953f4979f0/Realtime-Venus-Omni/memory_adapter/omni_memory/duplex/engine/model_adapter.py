# Copyright 2026 The Realtime-Venus Team. All rights reserved.

"""Media capture and answer generation for Realtime-Venus-Omni Duplex."""

from __future__ import annotations
import copy
import random
from collections import deque
from contextlib import contextmanager, nullcontext
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence
from .audio_context import locate_audio_span
from .input_audio_state import (
    InputAudioState,
    capture_input_audio_state,
    restore_input_audio_state,
)
from .kv_cache import (
    concat_prevalidated_kv_caches,
    estimate_kv_bytes,
    kv_cache_layout_signature,
    relocate_kv_cache_keys_from_position_rows,
    relocate_rope_keys,
    slice_kv_cache,
)

_DECODER_BRANCH_STATE_NAMES = (
    "_unit_history",
    "_pending_unit_id",
    "_next_unit_id",
    "_pending_unit_start_cache_len",
    "_system_preserve_length",
    "_position_offset",
    "generated_tokens",
    "generated_special_tokens",
)
_DUPLEX_BRANCH_STATE_NAMES = (
    "pending_logits",
    "total_ids",
    "prefill_schema_tokens",
    "_current_unit_prefill_tokens",
    "current_mode",
    "_streaming_generate_count",
    "current_turn_ended",
    "audio_chunk_idx",
    "speak_count",
    "res_ids",
    "total_hidden",
    "audio_buffer",
    "input_audio_buffer",
    "query_generate_count",
)


class _AbsentState:
    """Sentinel for an attribute that did not exist in one branch."""

    def __copy__(self) -> "_AbsentState":
        return self


_ABSENT_STATE = _AbsentState()


@dataclass(frozen=True)
class EncodedDuplexUnit:
    """Artifacts captured from exactly one completed duplex input unit."""

    unit_id: int
    timestamp_seconds: float
    visual_embeddings: Any | None
    unit_cache: Any
    cache_start: int
    cache_end: int
    capture_local_start: int
    capture_local_end: int
    audio_cache: Any | None = None
    audio_cache_start: int | None = None
    audio_cache_end: int | None = None
    audio_capture_local_start: int | None = None
    audio_capture_local_end: int | None = None
    audio_token_count: int = 0
    visual_frame_count: int = 0


@dataclass
class QueryBranch:
    """Persistent query decoder and input audio state between generation chunks."""

    branch_id: int
    question: str
    retrieved_unit_ids: tuple[int, ...]
    cache: Any
    decoder_state: dict[str, Any]
    duplex_state: dict[str, Any]
    rng_state: dict[str, Any]
    chunk_count: int = 0
    appended_media_count: int = 0
    finished: bool = False
    closed: bool = False
    _adapter_identity: int = field(default=0, repr=False)
    input_audio_state: InputAudioState | None = None


@dataclass(frozen=True)
class QueryChunkResult:
    """One decoder chunk with the generation result."""

    branch_id: int
    chunk_index: int
    text: str
    audio: Any | None
    is_listen: bool
    end_of_turn: bool
    raw_result: dict[str, Any]


class RealtimeVenusOmniDuplexAdapter:
    """Load one model and expose cache-aware ingest/query operations."""

    def __init__(self, duplex_model: Any) -> None:
        self.duplex = duplex_model
        self.decoder = duplex_model.decoder
        self.device = getattr(
            duplex_model,
            "device",
            getattr(getattr(duplex_model, "model", None), "device", None),
        )
        if self.device is None:
            raise ValueError("duplex model must expose its inference device")
        self._prefix_cache: Any | None = None
        self._prefix_length = 0
        self._captured_cache_layout: tuple[Any, ...] | None = None
        self._prefix_decoder_state: dict[str, Any] = {}
        self._prefix_decoder_branch_state: dict[str, Any] = {}
        self._prefix_duplex_state: dict[str, Any] = {}
        self._prefix_duplex_branch_state: dict[str, Any] = {}
        self._next_unit_id = 0
        self._next_branch_id = 0
        self._live_media_timestamps: deque[tuple[int, float]] = deque()
        self._query_branches: dict[int, QueryBranch] = {}
        self._is_prepared = False

    @property
    def prefix_cache(self) -> Any | None:
        return self._prefix_cache

    @property
    def prefix_length(self) -> int:
        return self._prefix_length

    @property
    def live_unit_ids(self) -> tuple[int, ...]:
        """IDs physically present in the online decoder's media window."""
        return tuple((unit_id for (unit_id, _) in self._live_media_timestamps))

    def prepare(
        self,
        *,
        system_prompt: str,
        ref_audio: Any | None = None,
        prompt_wav_path: str | Path | None = None,
        context_previous_marker: str = "\n\nprevious: ",
        **kwargs: Any,
    ) -> Any:
        if self._query_branches:
            raise RuntimeError(
                "cannot prepare while persistent query branches are open"
            )
        result = self.duplex.prepare(
            prefix_system_prompt=system_prompt,
            ref_audio=ref_audio,
            prompt_wav_path=None if prompt_wav_path is None else str(prompt_wav_path),
            context_previous_marker=context_previous_marker,
            **kwargs,
        )
        self._prefix_length = self.cache_length()
        self._prefix_cache = (
            None
            if self._prefix_length == 0
            else slice_kv_cache(self.decoder.cache, 0, self._prefix_length)
        )
        self._captured_cache_layout = (
            None
            if self._prefix_cache is None
            else kv_cache_layout_signature(self._prefix_cache)
        )
        self._prefix_decoder_state = _capture_named_state(
            self.decoder, ("generated_tokens", "generated_special_tokens")
        )
        self._prefix_decoder_branch_state = _snapshot_exact_named_state(
            self.decoder, ("generated_tokens", "generated_special_tokens")
        )
        self._prefix_duplex_state = _capture_named_state(
            self.duplex, _DUPLEX_BRANCH_STATE_NAMES
        )
        self._prefix_duplex_branch_state = _snapshot_exact_named_state(
            self.duplex, _DUPLEX_BRANCH_STATE_NAMES
        )
        self._live_media_timestamps.clear()
        self._next_unit_id = 0
        self._is_prepared = True
        return result

    def cache_length(self) -> int:
        getter = getattr(self.decoder, "get_cache_length", None)
        if callable(getter):
            return int(getter())
        cache = getattr(self.decoder, "cache", None)
        if cache is None:
            return 0
        if hasattr(cache, "key_cache"):
            return int(cache.key_cache[0].shape[-2]) if cache.key_cache else 0
        return int(cache[0][0].shape[-2])

    def ingest_media_unit(
        self,
        *,
        timestamp_seconds: float,
        frame_list: Sequence[Any] | None,
        audio_waveform: Any | None,
        max_slice_nums: int = 1,
        finalize_as_listen: bool = True,
        capture_memory_artifacts: bool = True,
        capture_audio_artifacts: bool = False,
    ) -> EncodedDuplexUnit:
        """Encode one unit and optionally copy artifacts for retrieval memory."""
        if timestamp_seconds < 0:
            raise ValueError("timestamp_seconds must be nonnegative")
        if (
            self._live_media_timestamps
            and timestamp_seconds < self._live_media_timestamps[-1][1]
        ):
            raise ValueError("media timestamps must be nondecreasing")
        local_start = self.cache_length()
        timeline_start = self._absolute_cache_position(local_start)
        captured_vision: list[Any] = []
        capture_context = (
            _capture_method_output(
                self.duplex.model, "get_vision_embedding", captured_vision
            )
            if capture_memory_artifacts
            else nullcontext()
        )
        with capture_context:
            result = self.duplex.streaming_prefill(
                audio_waveform=audio_waveform,
                frame_list=list(frame_list) if frame_list else None,
                max_slice_nums=max_slice_nums,
                batch_vision_feed=True,
            )
        if not result or result.get("success") is not True:
            reason = result.get("reason") if isinstance(result, dict) else result
            raise RuntimeError(f"Realtime-Venus-Omni streaming_prefill failed: {reason}")
        prefill_local_end = self.cache_length()
        audio_local_start: int | None = None
        audio_local_end: int | None = None
        if capture_audio_artifacts and audio_waveform is not None:
            schemas = getattr(self.duplex, "prefill_schema_tokens", None)
            if not isinstance(schemas, (list, tuple)) or not schemas:
                raise RuntimeError(
                    "audio context capture requires official prefill_schema_tokens"
                )
            schema = schemas[-1]
            if not isinstance(schema, (list, tuple)):
                raise RuntimeError(
                    "latest official media prefill schema must be a sequence"
                )
            (relative_start, relative_end) = locate_audio_span(
                schema, expected_token_count=prefill_local_end - local_start
            )
            audio_local_start = local_start + relative_start
            audio_local_end = local_start + relative_end
        if finalize_as_listen:
            pass
        local_end = self.cache_length()
        if local_end <= local_start:
            raise RuntimeError("duplex unit did not append any KV tokens")
        unit_cache = (
            slice_kv_cache(self.decoder.cache, local_start, local_end)
            if capture_memory_artifacts
            else None
        )
        timeline_end = timeline_start + local_end - local_start
        visual = (
            _flatten_visual_embeddings(captured_vision[-1]) if captured_vision else None
        )
        audio_cache = (
            slice_kv_cache(self.decoder.cache, audio_local_start, audio_local_end)
            if audio_local_start is not None and audio_local_end is not None
            else None
        )
        unit = EncodedDuplexUnit(
            unit_id=self._next_unit_id,
            timestamp_seconds=float(timestamp_seconds),
            visual_embeddings=visual,
            unit_cache=unit_cache,
            cache_start=timeline_start,
            cache_end=timeline_end,
            capture_local_start=local_start,
            capture_local_end=local_end,
            audio_cache=audio_cache,
            audio_cache_start=(
                None
                if audio_local_start is None
                else timeline_start + audio_local_start - local_start
            ),
            audio_cache_end=(
                None
                if audio_local_end is None
                else timeline_start + audio_local_end - local_start
            ),
            audio_capture_local_start=audio_local_start,
            audio_capture_local_end=audio_local_end,
            audio_token_count=(
                0
                if audio_local_start is None or audio_local_end is None
                else audio_local_end - audio_local_start
            ),
        )
        self._live_media_timestamps.append((unit.unit_id, unit.timestamp_seconds))
        self._next_unit_id += 1
        return unit

    def embed_query(self, text: str) -> Any:
        """Return decoder-space question tokens for visual late interaction."""
        if not text.strip():
            raise ValueError("question text must be non-empty")
        token_ids = self.duplex.tokenizer.encode(text, add_special_tokens=False)
        if not token_ids:
            raise ValueError("question produced no tokenizer tokens")
        try:
            import torch
        except ImportError as error:
            raise RuntimeError("query embedding requires torch") from error
        ids = torch.tensor(token_ids, dtype=torch.long, device=self.device)
        embedder = _find_token_embedder(self.duplex, self.decoder)
        if embedder is None:
            raise RuntimeError(
                "loaded Realtime-Venus-Omni model exposes no token embedding layer"
            )
        return embedder(ids)

    def create_query_branch(
        self, *, question: str, units: Sequence[Any] = (), use_live_cache: bool = False
    ) -> QueryBranch:
        """Assemble retrieval context and prefill text into a persistent branch.

        The live media decoder is restored before this method returns.  Setting
        ``use_live_cache`` creates the no-memory baseline branch and therefore
        cannot be combined with retrieved units.
        """
        if not isinstance(question, str) or not question.strip():
            raise ValueError("question must be a non-empty string")
        if not self._is_prepared:
            raise RuntimeError("prepare must be called before creating a query branch")
        if use_live_cache and units:
            raise ValueError("use_live_cache cannot be combined with retrieved units")
        input_audio_state = capture_input_audio_state(self.duplex, clone=True)
        if use_live_cache:
            cache = slice_kv_cache(self.decoder.cache, 0, self.cache_length())
            retrieved_unit_ids: tuple[int, ...] = ()
            initial_decoder_state = _snapshot_exact_named_state(
                self.decoder, _DECODER_BRANCH_STATE_NAMES
            )
            initial_duplex_state = _snapshot_exact_named_state(
                self.duplex, _DUPLEX_BRANCH_STATE_NAMES
            )
        else:
            cache = self._assemble_branch_cache(units)
            initial_decoder_state = {}
            initial_duplex_state = {}
            retrieved_unit_ids = tuple(
                (
                    int(unit.unit_id)
                    for unit in sorted(
                        units, key=lambda item: (item.timestamp_seconds, item.unit_id)
                    )
                )
            )
        branch = QueryBranch(
            branch_id=self._next_branch_id,
            question=question,
            retrieved_unit_ids=retrieved_unit_ids,
            cache=cache,
            decoder_state=initial_decoder_state,
            duplex_state=initial_duplex_state,
            rng_state=_capture_rng_state(self.device),
            input_audio_state=input_audio_state,
            _adapter_identity=id(self),
        )
        with self._persistent_branch_context(branch, initialize=not use_live_cache):
            result = self.duplex.streaming_prefill(text_list=[question])
            if not result or result.get("success") is not True:
                reason = result.get("reason") if isinstance(result, dict) else result
                raise RuntimeError(f"question streaming_prefill failed: {reason}")
        self._query_branches[branch.branch_id] = branch
        self._next_branch_id += 1
        return branch

    def generate_query_chunk(
        self,
        branch: QueryBranch,
        *,
        max_new_tokens: int,
        decode_mode: str = "sampling",
        prompt_wav_path: str | Path | None = None,
        temperature: float = 0.7,
        top_k: int = 100,
        top_p: float = 0.8,
        listen_prob_scale: float = 1.0,
        listen_top_k: int | None = None,
        text_repetition_penalty: float = 1.05,
        text_repetition_window_size: int = 512,
    ) -> QueryChunkResult:
        """Generate one chunk, persist its updated branch, and restore live state."""
        branch = self._require_open_branch(branch)
        if branch.finished:
            raise RuntimeError("query branch has already reached end_of_turn")
        if max_new_tokens <= 0:
            raise ValueError("max_new_tokens must be positive")
        with self._persistent_branch_context(branch):
            result = dict(
                self.duplex.streaming_generate(
                    prompt_wav_path=(
                        None if prompt_wav_path is None else str(prompt_wav_path)
                    ),
                    max_new_speak_tokens_per_chunk=max_new_tokens,
                    decode_mode=decode_mode,
                    temperature=temperature,
                    top_k=top_k,
                    top_p=top_p,
                    listen_prob_scale=listen_prob_scale,
                    listen_top_k=listen_top_k,
                    text_repetition_penalty=text_repetition_penalty,
                    text_repetition_window_size=text_repetition_window_size,
                )
            )
        chunk_index = branch.chunk_count
        branch.chunk_count += 1
        branch.finished = bool(result.get("end_of_turn", False))
        return QueryChunkResult(
            branch_id=branch.branch_id,
            chunk_index=chunk_index,
            text=str(result.get("text") or ""),
            audio=_result_audio(result),
            is_listen=bool(result.get("is_listen", False)),
            end_of_turn=bool(result.get("end_of_turn", False)),
            raw_result=result,
        )

    def append_live_media_to_query(
        self,
        branch: QueryBranch,
        *,
        frame_list: Sequence[Any] | None,
        audio_waveform: Any | None,
        max_slice_nums: int = 1,
    ) -> dict[str, Any]:
        """Prefill a query tail using its decoder and isolated input audio state."""
        branch = self._require_open_branch(branch)
        if branch.finished:
            raise RuntimeError("cannot append media after query end_of_turn")
        with self._persistent_branch_context(branch):
            result = self.duplex.streaming_prefill(
                audio_waveform=audio_waveform,
                frame_list=list(frame_list) if frame_list else None,
                max_slice_nums=max_slice_nums,
                batch_vision_feed=True,
            )
            if not result or result.get("success") is not True:
                reason = result.get("reason") if isinstance(result, dict) else result
                raise RuntimeError(f"branch media streaming_prefill failed: {reason}")
        branch.appended_media_count += 1
        return {**dict(result), "branch_id": branch.branch_id}

    def close_query_branch(self, branch: QueryBranch) -> None:
        """Release a persistent branch. Closing the same branch twice is safe."""
        if not isinstance(branch, QueryBranch) or branch._adapter_identity != id(self):
            raise ValueError("query branch does not belong to this adapter")
        if branch.closed:
            return
        registered = self._query_branches.get(branch.branch_id)
        if registered is not branch:
            raise ValueError("query branch is not registered with this adapter")
        self._query_branches.pop(branch.branch_id)
        branch.cache = None
        branch.decoder_state.clear()
        branch.duplex_state.clear()
        branch.rng_state.clear()
        branch.input_audio_state = None
        branch.closed = True

    def _require_open_branch(self, branch: QueryBranch) -> QueryBranch:
        if not isinstance(branch, QueryBranch) or branch._adapter_identity != id(self):
            raise ValueError("query branch does not belong to this adapter")
        if branch.closed:
            raise RuntimeError("query branch is closed")
        if self._query_branches.get(branch.branch_id) is not branch:
            raise ValueError("query branch is not registered with this adapter")
        return branch

    @contextmanager
    def _persistent_branch_context(
        self, branch: QueryBranch, *, initialize: bool = False
    ) -> Iterator[None]:
        """Swap decoder and input audio state, then restore live even on failure."""
        if branch.input_audio_state is None:
            raise RuntimeError(
                "query branch has no input audio state; create a new branch"
            )
        live_input_audio_state = capture_input_audio_state(self.duplex)
        live_cache = self.decoder.cache
        live_decoder_state = _read_exact_named_state(
            self.decoder, _DECODER_BRANCH_STATE_NAMES
        )
        live_duplex_state = _read_exact_named_state(
            self.duplex, _DUPLEX_BRANCH_STATE_NAMES
        )
        live_rng_state = _capture_rng_state(self.device)
        self.decoder.cache = branch.cache
        input_audio_installed = False
        try:
            if initialize:
                self._initialize_branch_runtime()
            else:
                _restore_exact_named_state(
                    self.decoder, branch.decoder_state, clone_values=False
                )
                _restore_exact_named_state(
                    self.duplex, branch.duplex_state, clone_values=False
                )
            restore_input_audio_state(self.duplex, branch.input_audio_state)
            input_audio_installed = True
            _restore_rng_state(branch.rng_state)
            yield
        finally:
            try:
                if input_audio_installed:
                    branch.input_audio_state = capture_input_audio_state(self.duplex)
                branch.cache = self.decoder.cache
                branch.decoder_state = _read_exact_named_state(
                    self.decoder, _DECODER_BRANCH_STATE_NAMES
                )
                branch.duplex_state = _read_exact_named_state(
                    self.duplex, _DUPLEX_BRANCH_STATE_NAMES
                )
                branch.rng_state = _capture_rng_state(self.device)
            finally:
                try:
                    self.decoder.cache = live_cache
                    _restore_exact_named_state(
                        self.decoder, live_decoder_state, clone_values=False
                    )
                    _restore_exact_named_state(
                        self.duplex, live_duplex_state, clone_values=False
                    )
                finally:
                    try:
                        restore_input_audio_state(self.duplex, live_input_audio_state)
                    finally:
                        _restore_rng_state(live_rng_state)

    def _initialize_branch_runtime(self) -> None:
        if hasattr(self.decoder, "_unit_history"):
            self.decoder._unit_history = []
        if hasattr(self.decoder, "_pending_unit_id"):
            self.decoder._pending_unit_id = None
        if hasattr(self.decoder, "_next_unit_id"):
            self.decoder._next_unit_id = 0
        if hasattr(self.decoder, "_pending_unit_start_cache_len"):
            self.decoder._pending_unit_start_cache_len = self.cache_length()
        if hasattr(self.decoder, "_system_preserve_length"):
            self.decoder._system_preserve_length = self._prefix_length
        if hasattr(self.decoder, "_position_offset"):
            self.decoder._position_offset = 0
        _restore_exact_named_state(
            self.decoder, self._prefix_decoder_branch_state, clone_values=True
        )
        _restore_exact_named_state(
            self.duplex, self._prefix_duplex_branch_state, clone_values=True
        )

    def unit_kv_bytes(self, unit: EncodedDuplexUnit) -> int:
        self._validate_captured_cache_layout(unit.unit_cache)
        return estimate_kv_bytes(unit.unit_cache)

    def kv_cache_bytes(self, cache: Any) -> int:
        """Return exact tensor payload bytes for any captured KV slice."""
        self._validate_captured_cache_layout(cache)
        return estimate_kv_bytes(cache)

    def _validate_captured_cache_layout(self, cache: Any) -> None:
        layout = kv_cache_layout_signature(cache)
        if self._captured_cache_layout is None:
            self._captured_cache_layout = layout
        elif layout != self._captured_cache_layout:
            raise ValueError(
                "captured KV cache layout differs from the prepared model cache"
            )

    def move_unit_cache(self, cache: Any, device: str, *, pin_cpu: bool = False) -> Any:
        """Move an archived unit cache without changing its token layout."""
        if not pin_cpu and _cache_is_on_device(cache, device):
            return cache
        return _map_cache_tensors(
            cache, lambda tensor: _move_tensor(tensor, device=device, pin_cpu=pin_cpu)
        )

    def enforce_online_context_window(
        self, *, latest_timestamp_seconds: float, window_seconds: float
    ) -> tuple[int, ...]:
        """Keep completed media units in ``(latest-window, latest]``."""
        if latest_timestamp_seconds < 0:
            raise ValueError("latest_timestamp_seconds must be nonnegative")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        history = getattr(self.decoder, "_unit_history", None)
        drop_next = getattr(self.decoder, "_drop_next_unit", None)
        if history is None or not callable(drop_next):
            raise RuntimeError(
                "Realtime-Venus-Omni decoder lacks unit-aware sliding-window primitives"
            )
        dropped: list[int] = []
        while (
            self._live_media_timestamps
            and latest_timestamp_seconds - self._live_media_timestamps[0][1]
            >= window_seconds
        ):
            (expected_unit_id, _) = self._live_media_timestamps[0]
            media_history = [item for item in history if item.get("type") != "system"]
            first = media_history[0] if media_history else None
            if first is None:
                raise RuntimeError("failed to evict the oldest completed live unit")
            if not drop_next():
                raise RuntimeError("failed to evict the oldest completed live unit")
            self._live_media_timestamps.popleft()
            dropped.append(expected_unit_id)
            history = getattr(self.decoder, "_unit_history", history)
        return tuple(dropped)

    @staticmethod
    def _unit_rope_source_span(unit: Any) -> tuple[int, int]:
        """Return the position span that actually encoded one captured Key."""
        start = getattr(unit, "kv_capture_local_start", None)
        end = getattr(unit, "kv_capture_local_end", None)
        if start is None or end is None:
            raise ValueError(f"unit {unit.unit_id} lacks capture-local KV coordinates")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or (not isinstance(end, int))
            or (start < 0)
            or (end <= start)
        ):
            raise ValueError(
                f"unit {unit.unit_id} has an invalid capture-local KV span"
            )
        legacy_length = int(unit.kv_source_end - unit.kv_source_start)
        if end - start != legacy_length:
            raise ValueError(
                f"unit {unit.unit_id} source frames have different lengths"
            )
        return (int(start), int(end))

    def _assemble_branch_cache(self, units: Sequence[Any]) -> Any:
        """Build one dense cache, then relocate arbitrary source holes in one batch."""
        caches: list[Any] = []
        next_position = 0
        ordered_units = tuple(
            sorted(units, key=lambda item: (item.timestamp_seconds, item.unit_id))
        )
        plans: list[tuple[Any, int, int]] = []
        planned_target = self._prefix_length
        source_positions: list[int] = list(range(self._prefix_length))
        reindexed_unit_ids: list[int] = []
        for unit in ordered_units:
            (source_start, source_end) = self._unit_rope_source_span(unit)
            length = source_end - source_start
            plans.append((unit, length, planned_target))
            source_positions.extend(range(source_start, source_end))
            if source_start != planned_target:
                reindexed_unit_ids.append(int(unit.unit_id))
            planned_target += length
        target_positions = tuple(range(planned_target))
        source_position_tuple = tuple(source_positions)
        if self._prefix_cache is not None:
            if _cache_token_count(self._prefix_cache) == self._prefix_length:
                caches.append(self._prefix_cache)
            else:
                caches.append(
                    slice_kv_cache(
                        self._prefix_cache, 0, self._prefix_length, clone=False
                    )
                )
            next_position = self._prefix_length
        for unit, length, target_start in plans:
            if target_start != next_position:
                raise RuntimeError("KV assembly target plan became inconsistent")
            cache = self.move_unit_cache(unit.kv_cache, str(self.device))
            if _cache_token_count(cache) == length:
                caches.append(cache)
            else:
                caches.append(slice_kv_cache(cache, 0, length, clone=False))
            next_position += length
        if next_position != planned_target:
            raise RuntimeError("KV assembly token count diverged from its plan")
        if len(source_position_tuple) != next_position:
            raise RuntimeError("KV assembly position map has the wrong length")
        if not caches:
            raise RuntimeError("query branch cannot be assembled from an empty cache")
        assembled = concat_prevalidated_kv_caches(caches)
        if reindexed_unit_ids:
            (source_cos, source_sin) = self._build_rope_rows(
                _first_cache_key(assembled), source_position_tuple
            )
            (target_cos, target_sin) = self._build_rope_rows(
                _first_cache_key(assembled), target_positions
            )
            assembled = relocate_kv_cache_keys_from_position_rows(
                assembled,
                source_position_tuple,
                target_positions,
                source_cos=source_cos,
                source_sin=source_sin,
                target_cos=target_cos,
                target_sin=target_sin,
            )
        return assembled

    def _absolute_cache_position(self, local_position: int) -> int:
        """Map a compact cache index to its monotonic timeline position.

        Eviction relocates retained keys into the compact cache coordinate frame.
        The timeline position differs from the source position used to relocate
        an archived key.
        """
        offset = int(getattr(self.decoder, "_position_offset", 0))
        return local_position + offset

    def _reindex_unit_cache(
        self, cache: Any, *, source_start: int, target_start: int, length: int
    ) -> Any:
        """Relocate already-rotated keys while leaving values unchanged."""
        official = getattr(self.decoder, "_reindex_rope_for_cache", None)
        if callable(official):
            return official(cache, source_start, target_start, length)
        first_key = _first_cache_key(cache)
        limit = max(source_start + length, target_start + length)
        (cos_table, sin_table) = self._build_rope_tables(first_key, limit)
        source_positions = range(source_start, source_start + length)
        target_positions = range(target_start, target_start + length)
        return _map_cache_key_values(
            cache,
            key_transform=lambda key: relocate_rope_keys(
                key,
                source_positions,
                target_positions,
                cos_table=cos_table,
                sin_table=sin_table,
            ),
            value_transform=lambda value: value,
        )

    def _build_rope_tables(self, reference_key: Any, length: int) -> tuple[Any, Any]:
        """Ask the loaded model's own rotary module for matching cos/sin tables."""
        return self._build_rope_rows(reference_key, range(length))

    def _build_rope_rows(
        self, reference_key: Any, positions: Sequence[int]
    ) -> tuple[Any, Any]:
        """Ask the model rotary module only for the requested position rows."""
        rotary = _find_rotary_embedding(self.duplex, self.decoder)
        if rotary is None:
            raise RuntimeError(
                "non-contiguous KV retrieval requires an accessible model rotary embedding or decoder._reindex_rope_for_cache"
            )
        try:
            import torch
        except ImportError as error:
            raise RuntimeError("RoPE cache relocation requires torch") from error
        position_tuple = tuple((int(position) for position in positions))
        if any((position < 0 for position in position_tuple)):
            raise ValueError("RoPE positions must be non-negative")
        position_ids = torch.tensor(
            position_tuple, dtype=torch.long, device=reference_key.device
        ).unsqueeze(0)
        try:
            with torch.inference_mode():
                (cos_table, sin_table) = rotary(reference_key, position_ids)
        except TypeError as error:
            raise RuntimeError(
                "the loaded rotary embedding does not expose the expected forward(hidden_states, position_ids) interface"
            ) from error
        while cos_table.ndim > 2:
            cos_table = cos_table[0]
            sin_table = sin_table[0]
        expected_shape = (len(position_tuple), int(cos_table.shape[-1]))
        if tuple((int(size) for size in cos_table.shape)) != expected_shape:
            raise RuntimeError(
                "rotary embedding returned rows that do not match position_ids"
            )
        if tuple((int(size) for size in sin_table.shape)) != expected_shape:
            raise RuntimeError(
                "rotary embedding returned inconsistent cosine/sine rows"
            )
        return (cos_table, sin_table)

    def _finalize_listen_unit(self) -> dict[str, Any]:
        """Close a media unit while suppressing autonomous answers."""
        count = int(getattr(self.duplex, "_streaming_generate_count", 0))
        previous = int(getattr(self.duplex, "force_listen_count", 0))
        self.duplex.force_listen_count = max(previous, count + 1)
        try:
            result = dict(
                self.duplex.streaming_generate(
                    max_new_speak_tokens_per_chunk=20, decode_mode="greedy"
                )
            )
        finally:
            self.duplex.force_listen_count = previous
        if result.get("is_listen") is not True:
            raise RuntimeError(
                "forced media finalization unexpectedly generated speech"
            )
        return result


def compare_generation_reports(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """Compare bounded greedy generations without treating text as sufficient."""
    fields = (
        "text",
        "token_ids",
        "symbols",
        "end_of_turn",
        "stopped_reason",
        "chunk_count",
    )
    matches = {name: reference.get(name) == candidate.get(name) for name in fields}
    reference_chunks = reference.get("chunks") or []
    candidate_chunks = candidate.get("chunks") or []
    tracked_chunk_fields = (
        "text",
        "is_listen",
        "end_of_turn",
        "token_ids",
        "symbols",
        "decode",
    )
    reference_first = (
        {name: reference_chunks[0].get(name) for name in tracked_chunk_fields}
        if reference_chunks
        else None
    )
    candidate_first = (
        {name: candidate_chunks[0].get(name) for name in tracked_chunk_fields}
        if candidate_chunks
        else None
    )
    return {
        "all_tracked_fields_match": all(matches.values()),
        "field_matches": matches,
        "first_chunk_match": reference_first == candidate_first,
        "reference_first_chunk": reference_first,
        "candidate_first_chunk": candidate_first,
    }


def special_token_deltas(
    reference: dict[str, Any], candidate: dict[str, Any]
) -> dict[str, Any]:
    """Return signed logit/probability drift for shared special tokens."""
    reference_tokens = reference.get("special_tokens") or {}
    candidate_tokens = candidate.get("special_tokens") or {}
    result: dict[str, Any] = {}
    for symbol in sorted(set(reference_tokens) & set(candidate_tokens)):
        left = reference_tokens[symbol]
        right = candidate_tokens[symbol]
        result[symbol] = {
            "token_id": int(left["token_id"]),
            "reference_logit": float(left["logit"]),
            "current_logit": float(right["logit"]),
            "logit_delta": float(right["logit"] - left["logit"]),
            "reference_probability": float(left["probability"]),
            "current_probability": float(right["probability"]),
            "probability_delta": float(right["probability"] - left["probability"]),
        }
    return result


@contextmanager
def _capture_method_output(target: Any, name: str, sink: list[Any]) -> Iterator[None]:
    """Capture one encoder method result without a second encoder pass."""
    original = getattr(target, name, None)
    if original is None:
        yield
        return

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        sink.append(result)
        return result

    setattr(target, name, wrapped)
    try:
        yield
    finally:
        setattr(target, name, original)


def _flatten_visual_embeddings(value: Any) -> Any:
    while isinstance(value, (list, tuple)) and value:
        value = value[0]
    if value is None:
        return None
    if getattr(value, "ndim", 0) == 3:
        return value.reshape(-1, value.shape[-1]).detach().clone()
    if getattr(value, "ndim", 0) == 2:
        return value.detach().clone()
    raise RuntimeError("unexpected Realtime-Venus-Omni visual embedding shape")


def _copy_state(value: Any) -> Any:
    if isinstance(value, list):
        return [_copy_state(item) for item in value]
    if isinstance(value, deque):
        return deque((_copy_state(item) for item in value), maxlen=value.maxlen)
    if isinstance(value, dict):
        return {key: _copy_state(item) for (key, item) in value.items()}
    if isinstance(value, set):
        return {_copy_state(item) for item in value}
    if isinstance(value, tuple):
        return tuple((_copy_state(item) for item in value))
    clone = getattr(value, "clone", None)
    if callable(clone) and hasattr(value, "shape"):
        return clone()
    try:
        return copy.copy(value)
    except copy.Error:
        return value


def _capture_named_state(target: Any, names: Sequence[str]) -> dict[str, Any]:
    return {
        name: _copy_state(getattr(target, name))
        for name in names
        if hasattr(target, name)
    }


def _restore_named_state(target: Any, state: dict[str, Any]) -> None:
    for name, value in state.items():
        setattr(target, name, _copy_state(value))


def _snapshot_exact_named_state(target: Any, names: Sequence[str]) -> dict[str, Any]:
    """Clone named state while preserving whether each attribute exists."""
    return {
        name: (
            _copy_state(getattr(target, name))
            if hasattr(target, name)
            else _ABSENT_STATE
        )
        for name in names
    }


def _read_exact_named_state(target: Any, names: Sequence[str]) -> dict[str, Any]:
    """Read branch-owned references for a zero-copy context swap."""
    return {
        name: getattr(target, name) if hasattr(target, name) else _ABSENT_STATE
        for name in names
    }


def _restore_exact_named_state(
    target: Any, state: dict[str, Any], *, clone_values: bool
) -> None:
    """Restore values and delete attributes absent from the saved branch."""
    for name, value in state.items():
        if value is _ABSENT_STATE:
            if hasattr(target, name):
                delattr(target, name)
            continue
        setattr(target, name, _copy_state(value) if clone_values else value)


def _capture_rng_state(device: Any) -> dict[str, Any]:
    """Capture sampling state so query decoding cannot advance the live RNG."""
    state: dict[str, Any] = {"python": random.getstate()}
    try:
        import numpy as np
    except ImportError:
        pass
    else:
        state["numpy"] = np.random.get_state()
    try:
        import torch
    except ImportError:
        return state
    state["torch_cpu"] = torch.get_rng_state()
    if torch.cuda.is_available() and str(device).startswith("cuda"):
        state["torch_cuda_device"] = str(device)
        state["torch_cuda"] = torch.cuda.get_rng_state(device)
    return state


def _restore_rng_state(state: dict[str, Any]) -> None:
    """Restore every RNG backend captured by :func:`_capture_rng_state`."""
    random.setstate(state["python"])
    if "numpy" in state:
        try:
            import numpy as np
        except ImportError as error:
            raise RuntimeError(
                "NumPy disappeared while restoring branch RNG"
            ) from error
        np.random.set_state(state["numpy"])
    if "torch_cpu" not in state:
        return
    try:
        import torch
    except ImportError as error:
        raise RuntimeError("PyTorch disappeared while restoring branch RNG") from error
    torch.set_rng_state(state["torch_cpu"])
    if "torch_cuda" in state:
        torch.cuda.set_rng_state(state["torch_cuda"], device=state["torch_cuda_device"])


def _result_audio(result: dict[str, Any]) -> Any | None:
    for name in ("audio", "audio_waveform", "audio_wav", "wav"):
        if name in result:
            return result[name]
    return None


def _map_cache_tensors(cache: Any, transform: Any) -> Any:
    return _map_cache_key_values(
        cache, key_transform=transform, value_transform=transform
    )


def _map_cache_key_values(
    cache: Any, *, key_transform: Any, value_transform: Any
) -> Any:
    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        rebuilt = copy.copy(cache)
        rebuilt.key_cache = [key_transform(tensor) for tensor in cache.key_cache]
        rebuilt.value_cache = [value_transform(tensor) for tensor in cache.value_cache]
        return rebuilt
    if isinstance(cache, tuple):
        return tuple(
            ((key_transform(key), value_transform(value)) for (key, value) in cache)
        )
    if isinstance(cache, list):
        return [(key_transform(key), value_transform(value)) for (key, value) in cache]
    raise TypeError("unsupported KV cache representation")


def _move_tensor(tensor: Any, *, device: str, pin_cpu: bool) -> Any:
    moved = tensor.to(device=device)
    if pin_cpu and device == "cpu" and hasattr(moved, "pin_memory"):
        moved = moved.pin_memory()
    return moved


def _first_cache_key(cache: Any) -> Any:
    if hasattr(cache, "key_cache"):
        if not cache.key_cache:
            raise ValueError("KV cache has no initialized layers")
        return cache.key_cache[0]
    if isinstance(cache, (tuple, list)) and cache:
        return cache[0][0]
    raise TypeError("unsupported or empty KV cache representation")


def _cache_token_count(cache: Any) -> int:
    """Read the model cache sequence length without rebuilding layer views."""
    key = _first_cache_key(cache)
    if not hasattr(key, "shape") or len(key.shape) < 2:
        raise ValueError("KV cache key must expose a rank >= 2 shape")
    return int(key.shape[-2])


def _cache_is_on_device(cache: Any, device: Any) -> bool:
    """Return whether a model-generated cache already uses the target device."""
    current = getattr(_first_cache_key(cache), "device", None)
    if current is None:
        return False
    if current == device or str(current) == str(device):
        return True
    try:
        import torch

        return torch.device(current) == torch.device(device)
    except (ImportError, TypeError, ValueError, RuntimeError):
        return str(current) == str(device)


def _cache_layer_count(cache: Any) -> int:
    if hasattr(cache, "key_cache") and hasattr(cache, "value_cache"):
        if len(cache.key_cache) != len(cache.value_cache):
            raise ValueError("KV cache key/value layer counts differ")
        return len(cache.key_cache)
    if isinstance(cache, (tuple, list)):
        return len(cache)
    raise TypeError("unsupported KV cache representation")


def _call_integer_argument(
    args: Sequence[Any], kwargs: dict[str, Any], *, index: int, name: str
) -> int | None:
    value = kwargs.get(name, args[index] if len(args) > index else None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_rotary_embedding(duplex: Any, decoder: Any) -> Any | None:
    roots = (decoder, getattr(duplex, "model", None))
    paths = (
        "rotary_emb",
        "model.rotary_emb",
        "llm.model.rotary_emb",
        "llm.model.model.rotary_emb",
        "model.llm.model.rotary_emb",
    )
    for root in roots:
        if root is None:
            continue
        for path in paths:
            value = root
            try:
                for part in path.split("."):
                    value = getattr(value, part)
            except AttributeError:
                continue
            if callable(value):
                return value
    return None


def _find_token_embedder(duplex: Any, decoder: Any) -> Any | None:
    direct = getattr(decoder, "embed_token", None)
    if callable(direct):
        return direct
    roots = (decoder, getattr(duplex, "model", None))
    paths = (
        "embed_tokens",
        "model.embed_tokens",
        "llm.model.embed_tokens",
        "llm.model.model.embed_tokens",
    )
    for root in roots:
        if root is None:
            continue
        get_embeddings = getattr(root, "get_input_embeddings", None)
        if callable(get_embeddings):
            layer = get_embeddings()
            if callable(layer):
                return layer
        for path in paths:
            value = root
            try:
                for part in path.split("."):
                    value = getattr(value, part)
            except AttributeError:
                continue
            if callable(value):
                return value
    return None
