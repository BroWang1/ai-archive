# Copyright 2025 The StepFun and HuggingFace Inc. team. All rights reserved.
# Licensed under the Apache License, Version 2.0.
"""Step-5 perception encoder; parameter names match the released checkpoint."""
from __future__ import annotations

from typing import Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers.activations import ACT2FN
from transformers.configuration_utils import PretrainedConfig


class Step5VisionConfig(PretrainedConfig):
    model_type = "perception_encoder"

    def __init__(
        self,
        width=1536,
        layers=47,
        heads=16,
        num_channels=3,
        image_size=728,
        mlp_ratio=8960 / 1536,
        patch_size=14,
        hidden_act="quick_gelu",
        layer_norm_eps=1e-5,
        ues_cls_token=False,
        use_cls_token: Optional[bool] = None,
        use_ln_pre=True,
        use_ln_post=False,
        use_abs_posemb=True,
        use_rope2d=True,
        ls_init_value=0.1,
        **kwargs,
    ):
        self.width = width
        self.layers = layers
        self.heads = heads
        self.num_channels = num_channels
        self.patch_size = patch_size
        self.image_size = image_size
        self.mlp_ratio = mlp_ratio
        self.layer_norm_eps = layer_norm_eps
        self.hidden_act = hidden_act
        if use_cls_token is None:
            use_cls_token = ues_cls_token
        self.ues_cls_token = use_cls_token
        self.use_cls_token = use_cls_token
        self.use_ln_pre = use_ln_pre
        self.ls_init_value = ls_init_value
        self.use_ln_post = use_ln_post
        self.use_abs_posemb = use_abs_posemb
        self.use_rope2d = use_rope2d
        super().__init__(**kwargs)


def rotate_half(x: torch.Tensor) -> torch.Tensor:
    """Rotate adjacent coordinate pairs for the encoder's interleaved RoPE."""
    x = x.reshape(*x.shape[:-1], -1, 2)
    x1, x2 = x.unbind(dim=-1)
    x = torch.stack((-x2, x1), dim=-1)
    return x.reshape(*x.shape[:-2], -1)


def apply_rotary_emb(freqs: torch.Tensor,
                     t: torch.Tensor,
                     start_index: int = 0,
                     scale: float = 1.0,
                     seq_dim: int = -2) -> torch.Tensor:
    """Apply 2D rotary embeddings to queries / keys."""
    dtype = t.dtype

    if t.ndim == 3:
        seq_len = t.shape[seq_dim]
        freqs = freqs[-seq_len:]

    rot_dim = freqs.shape[-1]
    end_index = start_index + rot_dim
    assert rot_dim <= t.shape[-1], (
        f"feature dimension {t.shape[-1]} is too small for rot_dim {rot_dim}")

    t_left, t, t_right = (
        t[..., :start_index],
        t[..., start_index:end_index],
        t[..., end_index:],
    )
    t = (t * freqs.cos() * scale) + (rotate_half(t) * freqs.sin() * scale)
    out = torch.cat((t_left, t, t_right), dim=-1)
    return out.type(dtype)


