"""Fused QB routing: select on logits - beta, weight with sigmoid(logits).

Both paths break ties by lowest expert index; HF torch.topk leaves ties
unspecified. FP32 weights are numerically close, not guaranteed bit-identical.
Optional local expert ids require the dispatcher to skip its own mapping.
"""

from __future__ import annotations

from typing import Optional, Tuple

import torch

try:
    import triton
    import triton.language as tl

    _HAS_TRITON = True
except ImportError:  # pragma: no cover - Triton ships with every CUDA build
    triton = None
    tl = None
    _HAS_TRITON = False

# One Triton block must span the whole expert axis so the top-k passes stay
# inside a single reduction tree.
_MAX_FUSED_EXPERTS = 4096


if _HAS_TRITON:

    @triton.jit
    def _gate_gemv_kernel(x_ptr, w_ptr, out_ptr, K, N,
                          BLOCK_N: tl.constexpr, BLOCK_K: tl.constexpr):
        """One expert's logit per program: dot(bf16 activations, fp32 weights)."""
        pid_n = tl.program_id(0)
        offs_n = pid_n * BLOCK_N + tl.arange(0, BLOCK_N)
        mask_n = offs_n < N
        acc = tl.zeros([BLOCK_N, BLOCK_K], tl.float32)
        for k0 in range(0, K, BLOCK_K):
            offs_k = k0 + tl.arange(0, BLOCK_K)
            mask_k = offs_k < K
            # Widening happens in registers.  bf16 -> fp32 is exact, so this
            # forms the same products as the eager path; only the order the
            # partial sums are combined in differs.
            x = tl.load(x_ptr + offs_k, mask=mask_k, other=0.0).to(tl.float32)
            w = tl.load(w_ptr + offs_n[:, None] * K + offs_k[None, :],
                        mask=mask_n[:, None] & mask_k[None, :], other=0.0)
            acc += w * x[None, :]
        tl.store(out_ptr + offs_n, tl.sum(acc, axis=1), mask=mask_n)


def gate_gemv(
    hidden_states: torch.Tensor, weight: torch.Tensor
) -> Optional[torch.Tensor]:
    """Single-token FP32 router GEMV; other shapes use the caller\'s linear op."""

    if not _HAS_TRITON or hidden_states.device.type != "cuda":
        return None
    if hidden_states.dim() != 2 or hidden_states.shape[0] != 1:
        return None
    if weight.ndim != 2 or weight.device != hidden_states.device:
        return None
    if weight.dtype != torch.float32 or not weight.is_contiguous():
        return None
    if not hidden_states.is_contiguous():
        return None

    num_experts, hidden_size = weight.shape
    if hidden_states.shape[1] != hidden_size:
        return None

    out = torch.empty(
        (1, num_experts), dtype=torch.float32, device=hidden_states.device
    )
    _gate_gemv_kernel[(num_experts,)](
        hidden_states,
        weight,
        out,
        hidden_size,
        num_experts,
        BLOCK_N=1,
        BLOCK_K=1024,
        num_warps=8,
    )
    return out


def select_bias_rows(
    bias: torch.Tensor,
    num_tokens: int,
    modality_id: Optional[torch.Tensor],
) -> torch.Tensor:
    """Expand a ``[E]`` vector or ``[2, E]`` modality table to what routing reads.

    ``modality_id`` is the flattened per-token flag (0=text, 1=vision,
    -1=padding), so anything that is not exactly 1 routes as text.
    """

    if bias.dim() != 2:
        return bias
    if modality_id is None:
        return bias[0]
    modality_id = modality_id.reshape(-1).to(device=bias.device)
    if modality_id.shape[0] != num_tokens:
        raise ValueError(
            "modality_id must align with router logits, got "
            f"{tuple(modality_id.shape)} vs ({num_tokens},)"
        )
    return bias.index_select(0, (modality_id == 1).long())


def to_local_expert_ids(
    topk_ids: torch.Tensor, local_expert_range: Tuple[int, int]
) -> torch.Tensor:
    """Global -> local expert ids, matching ``StandardDispatcher``'s table.

    That table is ``arange(count)`` over ``[base, base + count)`` and -1
    everywhere else, so the translation is affine and needs no gather.
    """

    base, count = local_expert_range
    local = topk_ids.to(torch.int32) - base
    return torch.where(
        (local >= 0) & (local < count), local, torch.full_like(local, -1)
    )


