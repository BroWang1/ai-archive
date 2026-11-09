"""Minimal inference layers used by Cola2.

The module intentionally depends only on PyTorch.  It contains the dense
Qwen3-shaped token decoder, the TextVAE-style encoder/condition block and the
latent DiT block needed by the Full-DiT generation path.
"""

from __future__ import annotations

import math
from typing import Optional

import torch
import torch.nn.functional as F
from torch import nn


def additive_attention_mask(
    allowed: torch.Tensor, dtype: torch.dtype
) -> torch.Tensor:
    """Convert a boolean ``[B,Q,K]`` allow tensor to an SDPA bias."""

    if allowed.dtype is not torch.bool:
        allowed = allowed.bool()
    mask = torch.zeros(
        allowed.shape[0],
        1,
        allowed.shape[1],
        allowed.shape[2],
        dtype=dtype,
        device=allowed.device,
    )
    return mask.masked_fill(~allowed.unsqueeze(1), torch.finfo(dtype).min)


def causal_padding_allow(valid: torch.Tensor) -> torch.Tensor:
    """Causal attention with finite diagonal entries for padded queries."""

    valid = valid.bool()
    batch, length = valid.shape
    index = torch.arange(length, device=valid.device)
    allowed = valid[:, None, :] & (index[None, None, :] <= index[None, :, None])
    eye = torch.eye(length, dtype=torch.bool, device=valid.device)
    return allowed | eye.unsqueeze(0).expand(batch, -1, -1)


def block_causal_allow(
    valid: torch.Tensor, block_ids: torch.Tensor
) -> torch.Tensor:
    """Allow all valid keys in the query's block or an earlier block."""

    valid = valid.bool()
    allowed = valid[:, None, :] & (
        block_ids[:, None, :] <= block_ids[:, :, None]
    )
    length = valid.shape[1]
    eye = torch.eye(length, dtype=torch.bool, device=valid.device)
    return allowed | eye.unsqueeze(0)


def span_local_allow(valid: torch.Tensor, segment_ids: torch.Tensor) -> torch.Tensor:
    """Bidirectional attention inside each dynamic span."""

    valid = valid.bool()
    allowed = (
        valid[:, :, None]
        & valid[:, None, :]
        & (segment_ids[:, :, None] == segment_ids[:, None, :])
    )
    length = valid.shape[1]
    eye = torch.eye(length, dtype=torch.bool, device=valid.device)
    return allowed | eye.unsqueeze(0)


class RMSNorm(nn.Module):
    """Qwen/T5 style RMSNorm with a float32 variance reduction."""

    def __init__(self, hidden_size: int, eps: float = 1e-6) -> None:
        super().__init__()
        self.weight = nn.Parameter(torch.ones(hidden_size))
        self.variance_epsilon = float(eps)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        dtype = hidden_states.dtype
        states = hidden_states.float()
        variance = states.square().mean(dim=-1, keepdim=True)
        states = states * torch.rsqrt(variance + self.variance_epsilon)
        return states.to(dtype) * self.weight


def _rotate_half(x: torch.Tensor) -> torch.Tensor:
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def _rotate_every_two(x: torch.Tensor) -> torch.Tensor:
    first = x[..., 0::2]
    second = x[..., 1::2]
    return torch.stack((-second, first), dim=-1).flatten(-2)


def _rope_cos_sin(
    position_ids: torch.Tensor,
    rotary_dim: int,
    theta: float,
    dtype: torch.dtype,
    *,
    interleaved: bool,
) -> tuple[torch.Tensor, torch.Tensor]:
    inv_freq = 1.0 / (
        theta
        ** (
            torch.arange(
                0,
                rotary_dim,
                2,
                dtype=torch.float32,
                device=position_ids.device,
            )
            / rotary_dim
        )
    )
    freqs = position_ids.float().unsqueeze(-1) * inv_freq
    angles = (
        freqs.repeat_interleave(2, dim=-1)
        if interleaved
        else torch.cat((freqs, freqs), dim=-1)
    ).unsqueeze(1)
    return angles.cos().to(dtype), angles.sin().to(dtype)


