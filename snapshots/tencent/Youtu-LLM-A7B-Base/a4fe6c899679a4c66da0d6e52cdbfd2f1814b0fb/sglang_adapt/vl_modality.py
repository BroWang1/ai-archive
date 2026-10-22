# SPDX-License-Identifier: Apache-2.0
"""Graph-stable modality masks matching the checkpoint's training granularity.

Sample-level router bias applies to every token of a multimodal request.
Token-level bias and dual shared experts apply only to image/video tokens.
When both granularities are needed, the router and shared branch use separate
buffers; CUDA graph replay refreshes both before launch.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import torch

MODALITY_TEXT = 0
MODALITY_VISION = 1

GRANULARITY_SAMPLE = "sample"
GRANULARITY_TOKEN = "token"


class VLModality:
    """Owns the graph-stable id buffer and the ForwardBatch derivation."""

    def __init__(self) -> None:
        self._buffer: Optional[torch.Tensor] = None
        self._staging: Optional[torch.Tensor] = None
        self._capacity = 0
        self._copy_done = None
        self._granularity = GRANULARITY_SAMPLE
        self._image_token_id: Optional[int] = None
        self._video_token_id: Optional[int] = None

    # ── setup ────────────────────────────────────────────────────────────────
    def enable(
        self,
        capacity: int,
        device: torch.device,
        granularity: str = GRANULARITY_SAMPLE,
        image_token_id: Optional[int] = None,
        video_token_id: Optional[int] = None,
    ) -> None:
        """Allocate once, before any capture, so the address stays valid."""
        if granularity not in (GRANULARITY_SAMPLE, GRANULARITY_TOKEN):
            raise ValueError(f"unknown modality granularity {granularity!r}")
        if capacity <= 0:
            raise ValueError("modality capacity must be positive")
        if self._buffer is not None:
            if (
                self._buffer.device != torch.device(device)
                or self._capacity < capacity
                or self._granularity != granularity
                or self._image_token_id != image_token_id
                or self._video_token_id != video_token_id
            ):
                raise ValueError("Cannot reconfigure a graph-stable modality buffer")
            return
        self._granularity = granularity
        self._image_token_id = (
            None if image_token_id is None else int(image_token_id)
        )
        self._video_token_id = (
            None if video_token_id is None else int(video_token_id)
        )
        self._capacity = int(capacity)
        self._buffer = torch.zeros(self._capacity, dtype=torch.int8, device=device)
        staging = torch.zeros(self._capacity, dtype=torch.int8)
        try:
            staging = staging.pin_memory()
        except RuntimeError:
            pass
        self._staging = staging
        if staging.is_pinned() and self._buffer.is_cuda:
            self._copy_done = torch.cuda.Event()

    @property
    def enabled(self) -> bool:
        return self._buffer is not None

    @property
    def granularity(self) -> str:
        return self._granularity

    def _check_capacity(self, num_tokens: int) -> None:
        if num_tokens > self._capacity:
            raise ValueError(
                f"VL modality buffer capacity {self._capacity} < {num_tokens} tokens; "
                "increase the capacity before CUDA graph capture."
            )

    # ── sample-level derivation ──────────────────────────────────────────────
    @staticmethod
    def _sample_flags(forward_batch) -> Optional[np.ndarray]:
        """Per-token VL-sample flags, or None when every token is text."""
        mm_inputs = getattr(forward_batch, "mm_inputs", None)
        if not mm_inputs:
            return None
        req_flags = np.fromiter(
            (MODALITY_TEXT if item is None else MODALITY_VISION for item in mm_inputs),
            dtype=np.int8,
            count=len(mm_inputs),
        )
        if not req_flags.any():
            return None
        lens = getattr(forward_batch, "extend_seq_lens_cpu", None)
        if lens is not None:
            if len(lens) != req_flags.shape[0]:
                raise ValueError("extend lengths must align with multimodal requests")
            return np.repeat(req_flags, np.asarray(lens, dtype=np.int64))
        spec_info = getattr(forward_batch, "spec_info", None)
        tokens_per_req = getattr(spec_info, "num_tokens_per_req", 1)
        if tokens_per_req < 1:
            raise ValueError("speculative modality routing needs num_tokens_per_req")
        return np.repeat(req_flags, tokens_per_req)

    @staticmethod
    def _fit(flags: np.ndarray, num_tokens: int) -> np.ndarray:
        if flags.shape[0] == num_tokens:
            return flags
        if flags.shape[0] > num_tokens:
            raise ValueError("sample modality flags exceed the token count")
        out = np.zeros(num_tokens, dtype=np.int8)
        out[: flags.shape[0]] = flags
        return out

    # ── token-level derivation ───────────────────────────────────────────────
    def _token_ids(self, forward_batch, num_tokens: int) -> Optional[torch.Tensor]:
        """Vision flags for the placeholder tokens themselves, on device.

        Derived from input_ids rather than mm_inputs because the distinction
        being made is within a sequence, not between requests.  SGLang has
        already swapped the placeholder *embeddings* by the time the language
        model runs, but input_ids still line up with the flattened hidden
        states, so the placeholders remain findable.
        """
        input_ids = getattr(forward_batch, "input_ids", None)
        if input_ids is None or input_ids.numel() == 0:
            return None
        ids = input_ids[:num_tokens]

        mask = None
        if self._image_token_id is not None:
            mask = ids == self._image_token_id
        if self._video_token_id is not None:
            hit = ids == self._video_token_id
            mask = hit if mask is None else (mask | hit)

        # pad_input_ids may have replaced the placeholder spans with per-item
        # pad_value sentinels before batching, in which case the raw token ids
        # above match nothing.  The mm_items are still aligned, so their
        # sentinels recover the spans without needing per-request offsets.
        mm_inputs = getattr(forward_batch, "mm_inputs", None) or ()
        pad_values = []
        for mm_input in mm_inputs:
            if mm_input is None:
                continue
            for item in getattr(mm_input, "mm_items", None) or ():
                if getattr(item, "pad_value", None) is None:
                    continue
                if self._is_visual(item):
                    pad_values.append(int(item.pad_value))
        for value in set(pad_values):
            hit = ids == value
            mask = hit if mask is None else (mask | hit)

        if mask is None:
            return None
        return mask.to(torch.int8)

    @staticmethod
    def _is_visual(item) -> bool:
        try:
            from sglang.srt.managers.schedule_batch import Modality
        except ImportError:  # pragma: no cover - SGLang always provides this
            return True
        return getattr(item, "modality", None) in (Modality.IMAGE, Modality.VIDEO)

    # ── per-iteration ────────────────────────────────────────────────────────
    def fill(self, forward_batch, raw_num_tokens: int, padded_num_tokens: int) -> None:
        """Refresh the graph-resident buffer for the batch about to be launched."""
        buf = self._buffer
        if buf is None:
            return
        if not 0 <= raw_num_tokens <= padded_num_tokens:
            raise ValueError("Expected 0 <= raw_num_tokens <= padded_num_tokens")
        self._check_capacity(padded_num_tokens)

        if self._granularity == GRANULARITY_TOKEN:
            ids = self._token_ids(forward_batch, raw_num_tokens)
            if ids is None:
                buf[:padded_num_tokens].zero_()
                return
            n = ids.shape[0]
            buf[:n].copy_(ids, non_blocking=True)
            if n < padded_num_tokens:
                buf[n:padded_num_tokens].zero_()
            return

        flags = self._sample_flags(forward_batch)
        if flags is None:
            buf[:padded_num_tokens].zero_()
            return
        flags = self._fit(flags, raw_num_tokens)
        n = flags.shape[0]
        # Overlap scheduling can reach the next CPU fill before the previous
        # asynchronous H2D copy has finished reading this pinned allocation.
        if self._copy_done is not None:
            self._copy_done.synchronize()
        self._staging[:n].copy_(torch.from_numpy(flags))
        buf[:n].copy_(self._staging[:n], non_blocking=True)
        if self._copy_done is not None:
            self._copy_done.record(torch.cuda.current_stream(buf.device))
        if n < padded_num_tokens:
            buf[n:padded_num_tokens].zero_()

    def graph_view(self, num_tokens: int) -> Optional[torch.Tensor]:
        """The slice a captured graph reads; None disables modality routing."""
        buf = self._buffer
        if buf is None:
            return None
        self._check_capacity(num_tokens)
        return buf[:num_tokens]

    def eager_ids(
        self, forward_batch, num_tokens: int, device: torch.device
    ) -> Optional[torch.Tensor]:
        if self._granularity == GRANULARITY_TOKEN:
            ids = self._token_ids(forward_batch, num_tokens)
            if ids is None:
                return None
            if ids.shape[0] < num_tokens:
                padded = torch.zeros(num_tokens, dtype=torch.int8, device=ids.device)
                padded[: ids.shape[0]] = ids
                ids = padded
            return ids.to(device=device, non_blocking=True)

        flags = self._sample_flags(forward_batch)
        if flags is None:
            return None
        return torch.from_numpy(self._fit(flags, num_tokens)).to(
            device=device, non_blocking=True
        )


def modality_granularity(config) -> Optional[str]:
    """Router training mask, or the shared-expert mask if the router has none."""
    if getattr(config, "moe_router_modality_aware_expert_bias", False):
        return (
            GRANULARITY_TOKEN
            if getattr(config, "moe_router_token_level_modality", False)
            else GRANULARITY_SAMPLE
        )
    if getattr(config, "enable_multimodal_shared_experts", False):
        return GRANULARITY_TOKEN
    return None


VL_MODALITY = VLModality()
VL_SHARED_MODALITY = VLModality()
