"""BF16 output gating and exact RoPE layout permutation with eager fallbacks."""

from __future__ import annotations

from typing import Optional

import torch

try:
    import triton
    import triton.language as tl

    _HAS_TRITON = True
except ImportError:  # pragma: no cover - Triton ships with every CUDA build
    triton = None
    tl = None
    _HAS_TRITON = False


if _HAS_TRITON:

    @triton.jit
    def _sigmoid_gate_mul_kernel(x_ptr, g_ptr, out_ptr, H, D,
                                 BLOCK_D: tl.constexpr):
        pid_t = tl.program_id(0)
        pid_h = tl.program_id(1)
        g = tl.load(g_ptr + pid_t * H + pid_h).to(tl.float32)
        g = tl.sigmoid(g)
        # Round to the activation dtype before multiplying.  The eager chain
        # does this via `.to(dtype=x.dtype)`, and skipping it would be more
        # accurate but no longer bit-identical.
        g = g.to(x_ptr.dtype.element_ty).to(tl.float32)
        offs = tl.arange(0, BLOCK_D)
        mask = offs < D
        base = pid_t * H * D + pid_h * D
        x = tl.load(x_ptr + base + offs, mask=mask, other=0.0).to(tl.float32)
        tl.store(out_ptr + base + offs, (x * g).to(out_ptr.dtype.element_ty),
                 mask=mask)


if _HAS_TRITON:

    @triton.jit
    def _deinterleave_pair_kernel(q_ptr, k_ptr, qo_ptr, ko_ptr, HQ, D,
                                  BLOCK_D: tl.constexpr):
        pid = tl.program_id(0)
        half = D // 2
        offs = tl.arange(0, BLOCK_D)
        mask = offs < half
        # Destination lane i takes source lane 2i; lane half + i takes 2i + 1.
        src_even = offs * 2
        src_odd = offs * 2 + 1
        if pid < HQ:
            base = pid * D
            e = tl.load(q_ptr + base + src_even, mask=mask, other=0.0)
            o = tl.load(q_ptr + base + src_odd, mask=mask, other=0.0)
            tl.store(qo_ptr + base + offs, e, mask=mask)
            tl.store(qo_ptr + base + half + offs, o, mask=mask)
        else:
            base = (pid - HQ) * D
            e = tl.load(k_ptr + base + src_even, mask=mask, other=0.0)
            o = tl.load(k_ptr + base + src_odd, mask=mask, other=0.0)
            tl.store(ko_ptr + base + offs, e, mask=mask)
            tl.store(ko_ptr + base + half + offs, o, mask=mask)


def deinterleave_rope_pair(q: torch.Tensor, k: torch.Tensor):
    """``cat((x[..., 0::2], x[..., 1::2]), -1)`` for Q and K in one launch.

    Returns ``(q_out, k_out)`` or ``None`` if the shapes are not handled.

    This is the Megatron-interleaved to half-and-half RoPE layout conversion,
    run once per MLA layer on each of Q and K.  At bs=1 with TP8 that is 640
    bytes across both tensors and 24 launches per token, measured at 36.2 us --
    all of it launch cost.  Doing both tensors in one kernel takes 3.17 us to
    1.10 (bench_mrope_deinterleave.py).

    No dtype restriction: this moves elements without computing on them, so the
    result is the same bits for any dtype.
    """

    if not _HAS_TRITON or q.device.type != "cuda":
        return None
    if q.dim() != 3 or k.dim() != 3:
        return None
    if not q.is_contiguous() or not k.is_contiguous():
        return None
    if q.device != k.device or q.dtype != k.dtype or q.shape[-1] != k.shape[-1]:
        return None
    dim = q.shape[-1]
    if dim % 2 or dim == 0:
        return None

    rows_q = q.shape[0] * q.shape[1]
    rows_k = k.shape[0] * k.shape[1]
    if rows_q == 0 or rows_k == 0:
        return None

    q_out = torch.empty_like(q)
    k_out = torch.empty_like(k)
    _deinterleave_pair_kernel[(rows_q + rows_k,)](
        q,
        k,
        q_out,
        k_out,
        rows_q,
        dim,
        BLOCK_D=triton.next_power_of_2(dim // 2),
        num_warps=1,
    )
    return q_out, k_out


def sigmoid_gate_mul(
    x: torch.Tensor, gate: torch.Tensor, num_heads: int, head_dim: int
) -> Optional[torch.Tensor]:
    """``(x.view(-1, H, D) * sigmoid(gate.float()).to(x.dtype)[..., None]).flatten(-2)``

    Returns ``None`` if the shapes or placement are not handled, so the caller
    keeps the eager expression as its fallback.

    The eager form is four launches -- widen, sigmoid, narrow, multiply -- and
    at bs=1 with TP8 they move about 1 KB between them, so all four are latency.
    Fusing them measures 1.11 us against 5.78 (bench_mla_output_gate.py).

    On the exactness, precisely: ``tl.sigmoid`` and ``torch.sigmoid`` can
    disagree by one fp32 ulp, so this is not bit-identical by construction.
    What rescues it is the ``.to(dtype=x.dtype)`` the eager chain performs
    before multiplying, reproduced above -- bf16 keeps 8 mantissa bits, coarse
    enough that a 1-ulp fp32 difference never reached a different bf16 value in
    any case tested, including 4096-token draws.  fp16 is not so lucky (2 of 6
    large-token cases differ by one fp16 ulp) and fp32 has no narrowing round at
    all, so both are declined and fall back to the eager chain.  Attention
    outputs here are bf16, so the fast path is the one the model takes.
    """

    if not _HAS_TRITON or x.device.type != "cuda":
        return None
    if x.device != gate.device or num_heads <= 0 or head_dim <= 0:
        return None
    if x.dtype is not torch.bfloat16:
        return None
    if x.dim() != 2 or gate.dim() != 2:
        return None
    if not x.is_contiguous() or not gate.is_contiguous():
        return None
    tokens = x.shape[0]
    if x.shape[1] != num_heads * head_dim:
        return None
    if gate.shape[0] != tokens or gate.shape[1] != num_heads:
        return None
    if tokens == 0:
        return x

    out = torch.empty_like(x)
    _sigmoid_gate_mul_kernel[(tokens, num_heads)](
        x,
        gate,
        out,
        num_heads,
        head_dim,
        BLOCK_D=triton.next_power_of_2(head_dim),
        num_warps=4,
    )
    return out