def apply_rotary(
    query: torch.Tensor,
    key: torch.Tensor,
    query_positions: torch.Tensor,
    key_positions: Optional[torch.Tensor] = None,
    *,
    rotary_dim: Optional[int] = None,
    theta: float = 1_000_000.0,
    interleaved: bool = False,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Apply non-interleaved RoPE to ``[B,H,L,C]`` query and key."""

    key_positions = query_positions if key_positions is None else key_positions
    rotary_dim = int(rotary_dim or query.shape[-1])
    q_rot, q_pass = query[..., :rotary_dim], query[..., rotary_dim:]
    k_rot, k_pass = key[..., :rotary_dim], key[..., rotary_dim:]
    q_cos, q_sin = _rope_cos_sin(
        query_positions,
        rotary_dim,
        theta,
        q_rot.dtype,
        interleaved=interleaved,
    )
    k_cos, k_sin = _rope_cos_sin(
        key_positions,
        rotary_dim,
        theta,
        k_rot.dtype,
        interleaved=interleaved,
    )
    rotate = _rotate_every_two if interleaved else _rotate_half
    q_rot = q_rot * q_cos + rotate(q_rot) * q_sin
    k_rot = k_rot * k_cos + rotate(k_rot) * k_sin
    return torch.cat((q_rot, q_pass), dim=-1), torch.cat(
        (k_rot, k_pass), dim=-1
    )


def _repeat_kv(states: torch.Tensor, repeats: int) -> torch.Tensor:
    if repeats == 1:
        return states
    batch, heads, length, dim = states.shape
    return (
        states[:, :, None, :, :]
        .expand(batch, heads, repeats, length, dim)
        .reshape(batch, heads * repeats, length, dim)
    )


class Qwen3Attention(nn.Module):
    """Dense grouped-query attention with Qwen3-compatible parameter names."""

    def __init__(
        self,
        hidden_size: int,
        num_heads: int,
        num_key_value_heads: int,
        head_dim: int,
        *,
        norm_eps: float,
        rope_theta: float,
        attention_dropout: float,
    ) -> None:
        super().__init__()
        if num_heads % num_key_value_heads:
            raise ValueError("num_heads must be divisible by num_key_value_heads.")
        self.num_heads = int(num_heads)
        self.num_key_value_heads = int(num_key_value_heads)
        self.num_key_value_groups = self.num_heads // self.num_key_value_heads
        self.head_dim = int(head_dim)
        self.rope_theta = float(rope_theta)
        self.attention_dropout = float(attention_dropout)
        self.q_proj = nn.Linear(
            hidden_size, self.num_heads * self.head_dim, bias=False
        )
        self.k_proj = nn.Linear(
            hidden_size, self.num_key_value_heads * self.head_dim, bias=False
        )
        self.v_proj = nn.Linear(
            hidden_size, self.num_key_value_heads * self.head_dim, bias=False
        )
        self.o_proj = nn.Linear(
            self.num_heads * self.head_dim, hidden_size, bias=False
        )
        self.q_norm = RMSNorm(self.head_dim, eps=norm_eps)
        self.k_norm = RMSNorm(self.head_dim, eps=norm_eps)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        position_ids: torch.Tensor,
    ) -> torch.Tensor:
        batch, query_length, _ = hidden_states.shape
        query = self.q_proj(hidden_states).view(
            batch, query_length, self.num_heads, self.head_dim
        )
        key = self.k_proj(hidden_states).view(
            batch, query_length, self.num_key_value_heads, self.head_dim
        )
        value = self.v_proj(hidden_states).view(
            batch, query_length, self.num_key_value_heads, self.head_dim
        )
        query = self.q_norm(query).transpose(1, 2)
        key = self.k_norm(key).transpose(1, 2)
        value = value.transpose(1, 2)
        query, key = apply_rotary(
            query,
            key,
            position_ids,
            rotary_dim=self.head_dim,
            theta=self.rope_theta,
        )
        key = _repeat_kv(key, self.num_key_value_groups)
        value = _repeat_kv(value, self.num_key_value_groups)
        output = F.scaled_dot_product_attention(
            query,
            key,
            value,
            attn_mask=attention_mask.to(query.dtype),
            dropout_p=self.attention_dropout if self.training else 0.0,
        )
        output = output.transpose(1, 2).reshape(
            batch, query_length, self.num_heads * self.head_dim
        )
        return self.o_proj(output)


class Qwen3MLP(nn.Module):
    def __init__(self, hidden_size: int, intermediate_size: int) -> None:
        super().__init__()
        self.gate_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.up_proj = nn.Linear(hidden_size, intermediate_size, bias=False)
        self.down_proj = nn.Linear(intermediate_size, hidden_size, bias=False)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return self.down_proj(
            F.silu(self.gate_proj(hidden_states)) * self.up_proj(hidden_states)
        )


class Qwen3DecoderBlock(nn.Module):
    """One pre-norm dense Qwen3 decoder block."""

    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        num_heads: int,
        num_key_value_heads: int,
        head_dim: int,
        *,
        norm_eps: float,
        rope_theta: float,
        attention_dropout: float = 0.0,
        hidden_dropout: float = 0.0,
    ) -> None:
        super().__init__()
        self.self_attn = Qwen3Attention(
            hidden_size,
            num_heads,
            num_key_value_heads,
            head_dim,
            norm_eps=norm_eps,
            rope_theta=rope_theta,
            attention_dropout=attention_dropout,
        )
        self.mlp = Qwen3MLP(hidden_size, intermediate_size)
        self.input_layernorm = RMSNorm(hidden_size, eps=norm_eps)
        self.post_attention_layernorm = RMSNorm(hidden_size, eps=norm_eps)
        self.dropout = nn.Dropout(hidden_dropout)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        position_ids: torch.Tensor,
    ) -> torch.Tensor:
        residual = hidden_states
        hidden_states = self.self_attn(
            self.input_layernorm(hidden_states),
            attention_mask,
            position_ids,
        )
        hidden_states = residual + self.dropout(hidden_states)
        residual = hidden_states
        hidden_states = self.mlp(
            self.post_attention_layernorm(hidden_states)
        )
        return residual + self.dropout(hidden_states)


class SwiGLU(nn.Module):
    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        values, gates = hidden_states.chunk(2, dim=-1)
        return values * F.silu(gates)


class TextVAEBlock(nn.Module):
    """TextVAE transformer block used by encoder, pool and condition stacks."""

    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        num_heads: int,
        *,
        norm_eps: float,
        rope_theta: float,
        attention_dropout: float = 0.0,
        hidden_dropout: float = 0.0,
        norm_style: str = "reordered",
    ) -> None:
        super().__init__()
        if hidden_size % num_heads:
            raise ValueError("hidden_size must be divisible by num_heads.")
        if intermediate_size % 2:
            raise ValueError("TextVAE SwiGLU intermediate size must be even.")
        self.num_heads = int(num_heads)
        self.head_dim = hidden_size // num_heads
        self.rope_theta = float(rope_theta)
        self.attention_dropout = float(attention_dropout)
        self.norm_style = str(norm_style)
        self.norm_attn = nn.LayerNorm(hidden_size, eps=norm_eps)
        self.qkv_proj = nn.Linear(hidden_size, hidden_size * 3, bias=False)
        # The native TextVAE normalizes the concatenated head axis before
        # reshaping (unlike Qwen3, whose q/k norms are per-head).
        self.q_norm = nn.LayerNorm(hidden_size, eps=norm_eps)
        self.k_norm = nn.LayerNorm(hidden_size, eps=norm_eps)
        self.attn_out_proj = nn.Linear(hidden_size, hidden_size, bias=True)
        self.dropout_layer = nn.Dropout(hidden_dropout)
        self.norm_ffn = nn.LayerNorm(hidden_size, eps=norm_eps)
        self.ffn_proj = nn.Linear(hidden_size, intermediate_size, bias=True)
        self.ffn_act = SwiGLU()
        self.ffn_out = nn.Linear(intermediate_size // 2, hidden_size, bias=True)

    def _attention(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        position_ids: torch.Tensor,
    ) -> torch.Tensor:
        batch, length, hidden_size = hidden_states.shape
        query, key, value = self.qkv_proj(hidden_states).chunk(3, dim=-1)
        query = self.q_norm(query).view(
            batch, length, self.num_heads, self.head_dim
        )
        key = self.k_norm(key).view(
            batch, length, self.num_heads, self.head_dim
        )
        value = value.view(
            batch, length, self.num_heads, self.head_dim
        ).transpose(1, 2)
        query = query.transpose(1, 2)
        key = key.transpose(1, 2)
        query, key = apply_rotary(
            query,
            key,
            position_ids,
            rotary_dim=self.head_dim,
            theta=self.rope_theta,
        )
        output = F.scaled_dot_product_attention(
            query,
            key,
            value,
            attn_mask=attention_mask.to(query.dtype),
            dropout_p=self.attention_dropout if self.training else 0.0,
        )
        output = output.transpose(1, 2).reshape(batch, length, hidden_size)
        return self.attn_out_proj(output)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        position_ids: torch.Tensor,
    ) -> torch.Tensor:
        if self.norm_style == "pre":
            attention_input = self.norm_attn(hidden_states)
            hidden_states = hidden_states + self.dropout_layer(
                self._attention(
                    attention_input, attention_mask, position_ids
                )
            )
            residual = hidden_states
            hidden_states = self.norm_ffn(hidden_states)
            hidden_states = self.ffn_out(
                self.ffn_act(self.ffn_proj(hidden_states))
            )
            return residual + self.dropout_layer(hidden_states)

        attention = self._attention(
            hidden_states, attention_mask, position_ids
        )
        if self.norm_style == "reordered":
            attention = self.norm_attn(attention)
        elif self.norm_style == "post_legacy":
            hidden_states = self.norm_attn(hidden_states)
        else:
            raise ValueError(f"Unknown norm_style={self.norm_style!r}.")
        hidden_states = hidden_states + self.dropout_layer(attention)
        residual = hidden_states
        feed_forward = self.ffn_out(
            self.ffn_act(self.ffn_proj(hidden_states))
        )
        feed_forward = self.norm_ffn(feed_forward)
        return residual + self.dropout_layer(feed_forward)


def sinusoidal_timestep_embedding(
    timesteps: torch.Tensor, embedding_dim: int
) -> torch.Tensor:
    """Diffusers-compatible sinusoidal embedding used by the native DiT."""

    half = embedding_dim // 2
    exponent = -math.log(10_000.0) * torch.arange(
        half, dtype=torch.float32, device=timesteps.device
    )
    exponent = exponent / max(half, 1)
    frequencies = torch.exp(exponent)
    angles = timesteps.float().unsqueeze(-1) * frequencies.unsqueeze(0)
    embedding = torch.cat((angles.sin(), angles.cos()), dim=-1)
    if embedding_dim % 2:
        embedding = F.pad(embedding, (0, 1))
    return embedding


class TimestepEmbedding(nn.Module):
    def __init__(self, hidden_size: int, output_size: int) -> None:
        super().__init__()
        self.sinusoidal_dim = 256
        self.proj_in = nn.Linear(self.sinusoidal_dim, hidden_size)
        self.proj_hid = nn.Linear(hidden_size, hidden_size)
        self.proj_out = nn.Linear(hidden_size, output_size)

    def forward(self, timesteps: torch.Tensor) -> torch.Tensor:
        embedding = sinusoidal_timestep_embedding(
            timesteps.reshape(-1), self.sinusoidal_dim
        ).to(self.proj_in.weight.dtype)
        embedding = F.silu(self.proj_in(embedding))
        embedding = F.silu(self.proj_hid(embedding))
        return self.proj_out(embedding)


class AdaLN(nn.Module):
    """Adaptive LayerNorm with native Cola DiT parameter naming."""

    def __init__(self, hidden_size: int, layers: tuple[str, ...]) -> None:
        super().__init__()
        for layer in layers:
            setattr(
                self,
                f"{layer}_in",
                nn.Sequential(
                    nn.SiLU(),
                    nn.Linear(hidden_size, hidden_size * 2, bias=True),
                ),
            )
            if layer != "out":
                setattr(
                    self,
                    f"{layer}_out",
                    nn.Sequential(
                        nn.SiLU(),
                        nn.Linear(hidden_size, hidden_size, bias=True),
                    ),
                )

    def modulate(
        self,
        hidden_states: torch.Tensor,
        embedding: torch.Tensor,
        layer: str,
        norm: nn.Module,
    ) -> torch.Tensor:
        shift, scale = getattr(self, f"{layer}_in")(embedding).chunk(2, -1)
        return norm(hidden_states) * (1.0 + scale) + shift

    def residual(
        self,
        update: torch.Tensor,
        residual: torch.Tensor,
        embedding: torch.Tensor,
        layer: str,
    ) -> torch.Tensor:
        gate = getattr(self, f"{layer}_out")(embedding)
        return residual + update * gate


class DiTAttention(nn.Module):
    def __init__(
        self,
        hidden_size: int,
        num_heads: int,
        head_dim: int,
        rope_dim: int,
        *,
        norm_eps: float,
        rope_theta: float,
        attention_dropout: float,
    ) -> None:
        super().__init__()
        self.num_heads = int(num_heads)
        self.head_dim = int(head_dim)
        self.rope_dim = int(rope_dim)
        self.rope_theta = float(rope_theta)
        self.attention_dropout = float(attention_dropout)
        self.proj_qkv = nn.Linear(
            hidden_size, 3 * num_heads * head_dim, bias=False
        )
        self.proj_out = nn.Linear(
            num_heads * head_dim, hidden_size, bias=False
        )
        self.norm_q = nn.LayerNorm(head_dim, eps=norm_eps)
        self.norm_k = nn.LayerNorm(head_dim, eps=norm_eps)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        position_ids: torch.Tensor,
    ) -> torch.Tensor:
        batch, length, _ = hidden_states.shape
        qkv = self.proj_qkv(hidden_states).view(
            batch, length, 3, self.num_heads, self.head_dim
        )
        query, key, value = qkv.unbind(dim=2)
        query = self.norm_q(query).transpose(1, 2)
        key = self.norm_k(key).transpose(1, 2)
        value = value.transpose(1, 2)
        query, key = apply_rotary(
            query,
            key,
            position_ids,
            rotary_dim=self.rope_dim,
            theta=self.rope_theta,
            interleaved=True,
        )
        output = F.scaled_dot_product_attention(
            query,
            key,
            value,
            attn_mask=attention_mask.to(query.dtype),
            dropout_p=self.attention_dropout if self.training else 0.0,
        )
        output = output.transpose(1, 2).reshape(
            batch, length, self.num_heads * self.head_dim
        )
        return self.proj_out(output)


class DiTMLP(nn.Module):
    def __init__(self, hidden_size: int, intermediate_size: int) -> None:
        super().__init__()
        self.proj_in = nn.Linear(hidden_size, intermediate_size, bias=True)
        self.act = nn.GELU(approximate="tanh")
        self.proj_out = nn.Linear(intermediate_size, hidden_size, bias=True)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return self.proj_out(self.act(self.proj_in(hidden_states)))


class DiTBlock(nn.Module):
    def __init__(
        self,
        hidden_size: int,
        intermediate_size: int,
        num_heads: int,
        head_dim: int,
        rope_dim: int,
        *,
        norm_eps: float,
        rope_theta: float,
        attention_dropout: float,
    ) -> None:
        super().__init__()
        self.msa_norm = nn.LayerNorm(
            hidden_size, eps=norm_eps, elementwise_affine=False
        )
        self.msa = DiTAttention(
            hidden_size,
            num_heads,
            head_dim,
            rope_dim,
            norm_eps=norm_eps,
            rope_theta=rope_theta,
            attention_dropout=attention_dropout,
        )
        self.mlp_norm = nn.LayerNorm(
            hidden_size, eps=norm_eps, elementwise_affine=False
        )
        self.mlp = DiTMLP(hidden_size, intermediate_size)
        self.ada = AdaLN(hidden_size, ("msa", "mlp"))

    def forward(
        self,
        hidden_states: torch.Tensor,
        embedding: torch.Tensor,
        attention_mask: torch.Tensor,
        position_ids: torch.Tensor,
    ) -> torch.Tensor:
        attention_input = self.ada.modulate(
            hidden_states, embedding, "msa", self.msa_norm
        )
        attention_output = self.msa(
            attention_input, attention_mask, position_ids
        )
        hidden_states = self.ada.residual(
            attention_output, hidden_states, embedding, "msa"
        )
        mlp_input = self.ada.modulate(
            hidden_states, embedding, "mlp", self.mlp_norm
        )
        mlp_output = self.mlp(mlp_input)
        return self.ada.residual(
            mlp_output, hidden_states, embedding, "mlp"
        )


class DurationHead(nn.Module):
    def __init__(self, hidden_size: int, intermediate_size: int, lmax: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(hidden_size, intermediate_size),
            nn.SiLU(),
            nn.Linear(intermediate_size, lmax),
        )

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return self.net(hidden_states)


class HardDurationExpander(nn.Module):
    """Repeat latent conditions by duration and add a local-position feature."""

    def __init__(
        self, hidden_size: int, output_size: int, local_position_dim: int
    ) -> None:
        super().__init__()
        self.output_size = int(output_size)
        self.loc_mlp = nn.Sequential(
            nn.Linear(3, local_position_dim),
            nn.SiLU(),
            nn.Linear(local_position_dim, local_position_dim),
        )
        self.cond_proj = nn.Linear(
            hidden_size + local_position_dim, output_size
        )

    def forward(
        self, hidden_states: torch.Tensor, lengths: torch.Tensor
    ) -> torch.Tensor:
        """Expand one unpadded latent row into token-aligned conditions."""

        if hidden_states.ndim != 2 or lengths.ndim != 1:
            raise ValueError("Expander expects hidden [K,D] and lengths [K].")
        if hidden_states.shape[0] != lengths.shape[0]:
            raise ValueError("Each latent needs exactly one duration.")
        pieces = []
        for latent, length_tensor in zip(hidden_states, lengths, strict=True):
            length = int(length_tensor.item())
            if length <= 0:
                continue
            positions = torch.arange(
                1,
                length + 1,
                dtype=hidden_states.dtype,
                device=hidden_states.device,
            )
            length_f = positions.new_full((length,), float(length))
            local_features = torch.stack(
                (
                    positions / length_f,
                    (length_f - positions) / length_f,
                    length_f.log(),
                ),
                dim=-1,
            )
            local = self.loc_mlp(local_features)
            repeated = latent.unsqueeze(0).expand(length, -1)
            pieces.append(self.cond_proj(torch.cat((repeated, local), dim=-1)))
        if not pieces:
            return hidden_states.new_zeros((0, self.output_size))
        return torch.cat(pieces, dim=0)
