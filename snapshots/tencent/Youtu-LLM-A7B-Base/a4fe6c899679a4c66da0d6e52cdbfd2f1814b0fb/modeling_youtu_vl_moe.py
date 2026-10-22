# coding=utf-8
"""
UTU-VL MoE HuggingFace 模型实现（适配 transformers 5.3）

架构：由 config 决定规模的 UTU-VL MoE LLM（KDA + Gated MLA hybrid attention +
      sigmoid MoE + grouped top-k + dual text/vision shared experts + half RoPE）
      + Qwen3-VL ViT。默认 config 对齐当前验证模型；后续
      scaling up 只需调整 config / checkpoint，不需要改类名。
特性：no deepstack, no SWA, no sink attention, MTP=0
参考：
  - utu_vl_30b_v4/modeling_utu_vl_v4.py（V4 骨架 + MRoPE + 多模态前向）
  - youtu_llm_v2_pro-128/modeling_youtu_llm_v2.py（shared expert + grouped topk 路由）
  - transformers.models.qwen3_vl（ViT + MRoPE + 多模态前向流程）
"""

import copy
import itertools
import inspect
from typing import Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F
import os

from einops import rearrange

from transformers.activations import ACT2FN
from transformers.cache_utils import Cache, DynamicCache
from transformers.generation import GenerationMixin
from transformers.integrations import use_kernel_forward_from_hub
from transformers.masking_utils import create_causal_mask
from transformers.modeling_layers import GradientCheckpointingLayer
from transformers.modeling_outputs import BaseModelOutputWithPast, CausalLMOutputWithPast
from transformers.modeling_utils import ALL_ATTENTION_FUNCTIONS, PreTrainedModel
from transformers.models.qwen3_vl.modeling_qwen3_vl import Qwen3VLVisionModel
from transformers.utils import can_return_tuple
from transformers.utils.deprecation import deprecate_kwarg
try:
    from transformers.utils.generic import check_model_inputs
except ImportError:
    def check_model_inputs(func):
        return func

try:
    from fla.modules import FusedRMSNormGated, ShortConvolution
    from fla.ops.kda import chunk_kda, fused_recurrent_kda
    from fla.ops.utils.index import prepare_cu_seqlens_from_mask
    from fla.utils import tensor_cache
except ImportError:
    FusedRMSNormGated = None
    ShortConvolution = None
    chunk_kda = None
    fused_recurrent_kda = None
    prepare_cu_seqlens_from_mask = None

    def tensor_cache(func):
        return func

from .configuration_youtu_vl_moe import YoutuVLMoEConfig

YoutuVLConfig = YoutuVLMoEConfig

MODALITY_PAD = -1
MODALITY_TEXT = 0
MODALITY_VISION = 1


def _uses_token_level_router_groups(config) -> bool:
    """Match MG --moe-router-token-level-modality: per-token text/vision rows."""
    return bool(
        getattr(config, "moe_router_modality_aware_expert_bias", False)
        and getattr(config, "moe_router_token_level_modality", False)
    )


def _needs_decoder_modality_id(config) -> bool:
    return bool(
        getattr(config, "enable_multimodal_shared_experts", False)
        or _uses_token_level_router_groups(config)
    )


def _sanitize_youtu_vl_moe_config(config: "YoutuVLConfig") -> None:
    """Strip SWA/sink fields that may leak from a stale cache.

    UTU-VL MoE has no SWA and no sink attention. If any of these fields are
    present, DynamicCache may create DynamicSlidingWindowLayer instances that
    break inference.
    """
    for attr in ("sliding_window", "sliding_window_size", "layer_types",
                 "window_size", "window_attn_skip_freq", "softmax_type",
                 "sink_only_on_swa"):
        if getattr(config, attr, None) is not None:
            setattr(config, attr, None)


class BaseModelOutputWithDeepstackFeatures:
    """Compatibility wrapper for Qwen3-VL vision outputs."""

    def __init__(self, pooler_output=None, deepstack_features=None):
        self.pooler_output = pooler_output
        self.deepstack_features = deepstack_features