def qb_route_reference(
    router_logits: torch.Tensor,
    qb_beta: torch.Tensor,
    modality_id: Optional[torch.Tensor],
    top_k: int,
    renormalize: bool,
    scaling: Optional[float],
    local_expert_range: Optional[Tuple[int, int]] = None,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Reference QB routing: select on raw logits, weight with the sigmoid."""

    logits = router_logits.float()
    bias = select_bias_rows(qb_beta, logits.shape[0], modality_id).float()
    adjusted = logits - (bias if bias.dim() == 2 else bias.unsqueeze(0))
    # A stable sort gives the same explicit tie rule as the fused kernel.
    topk_ids = torch.argsort(adjusted, dim=-1, descending=True, stable=True)[:, :top_k]
    topk_weights = logits.sigmoid().gather(1, topk_ids)
    if renormalize:
        topk_weights = topk_weights / (
            topk_weights.sum(dim=-1, keepdim=True) + 1e-20
        )
    if scaling is not None:
        topk_weights = topk_weights * scaling
    topk_ids = topk_ids.to(torch.int32)
    if local_expert_range is not None:
        topk_ids = to_local_expert_ids(topk_ids, local_expert_range)
    return topk_weights.to(torch.float32), topk_ids


if _HAS_TRITON:

    @triton.jit
    def _qb_route_kernel(
        logits_ptr,
        beta_ptr,
        modality_ptr,
        weights_ptr,
        ids_ptr,
        num_experts,
        scaling,
        expert_base,
        num_local_experts,
        TOP_K: tl.constexpr,
        BLOCK_E: tl.constexpr,
        BLOCK_K: tl.constexpr,
        HAS_MODALITY: tl.constexpr,
        RENORMALIZE: tl.constexpr,
        REMAP_LOCAL: tl.constexpr,
    ):
        token = tl.program_id(0)
        offs = tl.arange(0, BLOCK_E)
        offs_k = tl.arange(0, BLOCK_K)
        mask = offs < num_experts

        logits = tl.load(
            logits_ptr + token * num_experts + offs, mask=mask, other=0.0
        ).to(tl.float32)

        if HAS_MODALITY:
            bias_row = (tl.load(modality_ptr + token) == 1).to(tl.int32)
        else:
            bias_row = 0
        beta = tl.load(
            beta_ptr + bias_row * num_experts + offs, mask=mask, other=0.0
        ).to(tl.float32)

        # Selection happens on the raw logits; masked lanes must never win.
        work = tl.where(mask, logits - beta, float("-inf"))
        scores = tl.sigmoid(logits)
        available = mask

        # Winners are accumulated into a [BLOCK_K] register array rather than
        # marked in a [BLOCK_E] rank vector.  Both forms run the same TOP_K
        # rounds, but this one keeps the renormalize sum and the two stores on
        # 8 lanes instead of spreading them across all 256 -- the earlier
        # version issued a BLOCK_E-wide masked scatter to write 8 values.
        # Exact ties resolve to the lowest expert index; torch.topk leaves its
        # own tie-breaking unspecified, so the two can only disagree when two
        # fp32 gate logits land on the same bit pattern.
        sel_w = tl.zeros([BLOCK_K], tl.float32)
        sel_i = tl.zeros([BLOCK_K], tl.int32)
        for i in tl.static_range(TOP_K):
            best = tl.max(work, axis=0)
            winner = tl.min(
                tl.where(available & (work == best), offs, num_experts), axis=0
            )
            win_score = tl.sum(tl.where(offs == winner, scores, 0.0), axis=0)
            slot = offs_k == i
            sel_w = tl.where(slot, win_score, sel_w)
            sel_i = tl.where(slot, winner, sel_i)
            available = available & (offs != winner)
            work = tl.where(available, work, float("-inf"))

        if RENORMALIZE:
            sel_w = sel_w / (tl.sum(sel_w, axis=0) + 1e-20)
        sel_w = sel_w * scaling

        # Experts this rank does not own become -1, the drop sentinel the
        # triton runner already honours -- the same tensor StandardDispatcher
        # would have produced by gathering through its mapping table.
        if REMAP_LOCAL:
            sel_i = sel_i - expert_base
            sel_i = tl.where((sel_i >= 0) & (sel_i < num_local_experts), sel_i, -1)

        store_mask = offs_k < TOP_K
        tl.store(weights_ptr + token * TOP_K + offs_k, sel_w, mask=store_mask)
        tl.store(ids_ptr + token * TOP_K + offs_k, sel_i.to(tl.int32), mask=store_mask)


def _kernel_applicable(
    router_logits: torch.Tensor, qb_beta: torch.Tensor, top_k: int
) -> bool:
    if not _HAS_TRITON or not router_logits.is_cuda:
        return False
    if router_logits.dim() != 2:
        return False
    num_experts = router_logits.shape[-1]
    return (
        router_logits.dim() == 2
        and router_logits.shape[0] > 0
        and qb_beta.dim() in (1, 2)
        and qb_beta.shape[-1] == num_experts
        and (qb_beta.dim() == 1 or qb_beta.shape[0] == 2)
        and 0 < top_k <= num_experts
        and num_experts <= _MAX_FUSED_EXPERTS
    )


def qb_route(
    router_logits: torch.Tensor,
    qb_beta: torch.Tensor,
    modality_id: Optional[torch.Tensor],
    top_k: int,
    renormalize: bool,
    scaling: Optional[float],
    local_expert_range: Optional[Tuple[int, int]] = None,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """Fused QB routing; returns ``(topk_weights fp32, topk_ids int32)``.

    With ``local_expert_range`` the ids come out already translated to this
    rank's local numbering, which is only correct if the caller has also told
    the dispatcher to skip its own translation.
    """

    if router_logits.dim() != 2 or not 0 < top_k <= router_logits.shape[1]:
        raise ValueError("QB routing requires [tokens, experts] and 0 < top_k <= experts")
    if (
        qb_beta.ndim not in (1, 2)
        or qb_beta.shape[-1] != router_logits.shape[1]
        or (qb_beta.ndim == 2 and qb_beta.shape[0] != 2)
        or qb_beta.device != router_logits.device
    ):
        raise ValueError("qb_beta must be [experts] or [2, experts] on the logits device")
    if not _kernel_applicable(router_logits, qb_beta, top_k):
        return qb_route_reference(
            router_logits,
            qb_beta,
            modality_id,
            top_k,
            renormalize,
            scaling,
            local_expert_range,
        )

    num_tokens, num_experts = router_logits.shape
    logits = router_logits.float().contiguous()
    beta = qb_beta.float().contiguous()
    has_modality = beta.dim() == 2 and modality_id is not None

    if has_modality:
        modality_id = modality_id.reshape(-1).to(device=logits.device)
        if modality_id.shape[0] != num_tokens:
            raise ValueError(
                "modality_id must align with router logits, got "
                f"{tuple(modality_id.shape)} vs ({num_tokens},)"
            )
        modality_id = modality_id.contiguous()
    elif beta.dim() == 2:
        # No modality signal: every token routes on the text row.
        beta = beta[0].contiguous()

    topk_weights = torch.empty(
        (num_tokens, top_k), dtype=torch.float32, device=logits.device
    )
    topk_ids = torch.empty(
        (num_tokens, top_k), dtype=torch.int32, device=logits.device
    )
    block_e = triton.next_power_of_2(num_experts)
    _qb_route_kernel[(num_tokens,)](
        logits,
        beta,
        modality_id if has_modality else logits,
        topk_weights,
        topk_ids,
        num_experts,
        1.0 if scaling is None else float(scaling),
        0 if local_expert_range is None else local_expert_range[0],
        0 if local_expert_range is None else local_expert_range[1],
        TOP_K=top_k,
        BLOCK_E=block_e,
        BLOCK_K=triton.next_power_of_2(top_k),
        HAS_MODALITY=has_modality,
        RENORMALIZE=renormalize,
        REMAP_LOCAL=local_expert_range is not None,
        # The kernel body is TOP_K sequential max/min reductions over the expert
        # axis.  On a single warp those lower to register shuffles; with more
        # warps each pass has to round-trip through shared memory and hit a
        # barrier, which at this expert count costs more than the extra lanes
        # return.  SGLang's own router kernel picks the same way
        # (kernels/ops/moe/moe_fused_gate.py: ``num_warps = 1 if BLOCK_N <= 512``),
        # and its 2.8 us/launch against our 4.0 is what prompted the change.
        num_warps=1 if block_e <= 512 else 4,
    )
    return topk_weights, topk_ids


__all__ = [
    "gate_gemv",
    "qb_route",
    "qb_route_reference",
    "select_bias_rows",
    "to_local_expert_ids",
]