class EncoderRope2D(nn.Module):
    """Cacheable 2D rotary positional embedding."""

    def __init__(
        self,
        dim: int,
        max_grid_height: int,
        max_grid_width: int,
        use_cls_token: bool = False,
        theta: Union[int, float] = 10000,
        theta_rescale_factor: float = 1.0,
    ):
        super().__init__()
        self.dim = dim
        self.max_grid_height = max_grid_height
        self.max_grid_width = max_grid_width
        self.use_cls_token = use_cls_token
        self.theta = theta * theta_rescale_factor**(dim / (dim - 2))
        cache = self._compute_2d_freqs()
        self.register_buffer("freqs_cache", cache, persistent=False)
        self._cache_signature = None

    def _compute_inv_freq(self, base: Union[int, float],
                          dim: int, device=None) -> torch.Tensor:

        freqs = 1.0 / (base**(
            torch.arange(0, dim, 2, device=device)[:(dim // 2)].float() / dim))
        return freqs

    def _compute_freqs(self, t: torch.Tensor, inv_freq: torch.Tensor):
        freqs = torch.einsum("..., f -> ... f", t.type(inv_freq.dtype),
                             inv_freq)
        freqs = freqs.repeat_interleave(2, dim=-1)
        return freqs

    def _compute_2d_freqs(self, device=None) -> torch.Tensor:
        grid_h_range = torch.arange(self.max_grid_height, dtype=torch.float, device=device)
        grid_w_range = torch.arange(self.max_grid_width, dtype=torch.float, device=device)
        if self.use_cls_token:
            grid_h_range += 1
            grid_w_range += 1
        inv_freq = self._compute_inv_freq(self.theta, self.dim // 2, device=device)
        freqs_h = self._compute_freqs(grid_h_range, inv_freq)[:, None].expand(
            self.max_grid_height, self.max_grid_width, -1)
        freqs_w = self._compute_freqs(grid_w_range, inv_freq)[None, :].expand(
            self.max_grid_height, self.max_grid_width, -1)
        freqs = torch.cat([freqs_w, freqs_h], dim=-1).reshape(
            self.max_grid_height * self.max_grid_width, -1)
        if self.use_cls_token:
            freqs = torch.cat([torch.zeros(1, freqs.shape[-1], device=device), freqs], dim=0)
        freqs = freqs[None, None, ...]
        return freqs

    def forward(self, q: torch.Tensor, k: torch.Tensor,
                grid_hw: tuple[int, int]):
        # HF meta loading may materialize nonpersistent buffers with empty
        # storage. Rebuild from coordinates on first use and after device/dtype
        # changes, independently of how checkpoint parameters were loaded.
        signature = (q.device, q.dtype)
        if self._cache_signature != signature:
            self.freqs_cache = self._compute_2d_freqs(device=q.device).to(q.dtype)
            self._cache_signature = signature
        if not (0 < grid_hw[0] <= self.max_grid_height and 0 < grid_hw[1] <= self.max_grid_width):
            raise ValueError(f"RoPE grid {grid_hw} exceeds configured grid {(self.max_grid_height, self.max_grid_width)}")
        # If grid matches cached shape we reuse directly to avoid recomputation.
        if grid_hw[0] != self.max_grid_height or grid_hw[1] != self.max_grid_width:
            rows = torch.arange(grid_hw[0], device=q.device).view(-1, 1)
            cols = torch.arange(grid_hw[1], device=q.device).view(1, -1)
            positions = (rows * self.max_grid_width + cols).reshape(-1).to(
                torch.long)
            if self.use_cls_token:
                positions = torch.cat(
                    [torch.zeros(1, device=q.device, dtype=torch.long), positions + 1], dim=0)
            freqs = self.freqs_cache.index_select(2, positions)
        else:
            freqs = self.freqs_cache
        q = apply_rotary_emb(freqs, q)
        k = apply_rotary_emb(freqs, k)
        return q, k


class EncoderLayerScale(nn.Module):
    """Per-channel residual scaling used when ls_init_value is set."""

    def __init__(self, dim: int, init_values: float):
        super().__init__()
        self.gamma = nn.Parameter(torch.full((dim,), init_values))

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:  # (B, L, D)
        return hidden_states * self.gamma


class EncoderMLP(nn.Module):
    """Feed-forward network used inside each transformer block."""

    def __init__(self, hidden_size: int, intermediate_size: int,
                 hidden_act: str):
        super().__init__()
        self.c_fc = nn.Linear(hidden_size, intermediate_size, bias=True)
        self.act_fn = ACT2FN[hidden_act]
        self.c_proj = nn.Linear(intermediate_size, hidden_size, bias=True)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:

        hidden_states = self.c_proj(self.act_fn(self.c_fc(hidden_states)))
        return hidden_states


class EncoderVisionAttention(nn.Module):
    """Multi-head self attention with optional 2D RoPE."""

    def __init__(
        self,
        hidden_size: int,
        num_heads: int,
        max_grid_height: int,
        max_grid_width: int,
        use_cls_token: bool = False,
        use_rope2d: bool = True,
        rope_theta: Union[int, float] = 10000,
        rope_theta_rescale_factor: float = 1.0,
        rope_freqs_for: str = "lang",
    ):
        super().__init__()
        if hidden_size % num_heads != 0:
            raise ValueError(
                f"hidden_size ({hidden_size}) must be divisible by num_heads ({num_heads})."
            )
        if use_rope2d and (hidden_size // num_heads) % 4:
            raise ValueError("2D RoPE requires head_dim divisible by four")
        if use_rope2d and rope_freqs_for != "lang":
            raise ValueError("Only rope_freqs_for='lang' is implemented")
        self.num_heads = num_heads
        self.head_dim = hidden_size // num_heads
        self.scale = self.head_dim**-0.5
        self.in_proj_weight = nn.Parameter(torch.zeros(hidden_size * 3, hidden_size))
        self.in_proj_bias = nn.Parameter(torch.zeros(hidden_size * 3))
        self.out_proj = nn.Linear(hidden_size, hidden_size, bias=True)

        self.rope = None
        if use_rope2d:
            self.rope = EncoderRope2D(
                dim=self.head_dim,
                max_grid_height=max_grid_height,
                max_grid_width=max_grid_width,
                use_cls_token=use_cls_token,
                theta=rope_theta,
                theta_rescale_factor=rope_theta_rescale_factor,
            )

    def forward(self, hidden_states: torch.Tensor, grid_hw: tuple[int, int]) -> torch.Tensor:
        bsz, seq_len, _ = hidden_states.shape
        qkv = F.linear(
            hidden_states,
            self.in_proj_weight,
            self.in_proj_bias,
        )
        q, k, v = qkv.chunk(3, dim=-1)

        q = q.view(bsz, seq_len, self.num_heads,
                   self.head_dim).transpose(1, 2)
        k = k.view(bsz, seq_len, self.num_heads,
                   self.head_dim).transpose(1, 2)
        if self.rope is not None:
            q, k = self.rope(q, k, grid_hw=grid_hw)
        v = v.view(bsz, seq_len, self.num_heads,
                   self.head_dim).transpose(1, 2)

        attn_output = F.scaled_dot_product_attention(
            q, k, v, is_causal=False, scale=self.scale)
        attn_output = attn_output.transpose(1, 2).reshape(
            bsz, seq_len, self.num_heads * self.head_dim)
        return self.out_proj(attn_output)


class EncoderVisionBlock(nn.Module):
    """A single Vision Transformer block (self-attention + MLP)."""

    def __init__(
        self,
        hidden_size: int,
        num_heads: int,
        mlp_ratio: float,
        hidden_act: str,
        layer_norm_eps: float,
        ls_init_value: Optional[float] = None,
        max_grid_height: Optional[int] = None,
        max_grid_width: Optional[int] = None,
        use_cls_token: bool = False,
        use_rope2d: bool = True,
        rope_kwargs: Optional[dict] = None,
    ):
        super().__init__()
        rope_kwargs = rope_kwargs or {}
        self.attn = EncoderVisionAttention(
            hidden_size,
            num_heads,
            max_grid_height=max_grid_height,
            max_grid_width=max_grid_width,
            use_cls_token=use_cls_token,
            use_rope2d=use_rope2d,
            **rope_kwargs,
        )
        self.ln_1 = nn.LayerNorm(hidden_size, eps=layer_norm_eps)
        self.ln_2 = nn.LayerNorm(hidden_size, eps=layer_norm_eps)

        intermediate = int(hidden_size * mlp_ratio)
        self.mlp = EncoderMLP(hidden_size, intermediate, hidden_act)

        self.ls_1 = EncoderLayerScale(hidden_size, ls_init_value) if ls_init_value is not None else nn.Identity()
        self.ls_2 = EncoderLayerScale(hidden_size, ls_init_value) if ls_init_value is not None else nn.Identity()

    def forward(self, hidden_states: torch.Tensor,
                grid_hw: tuple[int, int]) -> torch.Tensor:
        residual = hidden_states
        hidden_states = self.ln_1(hidden_states)
        hidden_states = self.attn(hidden_states, grid_hw=grid_hw)
        hidden_states = residual + self.ls_1(hidden_states)

        residual = hidden_states
        hidden_states = self.ln_2(hidden_states)
        hidden_states = self.mlp(hidden_states)
        hidden_states = residual + self.ls_2(hidden_states)
        return hidden_states


class EncoderVisionTransformer(nn.Module):
    """Stack of encoder blocks parameterised by Step5VisionConfig."""

    def __init__(
        self,
        embed_dim: int,
        depth: int,
        num_heads: int,
        mlp_ratio: float,
        hidden_act: str,
        layer_norm_eps: float,
        ls_init_value: Optional[float] = None,
        max_grid_height: Optional[int] = None,
        max_grid_width: Optional[int] = None,
        use_cls_token: bool = False,
        use_rope2d: bool = True,
        rope_kwargs: Optional[dict] = None,
    ):
        super().__init__()
        rope_kwargs = rope_kwargs or {}
        self.resblocks = nn.ModuleList([
            EncoderVisionBlock(embed_dim, num_heads, mlp_ratio, hidden_act,
                               layer_norm_eps,
                               max_grid_height=max_grid_height,
                               max_grid_width=max_grid_width,
                               use_cls_token=use_cls_token,
                               use_rope2d=use_rope2d,
                               ls_init_value=ls_init_value,
                               rope_kwargs=rope_kwargs)
            for _ in range(depth)
        ])

    def forward(self,
                hidden_states: torch.Tensor,
                grid_hw: tuple[int, int]) -> torch.Tensor:
        for block in self.resblocks:
            hidden_states = block(hidden_states, grid_hw=grid_hw)
        return hidden_states


class Step5VisionEncoder(nn.Module):
    """
    Vision encoder built from Step5VisionConfig.

    The encoder performs patch embedding followed by a stack of transformer
    blocks. Only the config fields defined in Step5VisionConfig (and
    Step5VLConfig.vision_config) are expected.
    """

    def __init__(self, config: Step5VisionConfig):
        super().__init__()
        self.config = config

        self.hidden_size = config.width
        self.num_heads = config.heads
        self.num_hidden_layers = config.layers
        self.patch_size = config.patch_size
        self.image_size = config.image_size
        self.use_cls_token = getattr(config, "use_cls_token", False)
        self.use_rope2d = getattr(config, "use_rope2d", True)
        self.use_abs_posemb = getattr(config, "use_abs_posemb", True)
        self.layer_norm_eps = config.layer_norm_eps
        self.mlp_ratio = getattr(config, "mlp_ratio", 8960 / 1536)
        self.ls_init_value = getattr(config, "ls_init_value", None)
        self.hidden_act = config.hidden_act
        self.use_ln_pre = getattr(config, "use_ln_pre", False)
        self.use_ln_post = getattr(config, "use_ln_post", True)

        # Patch embedding.
        self.conv1 = nn.Conv2d(in_channels=config.num_channels,
                               out_channels=self.hidden_size,
                               kernel_size=self.patch_size,
                               stride=self.patch_size,
                               bias=False)

        self.ln_pre = nn.LayerNorm(self.hidden_size, eps=self.layer_norm_eps) if self.use_ln_pre else nn.Identity()
        self.ln_post = nn.LayerNorm(self.hidden_size, eps=self.layer_norm_eps) if self.use_ln_post else nn.Identity()

        grid_size = self.image_size // self.patch_size
        self.base_grid = (grid_size, grid_size)

        if self.use_cls_token:
            self.class_embedding = nn.Parameter(
                torch.randn(self.hidden_size) * (self.hidden_size**-0.5))
        else:
            self.class_embedding = None

        if self.use_abs_posemb:
            self.posemb_grid_size = self.image_size // self.patch_size
            self.positional_embedding = nn.Parameter(
                (self.hidden_size**-0.5) * torch.randn(
                    int(self.use_cls_token) + self.posemb_grid_size**2,
                    self.hidden_size,
                ))

        self.transformer = EncoderVisionTransformer(
            embed_dim=self.hidden_size,
            depth=self.num_hidden_layers,
            num_heads=self.num_heads,
            mlp_ratio=self.mlp_ratio,
            hidden_act=self.hidden_act,
            layer_norm_eps=self.layer_norm_eps,
            ls_init_value=self.ls_init_value,
            max_grid_height=self.base_grid[0],
            max_grid_width=self.base_grid[1],
            use_cls_token=self.use_cls_token,
            use_rope2d=self.use_rope2d,
            rope_kwargs={
                "rope_theta": getattr(config, "rope_theta", 10000),
                "rope_theta_rescale_factor":
                getattr(config, "rope_theta_rescale_factor", 1.0),
                "rope_freqs_for": getattr(config, "rope_freqs_for", "lang"),
            },
        )
        self.vit_downsampler1 = nn.Conv2d(self.hidden_size,
                                          self.hidden_size * 2,
                                          kernel_size=3,
                                          stride=2,
                                          padding=1)
        self.vit_downsampler2 = nn.Conv2d(self.hidden_size * 2,
                                          self.hidden_size * 4,
                                          kernel_size=3,
                                          stride=2,
                                          padding=1)


    def sample_abs_posemb(self, grid_h: int, grid_w: int):
        if self.posemb_grid_size == grid_h and self.posemb_grid_size == grid_w:
            return self.positional_embedding[None, ...]

        pos_embed = self.positional_embedding
        if self.use_cls_token:
            cls_token_embed, pos_embed = pos_embed[:1], pos_embed[1:]

        pos_embed = (pos_embed.reshape(1, self.posemb_grid_size,
                                       self.posemb_grid_size,
                                       -1).permute(0, 3, 1, 2).contiguous())
        pos_embed = F.interpolate(pos_embed,
                                  size=(grid_h, grid_w),
                                  mode="bilinear",
                                  align_corners=False)
        pos_embed = pos_embed.permute(0, 2, 3, 1).reshape(-1, self.hidden_size)

        if self.use_cls_token:
            pos_embed = torch.cat([cls_token_embed, pos_embed], dim=0)

        return pos_embed[None, ...]

    def forward(self, pixel_values: torch.Tensor) -> torch.Tensor:
        """
        Args:
            pixel_values: Image tensor of shape (B, C, H, W).
        """
        if pixel_values.ndim != 4 or pixel_values.shape[1] != self.config.num_channels:
            raise ValueError("pixel_values must have shape [images, channels, height, width]")
        bsz, _, height, width = pixel_values.shape
        if not bsz or min(height, width) < self.patch_size or height % self.patch_size or width % self.patch_size:
            raise ValueError("Image dimensions must be positive multiples of patch_size, with a nonempty batch")
        grid_h, grid_w = height // self.patch_size, width // self.patch_size

        hidden_state = self.conv1(pixel_values)  # (B, D, Gh, Gw)
        hidden_state = hidden_state.flatten(2).transpose(1, 2)  # (B, Gh*Gw, D)

        if self.use_cls_token:
            cls_token = self.class_embedding.view(1, 1,
                                                  -1).expand(bsz, -1, -1)
            hidden_state = torch.cat([cls_token, hidden_state], dim=1)

        if self.use_abs_posemb:
            pos_emb = self.sample_abs_posemb(grid_h, grid_w)
            hidden_state = hidden_state + pos_emb
        hidden_state = self.ln_pre(hidden_state)
        hidden_state = self.transformer(hidden_state, grid_hw=(grid_h, grid_w))

        if self.use_ln_post:
            hidden_state = self.ln_post(hidden_state)

        if self.use_cls_token:
            hidden_state = hidden_state[:, 1:, :]

        return hidden_state