def _qwen3vl_fast_pos_embed_interpolate_meta_safe(self, grid_thw):
    """Meta/offload-safe Qwen3-VL ViT absolute-position interpolation.

    Upstream ``Qwen3VLVisionModel.fast_pos_embed_interpolate`` builds the
    integer lookup tensor on ``self.pos_embed.weight.device``.  With
    ``device_map="auto"``/Accelerate, submodule parameters may stay on the
    ``meta`` device until the submodule pre-forward hook materializes them on
    the execution device.  In that state upstream creates a *meta* ``idx_tensor``
    and Accelerate later fails while moving the embedding input:

        NotImplementedError: Cannot copy out of meta tensor; no data!

    Keep upstream math/order unchanged, but when the embedding weight is still
    meta, create the lookup/weight tensors on ``grid_thw.device`` instead.  The
    embedding module's Accelerate hook can then materialize/move parameters and
    inputs normally.
    """

    grid_ts, grid_hs, grid_ws = grid_thw[:, 0], grid_thw[:, 1], grid_thw[:, 2]

    idx_list = [[] for _ in range(4)]
    weight_list = [[] for _ in range(4)]

    for t, h, w in zip(grid_ts, grid_hs, grid_ws):
        h_idxs = torch.linspace(0, self.num_grid_per_side - 1, h)
        w_idxs = torch.linspace(0, self.num_grid_per_side - 1, w)

        h_idxs_floor = h_idxs.int()
        w_idxs_floor = w_idxs.int()
        h_idxs_ceil = (h_idxs.int() + 1).clip(max=self.num_grid_per_side - 1)
        w_idxs_ceil = (w_idxs.int() + 1).clip(max=self.num_grid_per_side - 1)

        dh = h_idxs - h_idxs_floor
        dw = w_idxs - w_idxs_floor

        base_h = h_idxs_floor * self.num_grid_per_side
        base_h_ceil = h_idxs_ceil * self.num_grid_per_side

        indices = [
            (base_h[None].T + w_idxs_floor[None]).flatten(),
            (base_h[None].T + w_idxs_ceil[None]).flatten(),
            (base_h_ceil[None].T + w_idxs_floor[None]).flatten(),
            (base_h_ceil[None].T + w_idxs_ceil[None]).flatten(),
        ]

        weights = [
            ((1 - dh)[None].T * (1 - dw)[None]).flatten(),
            ((1 - dh)[None].T * dw[None]).flatten(),
            (dh[None].T * (1 - dw)[None]).flatten(),
            (dh[None].T * dw[None]).flatten(),
        ]

        for i in range(4):
            idx_list[i].extend(indices[i].tolist())
            weight_list[i].extend(weights[i].tolist())

    pos_weight = self.pos_embed.weight
    tensor_device = grid_thw.device if pos_weight.device.type == "meta" else pos_weight.device
    idx_tensor = torch.tensor(idx_list, dtype=torch.long, device=tensor_device)
    weight_tensor = torch.tensor(weight_list, dtype=pos_weight.dtype, device=tensor_device)
    pos_embeds = self.pos_embed(idx_tensor)
    # If pos_embed was meta before Accelerate's hook, the hook may materialize
    # and execute the embedding on a different device from grid_thw/tensor_device.
    weight_tensor = weight_tensor.to(device=pos_embeds.device, dtype=pos_embeds.dtype)
    pos_embeds = pos_embeds * weight_tensor[:, :, None]
    patch_pos_embeds = pos_embeds[0] + pos_embeds[1] + pos_embeds[2] + pos_embeds[3]

    patch_pos_embeds = patch_pos_embeds.split([h * w for h, w in zip(grid_hs, grid_ws)])

    patch_pos_embeds_permute = []
    merge_size = self.config.spatial_merge_size
    for pos_embed, t, h, w in zip(patch_pos_embeds, grid_ts, grid_hs, grid_ws):
        pos_embed = pos_embed.repeat(t, 1)
        pos_embed = (
            pos_embed.view(t, h // merge_size, merge_size, w // merge_size, merge_size, -1)
            .permute(0, 1, 3, 2, 4, 5)
            .flatten(0, 4)
        )
        patch_pos_embeds_permute.append(pos_embed)
    patch_pos_embeds = torch.cat(patch_pos_embeds_permute)
    return patch_pos_embeds


# ──────────────────────────────────────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────────────────────────────────────

def rotate_half(x):
    x1 = x[..., : x.shape[-1] // 2]
    x2 = x[..., x.shape[-1] // 2 :]
    return torch.cat((-x2, x1), dim=-1)


def apply_rotary_pos_emb(q, k, cos, sin, unsqueeze_dim=1, multi_latent_attention=False):
    cos = cos.unsqueeze(unsqueeze_dim)
    sin = sin.unsqueeze(unsqueeze_dim)

    if multi_latent_attention:
        # Megatron MLA applies a dedicated interleaving before RoPE:
        #   t = cat(t[..., 0::2], t[..., 1::2], dim=-1)
        q = torch.cat((q[..., 0::2], q[..., 1::2]), dim=-1)
        k = torch.cat((k[..., 0::2], k[..., 1::2]), dim=-1)
        q_embed = (q * cos) + (rotate_half(q) * sin)
        k_embed = (k * cos) + (rotate_half(k) * sin)
        return q_embed, k_embed

    rotary_dim = cos.shape[-1]
    q_rot, q_pass = q[..., :rotary_dim], q[..., rotary_dim:]
    k_rot, k_pass = k[..., :rotary_dim], k[..., rotary_dim:]
    q_rot = (q_rot * cos) + (rotate_half(q_rot) * sin)
    k_rot = (k_rot * cos) + (rotate_half(k_rot) * sin)
    if q_pass.shape[-1] > 0:
        q_rot = torch.cat((q_rot, q_pass), dim=-1)
    if k_pass.shape[-1] > 0:
        k_rot = torch.cat((k_rot, k_pass), dim=-1)
    return q_rot, k_rot


def repeat_kv(hidden_states: torch.Tensor, n_rep: int) -> torch.Tensor:
    batch, num_key_value_heads, slen, head_dim = hidden_states.shape
    if n_rep == 1:
        return hidden_states
    hidden_states = hidden_states[:, :, None, :, :].expand(batch, num_key_value_heads, n_rep, slen, head_dim)
    return hidden_states.reshape(batch, num_key_value_heads * n_rep, slen, head_dim)


def _call_create_causal_mask_compat(
    config,
    inputs_embeds: torch.Tensor,
    attention_mask: Optional[torch.Tensor],
    cache_position: Optional[torch.Tensor],
    past_key_values: Optional[Cache],
    position_ids: Optional[torch.Tensor],
):
    """Call the causal-mask helper across transformers versions.

    5.3 spells ``input(s)_embeds`` either way and takes ``cache_position``;
    newer releases dropped ``cache_position`` and read offsets from the cache.
    """
    params = inspect.signature(create_causal_mask).parameters
    kwargs = {
        "config": config,
        "attention_mask": attention_mask,
        "cache_position": cache_position,
        "past_key_values": past_key_values,
        "position_ids": position_ids,
        "inputs_embeds" if "inputs_embeds" in params else "input_embeds": inputs_embeds,
    }
    return create_causal_mask(**{k: v for k, v in kwargs.items() if k in params})


def eager_attention_forward(
    module: nn.Module,
    query: torch.Tensor,
    key: torch.Tensor,
    value: torch.Tensor,
    attention_mask: Optional[torch.Tensor],
    scaling: float,
    dropout: float = 0.0,
    **kwargs,
):
    key_states = repeat_kv(key, module.num_key_value_groups)
    value_states = repeat_kv(value, module.num_key_value_groups)
    attn_weights = torch.matmul(query, key_states.transpose(2, 3)) * scaling
    if attention_mask is not None:
        causal_mask = attention_mask[:, :, :, : key_states.shape[-2]]
        attn_weights = attn_weights + causal_mask

    attn_weights = nn.functional.softmax(attn_weights.float(), dim=-1).to(query.dtype)
    attn_weights = nn.functional.dropout(attn_weights, p=dropout, training=module.training)
    attn_output = torch.matmul(attn_weights, value_states)
    attn_output = attn_output.transpose(1, 2).contiguous()
    return attn_output, attn_weights


# ──────────────────────────────────────────────────────────────────────────────
# RMSNorm
# ──────────────────────────────────────────────────────────────────────────────

@use_kernel_forward_from_hub("RMSNorm")
class YoutuVLRMSNorm(nn.Module):
    def __init__(self, hidden_size, eps=1e-6):
        super().__init__()
        self.weight = nn.Parameter(torch.ones(hidden_size))
        self.variance_epsilon = eps

    def forward(self, hidden_states):
        input_dtype = hidden_states.dtype
        hidden_states = hidden_states.to(torch.float32)
        variance = hidden_states.pow(2).mean(-1, keepdim=True)
        hidden_states = hidden_states * torch.rsqrt(variance + self.variance_epsilon)
        return self.weight * hidden_states.to(input_dtype)

    def extra_repr(self):
        return f"{tuple(self.weight.shape)}, eps={self.variance_epsilon}"


# ──────────────────────────────────────────────────────────────────────────────
# MRoPE 旋转位置编码（与 MG MultimodalRotaryEmbedding 完全一致的【块布局】MRoPE）
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLRotaryEmbedding(nn.Module):
    """
    Interleaved Multimodal RoPE（支持 rotary_percent 部分旋转）。
    mrope_section 将 rotary_dim//2 个频率对按 THW 交错分配（[THWTHW...TT]）：
    前 s0+s1+s2 个频率对按 THW 交错、剩余对全 temporal。
    与 MG vlm_patch/models/interleaved_mrope.py::InterleavedMultimodalRotaryEmbedding
    及 utu_vl_30b_v4 逐元素一致（MG 训练用交错布局，非 transformers 官方 Qwen3-VL 的交错也非 Qwen2-VL 的块布局——
    此处与 MG 的 InterleavedMultimodalRotaryEmbedding 完全对齐）。
    """

    def __init__(self, config: YoutuVLConfig, device=None):
        super().__init__()
        self.head_dim = config.head_dim
        self.rope_theta = config.rope_theta
        self.mrope_section = config.mrope_section
        self.rotary_percent = float(getattr(config, "rotary_percent", 1.0))
        if getattr(config, "experimental_attention_variant", None) == "kda":
            # Megatron MLA MRoPE is constructed with kv_channels=qk_pos_emb_head_dim
            # and rotary_percent=1.0.  Keep qk_rope_head_dim as the inv_freq divisor.
            rotary_dim = int(config.qk_rope_head_dim)
        else:
            if self.rotary_percent <= 0.0 or self.rotary_percent > 1.0:
                raise ValueError(
                    f"rotary_percent must be in (0, 1], got {self.rotary_percent}"
                )
            rotary_dim = int(self.head_dim * self.rotary_percent)
            if rotary_dim % 2 != 0:
                rotary_dim -= 1
            if rotary_dim <= 0:
                raise ValueError(
                    f"rotary_dim became non-positive: head_dim={self.head_dim}, rotary_percent={self.rotary_percent}"
                )
        self.rotary_dim = rotary_dim
        if sum(self.mrope_section) != self.rotary_dim // 2:
            raise ValueError(
                "mrope_section sum must equal rotary_dim//2, "
                f"got sum={sum(self.mrope_section)} rotary_dim={self.rotary_dim}"
            )

        inv_freq = 1.0 / (
            self.rope_theta
            ** (
                torch.arange(0, self.rotary_dim, 2, dtype=torch.int64).float()
                / self.rotary_dim
            )
        )
        self.register_buffer("inv_freq", inv_freq, persistent=False)

    def _recompute_inv_freq(self, device=None):
        inv_freq = 1.0 / (
            self.rope_theta
            ** (
                torch.arange(0, self.rotary_dim, 2, dtype=torch.int64, device=device).float()
                / self.rotary_dim
            )
        )
        self.inv_freq = inv_freq

    @torch.no_grad()
    def forward(self, x: torch.Tensor, position_ids: torch.Tensor):
        if self.inv_freq.abs().max() == 0:
            self._recompute_inv_freq(device=x.device)

        if position_ids.ndim == 2:
            position_ids = position_ids[None, ...].expand(3, position_ids.shape[0], -1)

        inv_freq_expanded = (
            self.inv_freq[None, None, :, None]
            .float()
            .expand(3, position_ids.shape[1], -1, 1)
        )
        position_ids_expanded = position_ids[:, :, None, :].float()

        device_type = x.device.type if x.device.type != "mps" else "cpu"
        with torch.autocast(device_type=device_type, enabled=False):
            freqs = (inv_freq_expanded.float() @ position_ids_expanded.float()).transpose(2, 3)
            freqs = self._apply_interleaved_mrope(freqs, self.mrope_section)
            emb = torch.cat((freqs, freqs), dim=-1)
            cos = emb.cos()
            sin = emb.sin()

        return cos.to(dtype=x.dtype), sin.to(dtype=x.dtype)

    @staticmethod
    def _apply_interleaved_mrope(freqs: torch.Tensor, mrope_section: list) -> torch.Tensor:
        # 与 MG vlm_patch/models/interleaved_mrope.py::InterleavedMultimodalRotaryEmbedding
        # 和 utu_vl_30b_v4/modeling_utu_vl_v4.py 完全一致的【交错布局】MRoPE。
        # 重排 freqs 从块 [TTT...HHH...WWW] 到交错 [THWTHWTHW...TT]：
        #   freqs_t 初始全 T；H/W 按 offset 1/2，在每 3 个一组里填入前 sum*3 区间。
        # NOTE: UTU-VL MoE LLM 由 MG 用 InterleavedMultimodalRotaryEmbedding（交错）训练，
        #   推理必须用交错布局才能一致；之前的块布局是错误判断，导致 5000+ step 乱码。
        freqs_t = freqs[0].clone()
        for dim_idx, offset in enumerate((1, 2), start=1):
            length = mrope_section[dim_idx] * 3
            idx = slice(offset, length, 3)
            freqs_t[..., idx] = freqs[dim_idx, ..., idx]
        return freqs_t


def _quantile_balancing_enabled(config) -> bool:
    method = getattr(config, "moe_router_expert_bias_update_method", "sign")
    topk_method = getattr(config, "topk_method", "noaux_tc")
    return method == "quantile" or topk_method in ("quantile_balancing", "quantile")


# ──────────────────────────────────────────────────────────────────────────────
# MoE 组件（sigmoid router + QB / grouped topk + optional rLatentMoE）
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLMLP(nn.Module):
    def __init__(self, config: YoutuVLConfig, hidden_size=None, intermediate_size=None):
        super().__init__()
        self.hidden_size = config.hidden_size if hidden_size is None else hidden_size
        self.intermediate_size = config.intermediate_size if intermediate_size is None else intermediate_size
        self.gate_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)
        self.up_proj = nn.Linear(self.hidden_size, self.intermediate_size, bias=False)
        self.down_proj = nn.Linear(self.intermediate_size, self.hidden_size, bias=False)
        self.act_fn = ACT2FN[config.hidden_act]

    def forward(self, x):
        return self.down_proj(self.act_fn(self.gate_proj(x)) * self.up_proj(x))


class YoutuVLTopkRouter(nn.Module):
    """sigmoid router with either Quantile Balancing or grouped noaux-tc bias.

    Quantile Balancing (Megatron ``quantile_balancing``) selects experts in the
    raw-logit domain with ``logits - qb_beta``, taking Top-(k+1) then the first
    k indices so ties match the training recompute path.  Expert weights still
    come from sigmoid(logits).  Group-limited routing is disabled in this mode.

    Sign / noaux-tc routing keeps the original ``e_score_correction_bias`` plus
    grouped top-k path.
    """

    def __init__(self, config: YoutuVLConfig):
        super().__init__()
        self.top_k = config.num_experts_per_tok
        self.n_routed_experts = config.n_routed_experts
        self.routed_scaling_factor = config.routed_scaling_factor
        self.n_group = config.n_group
        self.topk_group = config.topk_group
        self.norm_topk_prob = config.norm_topk_prob
        self.use_expert_bias = getattr(
            config, "moe_router_enable_expert_bias", True
        )
        self.use_quantile_balancing = _quantile_balancing_enabled(config)
        if self.use_quantile_balancing and not self.use_expert_bias:
            raise ValueError("Quantile Balancing requires expert bias to be enabled.")

        self.weight = nn.Parameter(torch.empty((self.n_routed_experts, config.hidden_size)))
        bias_shape = (
            (2, self.n_routed_experts)
            if getattr(config, "moe_router_modality_aware_expert_bias", False)
            else (self.n_routed_experts,)
        )
        if not self.use_expert_bias:
            self.qb_beta = None
            self.e_score_correction_bias = None
        elif self.use_quantile_balancing:
            self.register_buffer("qb_beta", torch.zeros(bias_shape, dtype=torch.float32))
            self.e_score_correction_bias = None
        else:
            self.register_buffer(
                "e_score_correction_bias",
                torch.zeros(bias_shape, dtype=torch.float32),
            )
            self.qb_beta = None

    def _apply(self, fn):
        super()._apply(fn)
        for name in ("qb_beta", "e_score_correction_bias"):
            bias = getattr(self, name, None)
            if isinstance(bias, torch.Tensor) and bias.dtype != torch.float32:
                bias.data = bias.data.float()
        return self

    def _bias_for_tokens(
        self,
        bias: torch.Tensor,
        scores: torch.Tensor,
        modality_id: Optional[torch.Tensor],
    ) -> torch.Tensor:
        bias = bias.float()
        if bias.dim() == 2:
            # MG --moe-router-modality-aware-expert-bias stores persistent
            # [text, vision] bias rows. Token-level training selects row 1 only
            # for image/video placeholders. Decode/generation without ids is text.
            if modality_id is None:
                return bias[0].unsqueeze(0)
            modality_id = modality_id.reshape(-1).to(device=scores.device)
            if modality_id.shape[0] != scores.shape[0]:
                raise ValueError(
                    "modality_id must align with router scores, got "
                    f"{tuple(modality_id.shape)} vs {tuple(scores.shape)}"
                )
            bias_index = (modality_id == MODALITY_VISION).long()
            return bias.index_select(0, bias_index)
        return bias.unsqueeze(0)

    @torch.no_grad()
    def get_topk_indices(
        self,
        scores,
        modality_id: Optional[torch.Tensor] = None,
        router_logits: Optional[torch.Tensor] = None,
    ):
        scores = scores.view(-1, self.n_routed_experts)
        if self.use_quantile_balancing:
            if router_logits is None:
                raise RuntimeError("QB routing requires raw router logits.")
            if self.qb_beta is None:
                raise RuntimeError("QB routing requires an initialized qb_beta buffer.")
            logits = router_logits.view(-1, self.n_routed_experts).float()
            qb_beta = self._bias_for_tokens(self.qb_beta, logits, modality_id)
            # Always select Top-(k+1) then keep the first k, matching Megatron
            # recompute / tie-breaking.
            return torch.topk(logits - qb_beta, k=self.top_k + 1, dim=-1).indices[:, : self.top_k]

        # 与 MG group_limited_topk 对齐：组内 topk = topk // group_topk。
        if self.e_score_correction_bias is None:
            scores_for_choice = scores
        else:
            correction_bias = self._bias_for_tokens(
                self.e_score_correction_bias, scores, modality_id
            )
            scores_for_choice = scores + correction_bias
        if self.n_group > 1:
            group_scores = (
                scores_for_choice.view(-1, self.n_group, self.n_routed_experts // self.n_group)
                .topk(self.top_k // self.topk_group, dim=-1)[0]
                .sum(dim=-1)
            )
            group_idx = torch.topk(group_scores, k=self.topk_group, dim=-1, sorted=False)[1]
            group_mask = torch.zeros_like(group_scores)
            group_mask.scatter_(1, group_idx, 1)
            score_mask = (
                group_mask.unsqueeze(-1)
                .expand(-1, self.n_group, self.n_routed_experts // self.n_group)
                .reshape(-1, self.n_routed_experts)
            )
            scores_for_choice = scores_for_choice.masked_fill(~score_mask.bool(), float("-inf"))
        return torch.topk(scores_for_choice, k=self.top_k, dim=-1, sorted=False)[1]

    def forward(self, hidden_states, modality_id: Optional[torch.Tensor] = None):
        hidden_states = hidden_states.view(-1, hidden_states.shape[-1])
        router_logits = F.linear(hidden_states.float(), self.weight.float())
        scores = router_logits.sigmoid()
        topk_indices = self.get_topk_indices(
            scores, modality_id=modality_id, router_logits=router_logits
        )
        topk_weights = scores.gather(1, topk_indices)
        if self.norm_topk_prob:
            topk_weights = topk_weights / (topk_weights.sum(dim=-1, keepdim=True) + 1e-20)
        topk_weights = topk_weights * self.routed_scaling_factor
        return topk_indices, topk_weights


class YoutuVLMultiModalSharedExperts(nn.Module):
    """Dual shared experts selected by token modality.

    This mirrors ``vlm_patch.models.multimodal_shared_experts.MultiModalSharedExperts``:
    ordinary text tokens select the ``text`` branch, image/video placeholder tokens
    select the ``vision`` branch, and padding tokens select zero shared output.
    Routed experts remain fully shared.
    """

    def __init__(self, config: YoutuVLConfig):
        super().__init__()
        intermediate_size = config.moe_shared_experts_intermediate_size
        self.text = YoutuVLMLP(config, intermediate_size=intermediate_size)
        self.vision = YoutuVLMLP(config, intermediate_size=intermediate_size)

    def forward(self, hidden_states: torch.Tensor, modality_id: Optional[torch.Tensor]) -> torch.Tensor:
        if modality_id is None:
            # Generation decode steps and text-only callers are all-text unless
            # a caller explicitly provides placeholder-aligned modality ids.
            modality_id = torch.full(
                hidden_states.shape[:2],
                MODALITY_TEXT,
                dtype=torch.int8,
                device=hidden_states.device,
            )
        if modality_id.shape != hidden_states.shape[:2]:
            raise ValueError(
                "modality_id must align with hidden_states [batch, seq], got "
                f"{tuple(modality_id.shape)} vs {tuple(hidden_states.shape[:2])}"
            )
        modality_id = modality_id.to(device=hidden_states.device)
        text_out = self.text(hidden_states)
        vision_out = self.vision(hidden_states)
        text_mask = (modality_id == MODALITY_TEXT).unsqueeze(-1).to(dtype=text_out.dtype)
        vision_mask = (modality_id == MODALITY_VISION).unsqueeze(-1).to(dtype=vision_out.dtype)
        return text_out * text_mask + vision_out * vision_mask


class YoutuVLMoE(nn.Module):
    """sigmoid routing MoE + shared expert path, optional rLatentMoE.

    Routed experts may run in a latent subspace: hidden -> fc1_latent_proj ->
    experts -> optional latent RMSNorm -> fc2_latent_proj -> hidden.  The router
    and shared experts always stay in the model hidden size, matching Megatron
    ``MoELayer``.
    """

    def __init__(self, config: YoutuVLConfig):
        super().__init__()
        self.moe_latent_size = getattr(config, "moe_latent_size", None)
        expert_hidden_size = (
            self.moe_latent_size if self.moe_latent_size else config.hidden_size
        )
        self.fc1_latent_proj = None
        self.fc2_latent_proj = None
        self.latent_rmsnorm = None
        if self.moe_latent_size:
            self.fc1_latent_proj = nn.Linear(
                config.hidden_size, self.moe_latent_size, bias=False
            )
            self.fc2_latent_proj = nn.Linear(
                self.moe_latent_size, config.hidden_size, bias=False
            )
            if getattr(config, "moe_latent_rmsnorm", False):
                self.latent_rmsnorm = YoutuVLRMSNorm(
                    self.moe_latent_size, eps=config.rms_norm_eps
                )

        self.experts = nn.ModuleList([
            YoutuVLMLP(
                config,
                hidden_size=expert_hidden_size,
                intermediate_size=config.moe_intermediate_size,
            )
            for _ in range(config.n_routed_experts)
        ])
        self.gate = YoutuVLTopkRouter(config)
        if config.n_shared_experts is not None and config.n_shared_experts > 0:
            if getattr(config, "enable_multimodal_shared_experts", False):
                self.shared_experts = YoutuVLMultiModalSharedExperts(config)
            else:
                self.shared_experts = YoutuVLMLP(
                    config,
                    intermediate_size=config.moe_shared_experts_intermediate_size,
                )
        else:
            self.shared_experts = None

    def forward(self, hidden_states, modality_id: Optional[torch.Tensor] = None):
        residuals = hidden_states
        orig_shape = hidden_states.shape
        topk_indices, topk_weights = self.gate(hidden_states, modality_id=modality_id)
        hidden_states_flat = hidden_states.view(-1, hidden_states.shape[-1])
        expert_input = hidden_states_flat
        if self.fc1_latent_proj is not None:
            expert_input = self.fc1_latent_proj(hidden_states_flat)

        final_hidden_states = torch.zeros(
            expert_input.shape[0],
            expert_input.shape[-1],
            dtype=topk_weights.dtype,
            device=expert_input.device,
        )
        topk = topk_indices.shape[1]
        flat_expert_indices = topk_indices.reshape(-1)
        sorted_route_indices = flat_expert_indices.argsort(stable=True)
        tokens_per_expert = torch.bincount(
            flat_expert_indices, minlength=len(self.experts)
        )

        start_idx = 0
        for expert_idx, num_tokens in enumerate(tokens_per_expert.tolist()):
            end_idx = start_idx + num_tokens
            if num_tokens:
                route_indices = sorted_route_indices[start_idx:end_idx]
                token_indices = torch.div(route_indices, topk, rounding_mode="floor")
                weight_indices = route_indices.remainder(topk)
                expert_output = self.experts[expert_idx](expert_input[token_indices])
                expert_weights = topk_weights[token_indices, weight_indices]
                final_hidden_states.index_add_(
                    0, token_indices, expert_output * expert_weights.unsqueeze(-1)
                )
            start_idx = end_idx

        if self.latent_rmsnorm is not None:
            final_hidden_states = self.latent_rmsnorm(final_hidden_states)
        if self.fc2_latent_proj is not None:
            final_hidden_states = self.fc2_latent_proj(final_hidden_states)

        final_hidden_states = final_hidden_states.view(*orig_shape).to(hidden_states.dtype)
        if self.shared_experts is not None:
            if isinstance(self.shared_experts, YoutuVLMultiModalSharedExperts):
                final_hidden_states = final_hidden_states + self.shared_experts(residuals, modality_id)
            else:
                final_hidden_states = final_hidden_states + self.shared_experts(residuals)
        return final_hidden_states


# ──────────────────────────────────────────────────────────────────────────────
# Attention（KDA + Gated MLA hybrid, no SWA, no sink）
# ──────────────────────────────────────────────────────────────────────────────


def _is_kda_layer(config: YoutuVLConfig, layer_idx: int) -> bool:
    return config.linear_attention_pattern[layer_idx] == 1


@tensor_cache
def get_unpad_data(attention_mask: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
    indices = torch.nonzero(attention_mask.flatten(), as_tuple=False).flatten()
    cu_seqlens = prepare_cu_seqlens_from_mask(attention_mask)
    return indices, cu_seqlens


def pad_input(
        hidden_states: torch.Tensor,
        indices: torch.LongTensor,
        batch_size: int,
        seq_len: int,
) -> torch.Tensor:
    out = hidden_states.new_zeros((batch_size * seq_len, *hidden_states.shape[1:]))
    out[indices] = hidden_states
    return out.view(batch_size, seq_len, *hidden_states.shape[1:])


class YoutuVLDynamicCache(DynamicCache):
    """Dynamic cache for mixed KDA/MLA inference.

    KDA layers maintain a convolution state and recurrent KDA state; MLA layers
    use ordinary key/value caches.  This mirrors Kimi's cache shape contract
    while preserving UTU-VL's Megatron-trained KDA parameterization.

    Inherits from ``Cache`` so that ``isinstance(past_key_values, Cache)``
    checks inside transformers (masking_utils, GenerationMixin, etc.) pass.
    The internal storage uses flat per-layer lists rather than the layered
    ``CacheLayerMixin`` structure, so ``__init__`` does **not** call
    ``super().__init__``; all duck-typed methods HF relies on
    (``get_seq_length``, ``get_mask_sizes``, ``reorder_cache``, ``__len__``,
    ``is_sliding``, ``has_previous_state``) are overridden below.
    """

    is_compileable = False

    def __init__(self, config: YoutuVLConfig):
        super().__init__()
        # Intentionally skip Cache.__init__: the base class expects a list of
        # CacheLayerMixin layers or a layer_class_to_replicate, but this hybrid
        # cache stores KDA conv/recurrent states and MLA KV entries in flat
        # parallel lists indexed by layer_idx.
        self.config = config
        self.layer_types = [
            "linear_attention" if _is_kda_layer(config, i) else "full_attention"
            for i in range(config.num_hidden_layers)
        ]
        self.transformer_layers = [
            i for i, layer_type in enumerate(self.layer_types) if layer_type == "full_attention"
        ]
        linear_layers = [
            i for i, layer_type in enumerate(self.layer_types) if layer_type == "linear_attention"
        ]
        self.last_linear_layer = linear_layers[-1] if linear_layers else -1
        self.conv_states = [None for _ in range(config.num_hidden_layers)]
        self.recurrent_states = [None for _ in range(config.num_hidden_layers)]
        self.key_cache = [None for _ in range(config.num_hidden_layers)]
        self.value_cache = [None for _ in range(config.num_hidden_layers)]

    def __len__(self):
        return len(self.layer_types)

    def update(
            self,
            key_states: torch.Tensor,
            value_states: torch.Tensor,
            layer_idx: int,
            cache_kwargs: Optional[dict] = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        # cache_kwargs is accepted for compatibility with HF Cache.update callers;
        # MLA does not need the RoPE/cache_position metadata here.
        if self.key_cache[layer_idx] is None:
            self.key_cache[layer_idx] = key_states
            self.value_cache[layer_idx] = value_states
        else:
            self.key_cache[layer_idx] = torch.cat([self.key_cache[layer_idx], key_states], dim=2)
            self.value_cache[layer_idx] = torch.cat(
                [self.value_cache[layer_idx], value_states], dim=2
            )
        return self.key_cache[layer_idx], self.value_cache[layer_idx]

    def reorder_cache(self, beam_idx: torch.LongTensor):
        for layer_idx in range(len(self.key_cache)):
            if self.key_cache[layer_idx] is not None:
                device = self.key_cache[layer_idx].device
                beam_idx_device = beam_idx.to(device)
                self.key_cache[layer_idx] = self.key_cache[layer_idx].index_select(0, beam_idx_device)
                self.value_cache[layer_idx] = self.value_cache[layer_idx].index_select(0, beam_idx_device)
            if self.conv_states[layer_idx] is not None:
                device = self.conv_states[layer_idx].device
                beam_idx_device = beam_idx.to(device)
                self.conv_states[layer_idx] = self.conv_states[layer_idx].index_select(0, beam_idx_device)
            if self.recurrent_states[layer_idx] is not None:
                device = self.recurrent_states[layer_idx].device
                beam_idx_device = beam_idx.to(device)
                self.recurrent_states[layer_idx] = self.recurrent_states[layer_idx].index_select(
                    0, beam_idx_device
                )

    def get_seq_length(self, layer_idx: Optional[int] = 0) -> int:
        """Returns the sequence length of the cached states. A layer index can be optionally passed."""
        # take any layer that contains cache and not empty tensor
        if layer_idx not in self.transformer_layers:
            layer_idx = self.transformer_layers[0]

        if len(self.key_cache) <= layer_idx or self.key_cache[layer_idx] is None:
            return 0
        return self.key_cache[layer_idx].shape[-2]

    def get_mask_sizes(self, cache_position: Union[torch.Tensor, int], layer_idx: int) -> tuple[int, int]:
        # transformers 5.3 passes cache_position; newer releases pass query_length.
        query_length = cache_position if isinstance(cache_position, int) else int(cache_position.shape[0])
        return query_length + self.get_seq_length(layer_idx), 0

    @property
    def has_previous_state(self):
        """We have a previous state if the last linear (conv) layer was already updated."""
        if self.last_linear_layer == -1:
            return False
        return self.conv_states[self.last_linear_layer] is not None


class YoutuVLMLAAttention(nn.Module):
    """Megatron MLA-compatible attention.

    Non-KDA layers in the training script use ``--multi-latent-attention`` with
    q-lora rank 256, kv-lora rank 128, qk/nope dim 128, RoPE dim 64, v dim 128,
    plus a head-wise output gate.  Parameter names intentionally match the
    generic Megatron MLA synchronizer: q_a/q_b/kv_a/kv_b/o_proj/g_proj.
    """

    def __init__(self, config: YoutuVLConfig, layer_idx: int):
        super().__init__()
        self.config = config
        self.layer_idx = layer_idx
        self.hidden_size = config.hidden_size
        self.num_heads = config.num_attention_heads
        self.num_key_value_heads = config.num_key_value_heads
        self.num_key_value_groups = self.num_heads // self.num_key_value_heads

        self.q_lora_rank = config.q_lora_rank
        self.kv_lora_rank = config.kv_lora_rank

        self.v_head_dim = config.v_head_dim
        self.qk_nope_head_dim = config.qk_nope_head_dim
        self.qk_rope_head_dim = config.qk_rope_head_dim
        self.q_head_dim = self.qk_nope_head_dim + self.qk_rope_head_dim
        self.scaling = self.q_head_dim ** -0.5
        self.attention_dropout = config.attention_dropout
        self.is_causal = True

        if self.q_lora_rank is not None:
            self.q_a_proj = nn.Linear(self.hidden_size, self.q_lora_rank, bias=False)
            self.q_a_layernorm = YoutuVLRMSNorm(self.q_lora_rank, eps=config.rms_norm_eps)
            self.q_b_proj = nn.Linear(
                self.q_lora_rank,
                self.num_heads * self.q_head_dim,
                bias=False
            )
        else:
            self.q_proj = nn.Linear(
                self.hidden_size, self.num_heads * self.q_head_dim, bias=False
            )

        self.kv_a_proj_with_mqa = nn.Linear(
            self.hidden_size, self.kv_lora_rank + self.qk_rope_head_dim, bias=False
        )
        self.kv_a_layernorm = YoutuVLRMSNorm(self.kv_lora_rank, eps=config.rms_norm_eps)
        self.kv_b_proj = nn.Linear(
            self.kv_lora_rank, self.num_heads * (self.qk_nope_head_dim + self.v_head_dim), bias=False
        )

        self.mla_output_gate_type = getattr(config, "mla_output_gate_type", "head_wise")
        if getattr(config, "attention_output_gate", False):
            if self.mla_output_gate_type == "channel_wise":
                self.g_proj = nn.Linear(
                    self.hidden_size, self.num_heads * self.v_head_dim, bias=False
                )
            elif self.mla_output_gate_type == "head_wise":
                self.g_proj = nn.Linear(self.hidden_size, self.num_heads, bias=False)
            else:
                raise ValueError(
                    f"Unsupported mla_output_gate_type={self.mla_output_gate_type!r}; "
                    "expected 'head_wise' or 'channel_wise'."
                )
        else:
            self.g_proj = None
        self.attn_implementation = getattr(
            config, "mla_attn_implementation", getattr(config, "_attn_implementation", "eager")
        )

        self.o_proj = nn.Linear(self.num_heads * self.v_head_dim, self.hidden_size, bias=False)

    @deprecate_kwarg("past_key_value", new_name="past_key_values", version="4.58")
    def forward(
            self,
            hidden_states: torch.Tensor,
            position_embeddings: tuple,
            attention_mask: Optional[torch.Tensor],
            past_key_values: Optional[Cache] = None,
            cache_position: Optional[torch.LongTensor] = None,
            **kwargs,
    ):
        batch_size, seq_len, _ = hidden_states.shape
        query_shape = (batch_size, seq_len, -1, self.q_head_dim)
        key_shape = (batch_size, seq_len, -1, self.qk_nope_head_dim + self.v_head_dim)

        if self.q_lora_rank is not None:
            q_states = self.q_b_proj(self.q_a_layernorm(self.q_a_proj(hidden_states)))
        else:
            q_states = self.q_proj(hidden_states)
        q_states = q_states.view(query_shape).transpose(1, 2)
        q_pass, q_rot = torch.split(q_states, [self.qk_nope_head_dim, self.qk_rope_head_dim], dim=-1)

        compressed_kv = self.kv_a_proj_with_mqa(hidden_states)
        k_pass, k_rot = torch.split(compressed_kv, [self.kv_lora_rank, self.qk_rope_head_dim], dim=-1)
        k_pass = self.kv_b_proj(self.kv_a_layernorm(k_pass)).view(key_shape).transpose(1, 2)
        k_pass, value_states = torch.split(k_pass, [self.qk_nope_head_dim, self.v_head_dim], dim=-1)
        k_rot = k_rot.view(batch_size, 1, seq_len, self.qk_rope_head_dim)

        cos, sin = position_embeddings
        q_rot, k_rot = apply_rotary_pos_emb(q_rot, k_rot, cos, sin, multi_latent_attention=True)
        # k_rot is MQA (1 head) but k_pass has num_heads.  Expand k_rot to
        # match num_heads before concatenation, matching Megatron MLA
        # (multi_latent_attention.py: k_pos_emb.expand(..., num_heads, ...)).
        k_rot = k_rot.expand(batch_size, self.num_heads, seq_len, self.qk_rope_head_dim)
        query_states = torch.cat((q_pass, q_rot), dim=-1)
        key_states = torch.cat((k_pass, k_rot), dim=-1)

        if past_key_values is not None:
            cache_kwargs = {"sin": sin, "cos": cos, "cache_position": cache_position}
            key_states, value_states = past_key_values.update(
                key_states, value_states, self.layer_idx, cache_kwargs
            )

        is_flash_attention = self.attn_implementation == "flash_attention_2"
        if is_flash_attention and getattr(self.config, "_attn_implementation", None) != self.attn_implementation:
            # transformers >= 5.12 picks the FA kernel from module.config._attn_implementation,
            # which the top-level model resolves to eager (it does not advertise FA support).
            self.config = copy.copy(self.config)
            self.config._attn_implementation = self.attn_implementation
        if is_flash_attention and attention_mask is not None and attention_mask.dim() != 2:
            # Transformers FA2 expects a 2D padding mask (or None).  A 4D eager
            # causal mask makes FA2 enter the wrong varlen path and produces
            # invalid cu_seqlens.  Causality is already represented by
            # module.is_causal, so drop non-2D masks defensively here as well.
            attention_mask = None
        if is_flash_attention and attention_mask is not None:
            attention_mask = attention_mask.to(device=query_states.device, dtype=torch.bool)
            if bool(torch.all(attention_mask)):
                attention_mask = None
        pad_value_for_flash = is_flash_attention and self.q_head_dim != self.v_head_dim
        if pad_value_for_flash:
            value_states = F.pad(value_states, [0, self.q_head_dim - self.v_head_dim])

        attention_interface = eager_attention_forward
        if self.attn_implementation != "eager" and self.attn_implementation in ALL_ATTENTION_FUNCTIONS:
            attention_interface = ALL_ATTENTION_FUNCTIONS[self.attn_implementation]

        attn_output, _ = attention_interface(
            self,
            query_states,
            key_states,
            value_states,
            attention_mask,
            dropout=0.0 if not self.training else self.attention_dropout,
            scaling=self.scaling,
            **kwargs,
        )
        if pad_value_for_flash:
            attn_output = attn_output[:, :, :, : self.v_head_dim]

        if self.g_proj is not None:
            gate = torch.sigmoid(self.g_proj(hidden_states).float()).to(attn_output.dtype)
            if self.mla_output_gate_type == "head_wise":
                gate = gate.unsqueeze(-1)
            else:
                gate = gate.view(batch_size, seq_len, self.num_heads, self.v_head_dim)
            attn_output = attn_output * gate

        attn_output = attn_output.reshape(batch_size, seq_len, self.num_heads * self.v_head_dim)
        return self.o_proj(attn_output)


class YoutuVLCausalDepthwiseConv1d(nn.Conv1d):
    """Pure-PyTorch fallback matching FLA ``ShortConvolution`` semantics.

    ``ShortConvolution`` subclasses ``nn.Conv1d`` and stores weights as
    ``[channels, 1, kernel]``.  Its forward accepts/returns batch-major
    ``[B, T, D]`` tensors, applies causal depthwise convolution, truncates to
    the original sequence length and includes the configured activation inside
    the module.  Keep the same weight shape and call convention so converted
    weights are compatible with both the fused FLA path and this fallback.
    """

    def __init__(
            self,
            channels: int,
            kernel_size: int,
            bias: bool = False,
            activation: str | None = "silu",
    ):
        super().__init__(
            in_channels=channels,
            out_channels=channels,
            kernel_size=kernel_size,
            groups=channels,
            bias=bias,
            padding=kernel_size - 1,
        )
        self.hidden_size = channels
        self.activation = activation
        if activation is not None and activation not in ("silu", "swish"):
            raise ValueError(f"Activation `{activation}` not supported by fallback short conv.")

    def forward(
            self,
            x: torch.Tensor,
            residual: Optional[torch.Tensor] = None,
            mask: Optional[torch.Tensor] = None,
            cache: Optional[torch.Tensor] = None,
            output_final_state: bool = False,
            cu_seqlens: Optional[torch.LongTensor] = None,
            **unused_kwargs,
    ) -> tuple[torch.Tensor, Optional[torch.Tensor]]:
        if mask is not None:
            if cu_seqlens is not None:
                raise ValueError("`mask` and `cu_seqlens` cannot be provided at the same time.")
            x = x.mul(mask.unsqueeze(-1))

        # Decoding step path: B*T == N (one token per sequence).
        # This mirrors FLA ShortConvolution.step().
        B, T, D = x.shape
        N = B if cu_seqlens is None else len(cu_seqlens) - 1
        if B * T == N:
            if cache is None:
                cache = x.new_zeros(N, D, self.kernel_size[0])
            cache = torch.roll(cache, shifts=-1, dims=-1)
            cache[:, :, -1] = x.view(N, T, D)[:, 0, :]
            y_t = (cache * self.weight.squeeze(1).unsqueeze(0)).sum(dim=-1)
            if self.bias is not None:
                y_t = y_t + self.bias
            if residual is not None:
                y_t = y_t + residual.view(N, T, D)[:, 0, :]
            if self.activation in ("silu", "swish"):
                y_t = F.silu(y_t)
            y = y_t.view(B, T, D)
            return y, (cache if output_final_state else None)

        if cu_seqlens is not None:
            # Varlen prefill path: x is [1, total_len, D], split into N segments.
            # Produce per-segment conv_state [N, D, W] when output_final_state=True,
            # matching FLA ShortConvolution's varlen behavior.
            if x.size(0) != 1:
                raise ValueError("Fallback short conv with cu_seqlens expects x shape [1, T, D].")
            boundaries = cu_seqlens.detach().cpu().tolist()
            segments = []
            final_states = []
            for seg_idx, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:])):
                if end <= start:
                    # Empty segment: zero-length output, zero state
                    segments.append(x.new_empty(1, 0, D))
                    if output_final_state:
                        final_states.append(x.new_zeros(D, self.kernel_size[0]))
                    continue
                seg_x = x[:, start:end, :]
                seg_cache = cache[seg_idx] if (cache is not None and seg_idx < cache.shape[0]) else None
                if seg_cache is None:
                    seg_cache = seg_x.new_zeros(D, self.kernel_size[0])
                seg_outputs = []
                for t in range(seg_x.size(1)):
                    seg_cache = torch.roll(seg_cache, shifts=-1, dims=-1)
                    seg_cache[:, -1] = seg_x[0, t, :]
                    y_t = (seg_cache * self.weight.squeeze(1)).sum(dim=-1)
                    if self.bias is not None:
                        y_t = y_t + self.bias
                    if self.activation in ("silu", "swish"):
                        y_t = F.silu(y_t)
                    seg_outputs.append(y_t.unsqueeze(0))
                segments.append(torch.cat(seg_outputs, dim=1))
                if output_final_state:
                    final_states.append(seg_cache)
            if not segments:
                empty = x.new_empty(1, 0, D)
                final = torch.stack(final_states, dim=0) if output_final_state else None
                return empty, final
            y = torch.cat(segments, dim=1).contiguous()
            final = torch.stack(final_states, dim=0) if output_final_state else None
            return y, final

        if cache is not None or output_final_state:
            # Batched prefill path without cu_seqlens: [B, T, D] with [B, D, W] cache.
            if cache is None:
                cache = x.new_zeros(x.size(0), x.size(-1), self.kernel_size[0])
            outputs = []
            for t in range(x.size(1)):
                cache = torch.roll(cache, shifts=-1, dims=-1)
                cache[:, :, -1] = x[:, t, :]
                y_t = (cache * self.weight.squeeze(1).unsqueeze(0)).sum(dim=-1)
                if self.bias is not None:
                    y_t = y_t + self.bias
                if residual is not None:
                    y_t = y_t + residual[:, t, :]
                if self.activation in ("silu", "swish"):
                    y_t = F.silu(y_t)
                outputs.append(y_t.unsqueeze(1))
            return torch.cat(outputs, dim=1), (cache if output_final_state else None)

        # No-cache forward: standard causal depthwise conv
        seq_len = x.size(1)
        y = super().forward(x.transpose(1, 2))[..., :seq_len].transpose(1, 2).contiguous()
        if residual is not None:
            y = y + residual
        if self.activation in ("silu", "swish"):
            y = F.silu(y)
        return y, None


class YoutuVLKDAAttention(nn.Module):
    """FLA-backed Kimi Delta Attention forward path matching Megatron KDA.

    KDA inference keeps its own convolution and recurrent states in
    ``YoutuVLDynamicCache``.  MLA layers in the same decoder keep standard KV
    cache entries through the same hybrid cache object.
    """

    def __init__(self, config: YoutuVLConfig, layer_idx: int):
        super().__init__()
        self.config = config
        self.layer_idx = layer_idx
        self.hidden_size = config.hidden_size
        if chunk_kda is None:
            raise ImportError(
                "FLA is required for UTU-VL KDA inference. Install the training-validated "
                "package version, e.g. `pip install 'flash-linear-attention[cuda]==0.5.2'`; "
                "do not use an unconstrained upgrade."
            )
        self.conv_size = config.short_conv_kernel_size

        self.num_heads = config.num_attention_heads
        self.head_dim = config.head_dim

        self.projection_size = self.num_heads * self.head_dim

        self.kda_gate_lower_bound = config.kda_gate_lower_bound
        self.safe_gate = self.kda_gate_lower_bound is not None

        self.qkv_proj = nn.Linear(self.hidden_size, 3 * self.projection_size, bias=False)
        self.use_fla_short_conv = (
                getattr(config, "kda_use_fla_short_conv", True) and ShortConvolution is not None
        )

        if self.use_fla_short_conv:
            self.conv1d = ShortConvolution(
                hidden_size=3 * self.projection_size,
                kernel_size=self.conv_size,
                bias=False,
                activation="silu",
            )
        else:
            self.conv1d = YoutuVLCausalDepthwiseConv1d(
                channels=3 * self.projection_size,
                kernel_size=self.conv_size,
                bias=False,
                activation="silu",
            )

        self.A_log = nn.Parameter(torch.log(torch.empty(
            self.num_heads, dtype=torch.float32).uniform_(1, 16)))

        self.f_a_proj = nn.Linear(self.hidden_size, self.head_dim, bias=False)
        self.f_b_proj = nn.Linear(self.head_dim, self.projection_size, bias=False)
        self.b_proj = nn.Linear(self.hidden_size, self.num_heads, bias=False)

        self.use_full_rank_gate = getattr(config, "use_full_rank_gate", True)
        if self.use_full_rank_gate:
            self.g_proj = nn.Linear(self.hidden_size, self.projection_size, bias=False)
        else:
            self.g_a_proj = nn.Linear(self.hidden_size, self.head_dim, bias=False)
            self.g_b_proj = nn.Linear(self.head_dim, self.projection_size, bias=True)

        self.dt_bias = nn.Parameter(torch.empty(self.projection_size, dtype=torch.float32))
        self.use_fused_rmsnorm_gated = (
                getattr(config, "kda_use_fused_rmsnorm_gated", True)
                and FusedRMSNormGated is not None
        )
        if self.use_fused_rmsnorm_gated:
            self.out_norm = FusedRMSNormGated(
                self.head_dim, eps=config.rms_norm_eps, activation="sigmoid"
            )
        else:
            self.out_norm = YoutuVLRMSNorm(self.head_dim, eps=config.rms_norm_eps)
        self.out_proj = nn.Linear(self.projection_size, self.hidden_size, bias=False)

    def _apply_short_conv(
            self,
            qkv: torch.Tensor,
            cache: Optional[torch.Tensor] = None,
            output_final_state: bool = False,
            cu_seqlens: Optional[torch.LongTensor] = None,
    ) -> tuple[torch.Tensor, Optional[torch.Tensor]]:
        # qkv: [batch, seq, channels].  FLA ShortConvolution and the fallback both
        # include the SiLU activation internally and return [batch, seq, channels].
        out, conv_state = self.conv1d(
            qkv,
            cache=cache,
            output_final_state=output_final_state,
            cu_seqlens=cu_seqlens,
        )
        return out, conv_state

    @deprecate_kwarg("past_key_value", new_name="past_key_values", version="4.58")
    def forward(
            self,
            hidden_states: torch.Tensor,
            attention_mask: Optional[torch.Tensor],
            cache_params: YoutuVLDynamicCache | None = None,
            **kwargs,
    ):
        if attention_mask is not None:
            if attention_mask.dim() != 2:
                attention_mask = kwargs.get("padding_mask")
            if attention_mask is not None and attention_mask.dim() != 2:
                raise ValueError(
                    "KDA attention_mask must be a 0/1 padding mask of shape [batch, seq]; "
                    "causal 4D masks are only for MLA layers."
                )

        # Save original batch/seq before unpadding; pad_input needs the original
        # padded shape to scatter valid tokens back to [B, S, H].
        orig_batch_size, orig_seq_len, _ = hidden_states.shape
        use_cache = cache_params is not None

        indices = None
        cu_seqlens = kwargs.get("cu_seqlens")
        if attention_mask is not None:
            # When generation decodes one step with cache, TextModel passes None.
            # For prefill with padding, unpad so ShortConvolution/chunk_kda do not
            # mix padding tokens into recurrent state.
            indices, cu_seqlens = get_unpad_data(attention_mask[:, -orig_seq_len:])
            hidden_states = rearrange(hidden_states, "b s ... -> (b s) ...")[indices].unsqueeze(0)

        conv_state = None
        recurrent_state = None
        if use_cache:
            conv_state = cache_params.conv_states[self.layer_idx]
            recurrent_state = cache_params.recurrent_states[self.layer_idx]

        qkv_proj_states = self.qkv_proj(hidden_states)

        qkv, conv_state = self._apply_short_conv(
            qkv_proj_states,
            cache=conv_state,
            output_final_state=use_cache,
            cu_seqlens=cu_seqlens,
        )
        # qkv is unpadded: [1, num_valid, C] (or [B, seq, C] without unpad)
        batch_size, seq_len, _ = qkv.shape
        query, key, value = torch.split(
            qkv, [self.projection_size, self.projection_size, self.projection_size], dim=-1
        )

        query = query.view(batch_size, seq_len, self.num_heads, self.head_dim).contiguous()
        key = key.view(batch_size, seq_len, self.num_heads, self.head_dim).contiguous()
        value = value.view(batch_size, seq_len, self.num_heads, self.head_dim).contiguous()

        f_a = self.f_a_proj(hidden_states)
        g_decay = self.f_b_proj(f_a).view(batch_size, seq_len, self.num_heads, self.head_dim).contiguous()

        beta = self.b_proj(hidden_states).float()

        use_fused_recurrent = use_cache and seq_len == 1 and fused_recurrent_kda is not None

        if use_fused_recurrent:
            core_attn_out, recurrent_state = fused_recurrent_kda(
                q=query,
                k=key,
                v=value,
                g=g_decay,
                beta=beta,
                A_log=self.A_log,
                dt_bias=self.dt_bias,
                initial_state=recurrent_state,
                output_final_state=use_cache,
                use_qk_l2norm_in_kernel=True,
                use_gate_in_kernel=True,
                use_beta_sigmoid_in_kernel=True,
                lower_bound=self.kda_gate_lower_bound,
                transpose_state_layout=True,
                cu_seqlens=cu_seqlens,
            )
        else:
            core_attn_out, recurrent_state = chunk_kda(
                q=query,
                k=key,
                v=value,
                g=g_decay,
                beta=beta,
                A_log=self.A_log,
                dt_bias=self.dt_bias,
                initial_state=recurrent_state,
                output_final_state=use_cache,
                use_qk_l2norm_in_kernel=True,
                use_gate_in_kernel=True,
                use_beta_sigmoid_in_kernel=True,
                safe_gate=self.safe_gate,
                lower_bound=self.kda_gate_lower_bound,
                transpose_state_layout=True,
                cu_seqlens=cu_seqlens,
            )

        if use_cache:
            cache_params.conv_states[self.layer_idx] = conv_state
            cache_params.recurrent_states[self.layer_idx] = recurrent_state

        if self.use_full_rank_gate:
            output_gate = self.g_proj(hidden_states)
        else:
            output_gate = self.g_b_proj(self.g_a_proj(hidden_states))

        output_gate = output_gate.view(
            batch_size, seq_len, self.num_heads, self.head_dim
        )
        if self.use_fused_rmsnorm_gated:
            norm_out = self.out_norm(core_attn_out, output_gate)
        else:
            norm_out = self.out_norm(core_attn_out.reshape(-1, self.head_dim)).view_as(core_attn_out)
            norm_out = norm_out * torch.sigmoid(output_gate.float()).to(norm_out.dtype)
        norm_out = norm_out.reshape(batch_size, seq_len, self.projection_size)
        output = self.out_proj(norm_out)

        if indices is not None:
            output = pad_input(output.squeeze(0), indices, orig_batch_size, orig_seq_len)
        return output


def build_youtu_vl_attention(config: YoutuVLConfig, layer_idx: int) -> nn.Module:
    if getattr(config, "experimental_attention_variant", None) == "kda":
        if _is_kda_layer(config, layer_idx):
            return YoutuVLKDAAttention(config=config, layer_idx=layer_idx)
        return YoutuVLMLAAttention(config=config, layer_idx=layer_idx)
    return YoutuVLAttention(config=config, layer_idx=layer_idx)


# ──────────────────────────────────────────────────────────────────────────────
# Attention（GQA + QKNorm, vanilla softmax, no SWA, no sink）
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLAttention(nn.Module):
    def __init__(self, config: YoutuVLConfig, layer_idx: int):
        super().__init__()
        self.config = config
        self.layer_idx = layer_idx
        self.head_dim = config.head_dim
        self.num_key_value_groups = config.num_attention_heads // config.num_key_value_heads
        self.scaling = self.head_dim ** -0.5
        self.attention_dropout = config.attention_dropout
        self.is_causal = True

        self.q_proj = nn.Linear(config.hidden_size, config.num_attention_heads * self.head_dim, bias=False)
        self.k_proj = nn.Linear(config.hidden_size, config.num_key_value_heads * self.head_dim, bias=False)
        self.v_proj = nn.Linear(config.hidden_size, config.num_key_value_heads * self.head_dim, bias=False)
        self.o_proj = nn.Linear(config.num_attention_heads * self.head_dim, config.hidden_size, bias=False)

        self.q_norm = YoutuVLRMSNorm(self.head_dim, eps=config.rms_norm_eps)
        self.k_norm = YoutuVLRMSNorm(self.head_dim, eps=config.rms_norm_eps)

        self.softmax_offset = None

    @deprecate_kwarg("past_key_value", new_name="past_key_values", version="4.58")
    def forward(
        self,
        hidden_states: torch.Tensor,
        position_embeddings: tuple,
        attention_mask: Optional[torch.Tensor],
        past_key_values: Optional[Cache] = None,
        cache_position: Optional[torch.LongTensor] = None,
        **kwargs,
    ):
        input_shape = hidden_states.shape[:-1]
        hidden_shape = (*input_shape, -1, self.head_dim)

        query_states = self.q_proj(hidden_states).view(hidden_shape).transpose(1, 2)
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0 attn] q_proj: nan={torch.isnan(query_states).sum().item()} max={query_states.abs().max().item():.3f}", flush=True)
        query_states = self.q_norm(query_states)
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0 attn] q_norm: nan={torch.isnan(query_states).sum().item()} max={query_states.abs().max().item():.3f}", flush=True)

        key_states = self.k_proj(hidden_states).view(hidden_shape).transpose(1, 2)
        key_states = self.k_norm(key_states)

        value_states = self.v_proj(hidden_states).view(hidden_shape).transpose(1, 2)

        cos, sin = position_embeddings
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0 attn] cos: nan={torch.isnan(cos).sum().item()} max={cos.abs().max().item():.3f} shape={tuple(cos.shape)}", flush=True)
        query_states, key_states = apply_rotary_pos_emb(query_states, key_states, cos, sin)
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0 attn] after rope q: nan={torch.isnan(query_states).sum().item()} max={query_states.abs().max().item():.3f}", flush=True)

        if past_key_values is not None:
            cache_kwargs = {"sin": sin, "cos": cos, "cache_position": cache_position}
            key_states, value_states = past_key_values.update(key_states, value_states, self.layer_idx, cache_kwargs)

        attention_interface = eager_attention_forward
        if self.config._attn_implementation != "eager":
            attention_interface = ALL_ATTENTION_FUNCTIONS[self.config._attn_implementation]

        attn_output, attn_weights = attention_interface(
            self,
            query_states,
            key_states,
            value_states,
            attention_mask,
            dropout=0.0 if not self.training else self.attention_dropout,
            scaling=self.scaling,
            **kwargs,
        )

        attn_output = attn_output.reshape(*input_shape, -1).contiguous()
        attn_output = self.o_proj(attn_output)
        return attn_output, attn_weights


# ──────────────────────────────────────────────────────────────────────────────
# Decoder Layer
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLDecoderLayer(GradientCheckpointingLayer):
    def __init__(self, config: YoutuVLConfig, layer_idx: int):
        super().__init__()
        self.layer_idx = layer_idx
        self.hidden_size = config.hidden_size
        self.self_attn = build_youtu_vl_attention(config=config, layer_idx=layer_idx)
        self.is_linear_attn = isinstance(self.self_attn, YoutuVLKDAAttention)

        if layer_idx >= config.first_k_dense_replace:
            self.mlp = YoutuVLMoE(config)
        else:
            self.mlp = YoutuVLMLP(config)

        self.input_layernorm = YoutuVLRMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = YoutuVLRMSNorm(config.hidden_size, eps=config.rms_norm_eps)

    @deprecate_kwarg("past_key_value", new_name="past_key_values", version="4.58")
    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.LongTensor] = None,
        past_key_values: Optional[Cache] = None,
        use_cache: Optional[bool] = False,
        cache_position: Optional[torch.LongTensor] = None,
        position_embeddings: Optional[tuple] = None,
        modality_id: Optional[torch.Tensor] = None,
        **kwargs,
    ) -> torch.Tensor:
        residual = hidden_states
        hidden_states = self.input_layernorm(hidden_states)
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0] after input_ln: nan={torch.isnan(hidden_states).sum().item()} max={hidden_states.abs().max().item():.3f}", flush=True)

        if self.is_linear_attn:
            hidden_states = self.self_attn(
                hidden_states=hidden_states,
                attention_mask=attention_mask,
                cache_params=past_key_values,
                **kwargs,
            )
        else:
            attn_out = self.self_attn(
                hidden_states=hidden_states,
                attention_mask=attention_mask,
                position_ids=position_ids,
                past_key_values=past_key_values,
                use_cache=use_cache,
                cache_position=cache_position,
                position_embeddings=position_embeddings,
                **kwargs,
            )
            hidden_states = attn_out[0] if isinstance(attn_out, tuple) else attn_out
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0] after attn: nan={torch.isnan(hidden_states).sum().item()} max={hidden_states.abs().max().item():.3f}", flush=True)
        hidden_states = residual + hidden_states

        residual = hidden_states
        hidden_states = self.post_attention_layernorm(hidden_states)
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0] after post_attn_ln: nan={torch.isnan(hidden_states).sum().item()} max={hidden_states.abs().max().item():.3f}", flush=True)
        if isinstance(self.mlp, YoutuVLMoE):
            hidden_states = self.mlp(hidden_states, modality_id=modality_id)
        else:
            hidden_states = self.mlp(hidden_states)
        if os.environ.get("UTU_DEBUG_NAN") and self.layer_idx == 0:
            print(f"[L0] after mlp: nan={torch.isnan(hidden_states).sum().item()} max={hidden_states.abs().max().item():.3f}", flush=True)
        hidden_states = residual + hidden_states
        return hidden_states


# ──────────────────────────────────────────────────────────────────────────────
# LLM（含 MRoPE Rotary Embedding）
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLTextModel(PreTrainedModel):
    """仅 LLM 部分（无 ViT），带 MRoPE 位置编码。"""

    config_class = YoutuVLConfig
    base_model_prefix = "model"
    supports_gradient_checkpointing = True
    _no_split_modules = ["YoutuVLDecoderLayer"]
    _skip_keys_device_placement = ["past_key_values"]
    _supports_flash_attn = True
    _supports_sdpa = True
    _supports_attention_backend = False
    _can_record_outputs = {}

    def __init__(self, config: YoutuVLConfig):
        _sanitize_youtu_vl_moe_config(config)
        super().__init__(config)
        self.padding_idx = config.pad_token_id
        self.vocab_size = config.vocab_size

        self.embed_tokens = nn.Embedding(config.vocab_size, config.hidden_size, self.padding_idx)
        self.layers = nn.ModuleList([
            YoutuVLDecoderLayer(config, layer_idx) for layer_idx in range(config.num_hidden_layers)
        ])
        self.norm = YoutuVLRMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.rotary_emb = YoutuVLRotaryEmbedding(config=config)
        self.gradient_checkpointing = False
        self.post_init()

    def get_input_embeddings(self):
        return self.embed_tokens

    def set_input_embeddings(self, value):
        self.embed_tokens = value

    @check_model_inputs
    def forward(
        self,
        input_ids: Optional[torch.LongTensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.LongTensor] = None,
        past_key_values: Optional[Cache] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        cache_position: Optional[torch.LongTensor] = None,
        use_cache: Optional[bool] = None,
        modality_id: Optional[torch.Tensor] = None,
        **kwargs,
    ) -> BaseModelOutputWithPast:
        if (input_ids is None) ^ (inputs_embeds is not None):
            raise ValueError("Exactly one of input_ids or inputs_embeds must be specified")

        if inputs_embeds is None:
            inputs_embeds = self.embed_tokens(input_ids)

        is_kda = getattr(self.config, "experimental_attention_variant", None) == "kda"
        if (
            use_cache
            and is_kda
            and past_key_values is not None
            and not isinstance(past_key_values, YoutuVLDynamicCache)
        ):
            # generate() pre-allocates a plain DynamicCache, which has no KDA state.
            if past_key_values.get_seq_length() > 0:
                raise TypeError("KDA models require YoutuVLDynamicCache, got a non-empty "
                                f"{type(past_key_values).__name__}.")
            past_key_values = None
        if use_cache and past_key_values is None:
            if is_kda:
                past_key_values = YoutuVLDynamicCache(config=self.config)
            else:
                past_key_values = DynamicCache(config=self.config)

        if cache_position is None:
            past_seen_tokens = past_key_values.get_seq_length() if past_key_values is not None else 0
            cache_position = torch.arange(
                past_seen_tokens, past_seen_tokens + inputs_embeds.shape[1], device=inputs_embeds.device
            )

        if position_ids is None:
            position_ids = cache_position.unsqueeze(0)

        causal_position_ids = position_ids if position_ids.ndim == 2 else None
        causal_mask = _call_create_causal_mask_compat(
            config=self.config,
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
            cache_position=cache_position,
            past_key_values=past_key_values,
            position_ids=causal_position_ids,
        )

        hidden_states = inputs_embeds
        position_embeddings = self.rotary_emb(hidden_states, position_ids)

        if (
            getattr(self.config, "enable_multimodal_shared_experts", False)
            or getattr(self.config, "moe_router_modality_aware_expert_bias", False)
        ):
            if modality_id is None:
                modality_id = torch.full(
                    hidden_states.shape[:2],
                    MODALITY_TEXT,
                    dtype=torch.int8,
                    device=hidden_states.device,
                )
            else:
                modality_id = modality_id.to(device=hidden_states.device, dtype=torch.int8)
                if modality_id.shape != hidden_states.shape[:2]:
                    raise ValueError(
                        "modality_id must align with decoder hidden states [batch, seq], got "
                        f"{tuple(modality_id.shape)} vs {tuple(hidden_states.shape[:2])}"
                    )

        if attention_mask is not None and attention_mask.dim() == 2:
            flash_attn_mask = None if bool(torch.all(attention_mask == 1)) else attention_mask
        else:
            flash_attn_mask = None
        if cache_position.numel() > 0 and int(cache_position[0].item()) > 0:
            linear_attn_mask = None
        else:
            linear_attn_mask = flash_attn_mask

        for decoder_layer in self.layers:
            if getattr(decoder_layer, "is_linear_attn", False):
                layer_mask = linear_attn_mask
            elif getattr(decoder_layer.self_attn, "attn_implementation", None) == "flash_attention_2":
                layer_mask = flash_attn_mask
            else:
                layer_mask = causal_mask
            hidden_states = decoder_layer(
                hidden_states,
                attention_mask=layer_mask,
                position_ids=position_ids,
                past_key_values=past_key_values,
                cache_position=cache_position,
                position_embeddings=position_embeddings,
                modality_id=modality_id,
                **kwargs,
            )

        hidden_states = self.norm(hidden_states)
        return BaseModelOutputWithPast(
            last_hidden_state=hidden_states,
            past_key_values=past_key_values,
        )


# ──────────────────────────────────────────────────────────────────────────────
# 多模态 Model（LLM + ViT）
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLModel(PreTrainedModel):
    """
    UTU-VL MoE 多模态模型骨干：
    - self.language_model: YoutuVLTextModel（UTU-VL MoE LLM）
    - self.visual: Qwen3VLVisionModel（Qwen3-VL ViT + merger）
    """

    config_class = YoutuVLConfig
    base_model_prefix = "model"
    # 含 Qwen3VLVisionBlock：accelerate device_map 需要视觉块作为 split 点，
    # 否则 self.visual 被当成不透明块，视觉权重（如 pos_embed）不会被加载/放置，
    # 前向时报 "Cannot copy out of meta tensor; no data!"。对齐上游 Qwen3VL 做法。
    _no_split_modules = ["YoutuVLDecoderLayer", "Qwen3VLVisionBlock"]
    _supports_flash_attn = False
    _supports_sdpa = False
    _supports_attention_backend = False

    def __init__(self, config: YoutuVLConfig):
        config._attn_implementation_internal = "eager"
        super().__init__(config)
        self.language_model = YoutuVLTextModel(config)
        self.visual = Qwen3VLVisionModel._from_config(config.vision_config)
        # See _qwen3vl_fast_pos_embed_interpolate_meta_safe above: this keeps
        # image prefill working when HF/Accelerate leaves ViT submodules on
        # meta before per-module dispatch hooks materialize them.
        self.visual.fast_pos_embed_interpolate = (
            _qwen3vl_fast_pos_embed_interpolate_meta_safe.__get__(
                self.visual, self.visual.__class__
            )
        )
        self.rope_deltas = None
        self.post_init()

    def get_input_embeddings(self):
        return self.language_model.embed_tokens

    def set_input_embeddings(self, value):
        self.language_model.embed_tokens = value

    def get_image_features(
        self,
        pixel_values: torch.FloatTensor,
        image_grid_thw: torch.LongTensor,
        **kwargs,
    ) -> BaseModelOutputWithDeepstackFeatures:
        pixel_values = pixel_values.type(self.visual.dtype)
        raw_vision_output = self.visual(pixel_values, grid_thw=image_grid_thw, **kwargs)
        if isinstance(raw_vision_output, tuple):
            pooler_output = raw_vision_output[0]
            deepstack_features = raw_vision_output[1] if len(raw_vision_output) > 1 else None
            vision_output = BaseModelOutputWithDeepstackFeatures(
                pooler_output=pooler_output,
                deepstack_features=deepstack_features,
            )
        else:
            vision_output = raw_vision_output
        split_sizes = (image_grid_thw.prod(-1) // self.visual.spatial_merge_size ** 2).tolist()
        image_embeds = torch.split(vision_output.pooler_output, [int(s) for s in split_sizes])
        vision_output.pooler_output = image_embeds
        return vision_output

    # ── MRoPE 位置 ID 计算 ────────────────────────────────────────────────────

    @staticmethod
    def _get_vision_position_ids(
        start_position: int,
        grid_thw,
        spatial_merge_size: int = 2,
        device=None,
    ) -> torch.Tensor:
        llm_grid_t = grid_thw[0].item()
        llm_grid_h = grid_thw[1].item() // spatial_merge_size
        llm_grid_w = grid_thw[2].item() // spatial_merge_size
        seq = llm_grid_t * llm_grid_h * llm_grid_w

        pos_t = torch.full((seq,), start_position, dtype=torch.long, device=device)
        pos_h = torch.arange(start_position, start_position + llm_grid_h, device=device).repeat_interleave(llm_grid_w * llm_grid_t)
        pos_w = torch.arange(start_position, start_position + llm_grid_w, device=device).repeat(llm_grid_h * llm_grid_t)
        return torch.stack([pos_t, pos_h, pos_w], dim=0)

    def get_rope_index(
        self,
        input_ids: torch.LongTensor,
        mm_token_type_ids: torch.IntTensor,
        image_grid_thw: Optional[torch.LongTensor] = None,
        video_grid_thw: Optional[torch.LongTensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        **kwargs,
    ):
        spatial_merge_size = self.config.vision_config.spatial_merge_size

        position_ids = torch.zeros(
            3, input_ids.shape[0], input_ids.shape[1],
            dtype=input_ids.dtype, device=input_ids.device,
        )
        mrope_position_deltas = []

        grid_iters = {
            1: iter(image_grid_thw) if image_grid_thw is not None else None,
            2: iter(video_grid_thw) if video_grid_thw is not None else None,
        }

        for batch_idx, current_input_ids in enumerate(input_ids):
            input_token_type = mm_token_type_ids[batch_idx]
            if attention_mask is not None:
                mask = attention_mask[batch_idx].bool()
                current_input_ids = current_input_ids[mask]
                input_token_type = input_token_type[mask]

            groups = []
            for key, grp in itertools.groupby(enumerate(input_token_type.tolist()), lambda x: x[1]):
                grp = list(grp)
                groups.append((key, grp[0][0], grp[-1][0] + 1))

            current_pos = 0
            llm_pos_ids_list = []
            for modality_type, start_idx, end_idx in groups:
                if modality_type == 0:
                    text_len = end_idx - start_idx
                    llm_pos_ids_list.append(
                        torch.arange(text_len, device=input_ids.device)
                        .view(1, -1).expand(3, -1) + current_pos
                    )
                    current_pos += text_len
                else:
                    grid_thw = next(grid_iters[modality_type])
                    vision_pos = self._get_vision_position_ids(
                        current_pos, grid_thw,
                        spatial_merge_size=spatial_merge_size,
                        device=input_ids.device,
                    )
                    llm_pos_ids_list.append(vision_pos)
                    current_pos += max(grid_thw[1], grid_thw[2]).item() // spatial_merge_size

            llm_positions = torch.cat(llm_pos_ids_list, dim=1).reshape(3, -1)
            if attention_mask is not None:
                position_ids[:, batch_idx, attention_mask[batch_idx].bool()] = llm_positions
            else:
                position_ids[:, batch_idx] = llm_positions
            mrope_position_deltas.append(llm_positions.max() + 1 - len(current_input_ids))

        mrope_position_deltas = torch.tensor(mrope_position_deltas, device=input_ids.device).unsqueeze(1)
        return position_ids, mrope_position_deltas

    def compute_3d_position_ids(
        self,
        input_ids,
        inputs_embeds,
        image_grid_thw=None,
        video_grid_thw=None,
        attention_mask=None,
        past_key_values=None,
        mm_token_type_ids=None,
    ):
        past_length = 0 if past_key_values is None else past_key_values.get_seq_length()
        can_compute = (
            input_ids is not None
            and mm_token_type_ids is not None
            and (image_grid_thw is not None or video_grid_thw is not None)
        )

        if can_compute and (self.rope_deltas is None or past_length == 0):
            position_ids, rope_deltas = self.get_rope_index(
                input_ids,
                mm_token_type_ids=mm_token_type_ids,
                image_grid_thw=image_grid_thw,
                video_grid_thw=video_grid_thw,
                attention_mask=attention_mask,
            )
            self.rope_deltas = rope_deltas
        elif self.rope_deltas is not None:
            batch_size, seq_length, _ = inputs_embeds.shape
            if attention_mask is not None:
                position_ids = attention_mask.long().cumsum(-1) - 1
                position_ids = position_ids.masked_fill(attention_mask == 0, 0)
                position_ids = position_ids.view(1, batch_size, -1).repeat(3, 1, 1).to(inputs_embeds.device)
            else:
                position_ids = torch.arange(past_length, past_length + seq_length)
                position_ids = position_ids.view(1, 1, -1).expand(3, batch_size, -1).to(inputs_embeds.device)
            delta = self.rope_deltas.repeat_interleave(batch_size // self.rope_deltas.shape[0], dim=0)
            position_ids = position_ids + delta.to(inputs_embeds.device)
        else:
            position_ids = None
        return position_ids

    def get_placeholder_mask(self, input_ids, inputs_embeds, image_features=None, video_features=None):
        if input_ids is None:
            special_image_mask = (inputs_embeds == self.get_input_embeddings()(
                torch.tensor(self.config.image_token_id, dtype=torch.long, device=inputs_embeds.device)
            )).all(-1)
            if self.config.video_token_id is not None:
                special_video_mask = (inputs_embeds == self.get_input_embeddings()(
                    torch.tensor(self.config.video_token_id, dtype=torch.long, device=inputs_embeds.device)
                )).all(-1)
            else:
                special_video_mask = torch.zeros(inputs_embeds.shape[:-1], dtype=torch.bool, device=inputs_embeds.device)
        else:
            special_image_mask = input_ids == self.config.image_token_id
            if self.config.video_token_id is not None:
                special_video_mask = input_ids == self.config.video_token_id
            else:
                special_video_mask = torch.zeros_like(input_ids, dtype=torch.bool)

        special_image_mask = special_image_mask.unsqueeze(-1).expand_as(inputs_embeds).to(inputs_embeds.device)
        special_video_mask = special_video_mask.unsqueeze(-1).expand_as(inputs_embeds).to(inputs_embeds.device)
        return special_image_mask, special_video_mask

    def build_decoder_modality_id(
        self,
        input_ids: Optional[torch.LongTensor],
        inputs_embeds: torch.FloatTensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> Optional[torch.Tensor]:
        """Build token-level modality ids for dual shared experts / router bias.

        Shape is batch-major ``[batch, seq]`` to match this HF implementation.
        It classifies the token itself: only image/video placeholder tokens are
        vision; ordinary text inside a VL sample remains text. Padding positions
        select zero shared-expert output and the text router-bias row.
        """
        if not _needs_decoder_modality_id(self.config):
            return None

        if input_ids is not None:
            modality_id = torch.full_like(
                input_ids,
                fill_value=MODALITY_TEXT,
                dtype=torch.int8,
                device=input_ids.device,
            )
            vision_mask = input_ids == self.config.image_token_id
            if self.config.video_token_id is not None:
                vision_mask = vision_mask | (input_ids == self.config.video_token_id)
        else:
            modality_id = torch.full(
                inputs_embeds.shape[:2],
                fill_value=MODALITY_TEXT,
                dtype=torch.int8,
                device=inputs_embeds.device,
            )
            image_token_embed = self.get_input_embeddings()(
                torch.tensor(self.config.image_token_id, dtype=torch.long, device=inputs_embeds.device)
            )
            vision_mask = (inputs_embeds == image_token_embed).all(-1)
            if self.config.video_token_id is not None:
                video_token_embed = self.get_input_embeddings()(
                    torch.tensor(self.config.video_token_id, dtype=torch.long, device=inputs_embeds.device)
                )
                vision_mask = vision_mask | (inputs_embeds == video_token_embed).all(-1)

        modality_id = torch.where(
            vision_mask,
            torch.full_like(modality_id, MODALITY_VISION),
            modality_id,
        )

        if attention_mask is not None and attention_mask.shape[-1] == modality_id.shape[-1]:
            pad_mask = ~attention_mask.to(device=modality_id.device, dtype=torch.bool)
            modality_id = torch.where(
                pad_mask,
                torch.full_like(modality_id, MODALITY_PAD),
                modality_id,
            )
        return modality_id.contiguous()

    def forward(
        self,
        input_ids: Optional[torch.LongTensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.LongTensor] = None,
        past_key_values: Optional[Cache] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        pixel_values: Optional[torch.Tensor] = None,
        pixel_values_videos: Optional[torch.FloatTensor] = None,
        image_grid_thw: Optional[torch.LongTensor] = None,
        video_grid_thw: Optional[torch.LongTensor] = None,
        mm_token_type_ids: Optional[torch.IntTensor] = None,
        cache_position: Optional[torch.LongTensor] = None,
        use_cache: Optional[bool] = None,
        **kwargs,
    ) -> BaseModelOutputWithPast:
        if (input_ids is None) ^ (inputs_embeds is not None):
            raise ValueError("Exactly one of input_ids or inputs_embeds must be specified")

        if inputs_embeds is None:
            inputs_embeds = self.get_input_embeddings()(input_ids)

        decoder_modality_id = self.build_decoder_modality_id(
            input_ids=input_ids,
            inputs_embeds=inputs_embeds,
            attention_mask=attention_mask,
        )

        # ── 视觉编码 ──────────────────────────────────────────────────────────
        if pixel_values is not None:
            image_out = self.get_image_features(pixel_values, image_grid_thw)
            image_embeds = torch.cat(image_out.pooler_output, dim=0).to(inputs_embeds.device, inputs_embeds.dtype)
            image_mask, _ = self.get_placeholder_mask(input_ids, inputs_embeds, image_features=image_embeds)
            inputs_embeds = inputs_embeds.masked_scatter(image_mask, image_embeds)

        if pixel_values_videos is not None:
            video_out = self.get_image_features(pixel_values_videos, video_grid_thw)
            video_embeds = torch.cat(video_out.pooler_output, dim=0).to(inputs_embeds.device, inputs_embeds.dtype)
            _, video_mask = self.get_placeholder_mask(input_ids, inputs_embeds, video_features=video_embeds)
            inputs_embeds = inputs_embeds.masked_scatter(video_mask, video_embeds)

        # Reconstruct mm_token_type_ids if the processor did not provide it.
        if mm_token_type_ids is None and input_ids is not None and (image_grid_thw is not None or video_grid_thw is not None):
            mm_token_type_ids = torch.zeros_like(input_ids, dtype=torch.int32, device=input_ids.device)
            if image_grid_thw is not None:
                mm_token_type_ids = mm_token_type_ids.masked_fill(input_ids == self.config.image_token_id, 1)
            if video_grid_thw is not None and self.config.video_token_id is not None:
                mm_token_type_ids = mm_token_type_ids.masked_fill(input_ids == self.config.video_token_id, 2)

        # ── 计算 3D MRoPE 位置 ID ─────────────────────────────────────────────
        if position_ids is None:
            position_ids = self.compute_3d_position_ids(
                input_ids=input_ids,
                inputs_embeds=inputs_embeds,
                image_grid_thw=image_grid_thw,
                video_grid_thw=video_grid_thw,
                attention_mask=attention_mask,
                past_key_values=past_key_values,
                mm_token_type_ids=mm_token_type_ids,
            )

        # ── LLM 前向 ─────────────────────────────────────────────────────────
        return self.language_model(
            input_ids=None,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            cache_position=cache_position,
            use_cache=use_cache,
            modality_id=decoder_modality_id,
            **kwargs,
        )


# ──────────────────────────────────────────────────────────────────────────────
# 顶层 CausalLM 模型
# ──────────────────────────────────────────────────────────────────────────────

class YoutuVLForConditionalGeneration(PreTrainedModel, GenerationMixin):
    """
    UTU-VL MoE 多模态生成模型（transformers 5.3 适配版）。
    """

    config_class = YoutuVLConfig
    _tied_weights_keys = []
    base_model_prefix = "model"
    supports_gradient_checkpointing = True
    _no_split_modules = ["YoutuVLDecoderLayer", "Qwen3VLVisionBlock"]
    _supports_flash_attn = False
    _supports_sdpa = False
    _supports_attention_backend = False

    def __init__(self, config: YoutuVLConfig):
        config._attn_implementation_internal = "eager"
        super().__init__(config)
        self.model = YoutuVLModel(config)
        self.vocab_size = config.vocab_size
        self.lm_head = nn.Linear(config.hidden_size, config.vocab_size, bias=False)
        self.post_init()

    def get_input_embeddings(self):
        return self.model.get_input_embeddings()

    def set_input_embeddings(self, value):
        self.model.set_input_embeddings(value)

    def get_output_embeddings(self):
        return self.lm_head

    def set_output_embeddings(self, new_embeddings):
        self.lm_head = new_embeddings

    def get_image_features(self, pixel_values, image_grid_thw=None, **kwargs):
        return self.model.get_image_features(pixel_values, image_grid_thw, **kwargs)

    @can_return_tuple
    def forward(
        self,
        input_ids: Optional[torch.LongTensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        position_ids: Optional[torch.LongTensor] = None,
        past_key_values: Optional[Cache] = None,
        inputs_embeds: Optional[torch.FloatTensor] = None,
        labels: Optional[torch.LongTensor] = None,
        pixel_values: Optional[torch.Tensor] = None,
        pixel_values_videos: Optional[torch.FloatTensor] = None,
        image_grid_thw: Optional[torch.LongTensor] = None,
        video_grid_thw: Optional[torch.LongTensor] = None,
        mm_token_type_ids: Optional[torch.IntTensor] = None,
        cache_position: Optional[torch.LongTensor] = None,
        logits_to_keep: Union[int, torch.Tensor] = 0,
        use_cache: Optional[bool] = None,
        **kwargs,
    ) -> CausalLMOutputWithPast:
        outputs = self.model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            position_ids=position_ids,
            past_key_values=past_key_values,
            inputs_embeds=inputs_embeds,
            pixel_values=pixel_values,
            pixel_values_videos=pixel_values_videos,
            image_grid_thw=image_grid_thw,
            video_grid_thw=video_grid_thw,
            mm_token_type_ids=mm_token_type_ids,
            cache_position=cache_position,
            use_cache=use_cache,
            **kwargs,
        )

        hidden_states = outputs.last_hidden_state
        slice_indices = slice(-logits_to_keep, None) if isinstance(logits_to_keep, int) else logits_to_keep
        logits = self.lm_head(hidden_states[:, slice_indices, :])

        loss = None
        if labels is not None:
            loss = self.loss_function(logits=logits, labels=labels, vocab_size=self.config.vocab_size, **kwargs)

        return CausalLMOutputWithPast(
            loss=loss,
            logits=logits,
            past_key_values=outputs.past_key_values,
            hidden_states=outputs.hidden_states,
            attentions=outputs.attentions,
        )

    def prepare_inputs_for_generation(
        self,
        input_ids,
        past_key_values=None,
        attention_mask=None,
        inputs_embeds=None,
        cache_position=None,
        position_ids=None,
        use_cache=True,
        pixel_values=None,
        pixel_values_videos=None,
        image_grid_thw=None,
        video_grid_thw=None,
        mm_token_type_ids=None,
        is_first_iteration=False,
        **kwargs,
    ):
        try:
            _past_seen = past_key_values.get_seq_length() if past_key_values is not None else 0
        except Exception:
            _past_seen = 0
        _is_decode = _past_seen > 0

        extra = dict(kwargs)
        try:
            import inspect as _inspect
            base_sig = _inspect.signature(super().prepare_inputs_for_generation)
            if "is_first_iteration" in base_sig.parameters:
                extra["is_first_iteration"] = is_first_iteration
        except Exception:
            pass

        model_inputs = super().prepare_inputs_for_generation(
            input_ids,
            past_key_values=past_key_values,
            attention_mask=attention_mask,
            inputs_embeds=inputs_embeds,
            cache_position=cache_position,
            position_ids=position_ids,
            use_cache=use_cache,
            pixel_values=pixel_values,
            pixel_values_videos=pixel_values_videos,
            image_grid_thw=image_grid_thw,
            video_grid_thw=video_grid_thw,
            mm_token_type_ids=mm_token_type_ids,
            **extra,
        )

        if _is_decode:
            # ── Decode step ────────────────────────────────────────────────
            if use_cache:
                model_inputs["pixel_values"] = None
                model_inputs["pixel_values_videos"] = None
            model_inputs["image_grid_thw"] = None
            model_inputs["video_grid_thw"] = None
            model_inputs["mm_token_type_ids"] = None

            batch_size = input_ids.shape[0]
            device = input_ids.device

            step_ids = model_inputs.get("input_ids", input_ids)
            step_len = int(step_ids.shape[1]) if step_ids is not None and step_ids.ndim == 2 else 1
            decode_cache_position = torch.arange(
                _past_seen, _past_seen + step_len, device=device, dtype=torch.long
            )
            model_inputs["cache_position"] = decode_cache_position

            if self.model.rope_deltas is not None:
                delta = self.model.rope_deltas.to(device)
                if delta.ndim == 1:
                    delta = delta.view(-1, 1)
                if delta.shape[0] != batch_size:
                    if batch_size % delta.shape[0] != 0:
                        raise RuntimeError(
                            f"rope_deltas batch mismatch: {delta.shape[0]} vs {batch_size}"
                        )
                    delta = delta.repeat_interleave(batch_size // delta.shape[0], dim=0)
                delta = delta.view(1, batch_size, 1).long()
            else:
                delta = torch.zeros((1, batch_size, 1), device=device, dtype=torch.long)

            base_pos = decode_cache_position.view(1, 1, step_len).expand(3, batch_size, step_len)
            model_inputs["position_ids"] = base_pos + delta
        else:
            # ── Prefill step ───────────────────────────────────────────────
            _ids = input_ids

            if mm_token_type_ids is None and _ids is not None and (image_grid_thw is not None or video_grid_thw is not None):
                mm_token_type_ids = torch.zeros_like(_ids, dtype=torch.int32, device=_ids.device)
                if image_grid_thw is not None:
                    mm_token_type_ids = mm_token_type_ids.masked_fill(
                        _ids == self.config.image_token_id, 1
                    )
                if video_grid_thw is not None and self.config.video_token_id is not None:
                    mm_token_type_ids = mm_token_type_ids.masked_fill(
                        _ids == self.config.video_token_id, 2
                    )

            has_vision = (
                _ids is not None
                and mm_token_type_ids is not None
                and (image_grid_thw is not None or video_grid_thw is not None)
            )
            if has_vision:
                vision_positions, rope_deltas = self.model.get_rope_index(
                    _ids,
                    mm_token_type_ids=mm_token_type_ids,
                    image_grid_thw=image_grid_thw,
                    video_grid_thw=video_grid_thw,
                    attention_mask=attention_mask,
                )
                self.model.rope_deltas = rope_deltas
                model_inputs["position_ids"] = vision_positions
            else:
                _pos_2d = model_inputs.get("position_ids")
                if _pos_2d is None:
                    seq_len = input_ids.shape[1]
                    _pos_2d = torch.arange(seq_len, device=input_ids.device).unsqueeze(0).expand(
                        input_ids.shape[0], -1
                    )
                model_inputs["position_ids"] = _pos_2d[None, ...].expand(3, -1, -1).clone()
                self.model.rope_deltas = torch.zeros(
                    input_ids.shape[0], 1, dtype=torch.long, device=input_ids.device
                )

        return model_inputs


# ── Public aliases ────────────────────────────────────────────────────────────────
YoutuVLMoEForConditionalGeneration = YoutuVLForConditionalGeneration
YoutuVLMoEModel = YoutuVLModel
YoutuVLMoETextModel = YoutuVLTextModel

__all__ = [
    "YoutuVLMoEConfig",
    "YoutuVLMoEForConditionalGeneration",
    "YoutuVLMoEModel",
    "YoutuVLMoETextModel",
]
