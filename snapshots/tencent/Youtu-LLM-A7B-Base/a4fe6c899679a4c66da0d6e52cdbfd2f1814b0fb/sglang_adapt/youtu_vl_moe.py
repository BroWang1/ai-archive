# SPDX-License-Identifier: Apache-2.0
"""SGLang 原生推理实现：UTU-VL-120B KDA MoE。

架构：UTU-VL-120B LLM（KDA + Gated MLA hybrid attention, QB sigmoid MoE
      [256 experts global top-8, modality-aware qb_beta, 1 shared expert] +
      interleaved MRoPE, no SWA, no sink, no DeepStack）
      + Qwen3-VL MoE ViT。

对应训练脚本：vlm_patch/scripts/train_youtu_v2_pro_120b.sh
参考实现：
- utu_vl_30b_v4/sglang_adapt/utu_vl_v4.py        : V4 sglang 骨架
- sglang/srt/models/qwen3_vl.py                   : 顶层多模态模型 + Qwen3VLMoeVisionModel 复用
- sglang/srt/models/qwen3_vl_moe.py               : MoE VLM 顶层 load_weights
- sglang/srt/models/qwen3_moe.py                  : GQA + QKNorm + RadixAttention / decoder / model
- sglang/srt/models/deepseek_v2.py                : sigmoid routing MoE + shared experts

注册方式：本模块末尾 `EntryClass = YoutuVLMoEForConditionalGeneration`，类名须与
checkpoint config.json 的 architectures[0] 一致。通过环境变量
SGLANG_EXTERNAL_MODEL_PACKAGE=sglang_adapt 注册。
"""

import os
from typing import Iterable, List, Optional, Tuple

import torch
import torch.nn as nn
import torch.nn.functional as F

from sglang.srt.layers.activation import SiluAndMul
from sglang.srt.layers.layernorm import RMSNorm
from sglang.kernels.ops.attention.fla.fused_norm_gate import FusedRMSNormGated
from sglang.srt.layers.linear import (
    ColumnParallelLinear,
    MergedColumnParallelLinear,
    QKVParallelLinear,
    ReplicatedLinear,
    RowParallelLinear,
)
from sglang.srt.layers.logits_processor import LogitsProcessor
from sglang.srt.layers.moe.fused_moe_triton.layer import FusedMoE
from sglang.srt.layers.moe.token_dispatcher import standard as _sgl_standard_dispatch
from sglang.srt.layers.moe.token_dispatcher.standard import StandardDispatcher
from sglang.srt.layers.moe.topk import StandardTopKOutput
from sglang.srt.layers.radix_attention import RadixAttention
from sglang.srt.layers.radix_linear_attention import RadixLinearAttention
from sglang.srt.layers.rotary_embedding import get_rope
from sglang.srt.layers.vocab_parallel_embedding import (
    ParallelLMHead,
    VocabParallelEmbedding,
)
from sglang.srt.distributed.parallel_state import get_pp_group
from sglang.srt.distributed import (
    moe_expert_parallel_all_reduce,
    moe_tensor_model_parallel_all_reduce,
    tensor_model_parallel_all_reduce,
)
from sglang.srt.layers.moe import should_skip_post_experts_all_reduce
from sglang.srt.layers.quantization.base_config import QuantizationConfig
from sglang.srt.layers.quantization.unquant import UnquantizedLinearMethod
from sglang.srt.layers.utils import get_layer_id
from sglang.srt.managers.mm_utils import (
    MultiModalityDataPaddingPatternMultimodalTokens,
    general_mm_embed_routine,
)
from sglang.srt.managers.schedule_batch import MultimodalDataItem
from sglang.srt.model_executor.forward_batch_info import ForwardBatch, PPProxyTensors
from sglang.srt.model_executor.runner import get_is_capture_mode
from sglang.srt.model_executor.runner_backend_utils.breakable_cuda_graph.context import (
    is_in_breakable_cuda_graph,
)
from sglang.srt.layers.communicator import (
    AttentionInputs,
    get_attn_tp_context,
)
from sglang.srt.model_loader.weight_utils import default_weight_loader, sharded_weight_loader
from sglang.srt.models.qwen3_vl import Qwen3VLMoeVisionModel
from sglang.srt.models.deepseek_v2 import DeepseekV2AttentionMLA
from sglang.srt.runtime_context import get_model, get_parallel, get_stream
from sglang.srt.server_args import get_global_server_args
from sglang.srt.utils import is_blackwell_supported
from sglang.srt.utils.common import BumpAllocator, add_prefix, set_weight_attrs
from sglang_adapt.fused_ops import deinterleave_rope_pair, sigmoid_gate_mul
from sglang_adapt.qb_routing import (
    gate_gemv,
    qb_route,
    select_bias_rows,
    to_local_expert_ids,
)
from sglang_adapt.vl_modality import (
    GRANULARITY_SAMPLE,
    GRANULARITY_TOKEN,
    VL_MODALITY,
    VL_SHARED_MODALITY,
    modality_granularity,
)


# Defaults for direct Python launches; the serve helper enables validated
# KDA/remap optimizations explicitly. Keep numerical fallbacks for comparison.
_SHARED_EXPERT_OVERLAP = os.environ.get("UTU_SHARED_EXPERT_OVERLAP", "1") == "1"
_FUSED_GATE_GEMV = os.environ.get("UTU_FUSED_GATE_GEMV", "1") == "1"
_FUSED_KDA_DECODE = os.environ.get("UTU_FUSED_KDA_DECODE", "0") == "1"
_FUSED_OUTPUT_GATE = os.environ.get("UTU_FUSED_OUTPUT_GATE", "1") == "1"
_FUSED_ROPE_REORDER = os.environ.get("UTU_FUSED_ROPE_REORDER", "1") == "1"
_FUSED_EXPERT_REMAP = os.environ.get("UTU_FUSED_EXPERT_REMAP", "0") == "1"


def _merge_weights_as_views(
    mods: list, pad_rows_to: int = 1
) -> Tuple[torch.Tensor, List[int]]:
    """Concatenate local weight rows and keep original parameters as shared views."""
    ws = [m.weight.data for m in mods]
    sizes = [w.shape[0] for w in ws]
    pad = (-sum(sizes)) % pad_rows_to
    if pad:
        ws = ws + [ws[0].new_zeros((pad, ws[0].shape[1]))]
    merged = torch.cat(ws, dim=0).contiguous()
    off = 0
    for m, n in zip(mods, sizes):
        m.weight.data = merged[off : off + n]
        off += n
    return merged, sizes


def _mergeable(mods: list) -> bool:
    """Merge only compatible unquantized, bias-free dense projections."""
    dtypes = set()
    for mod in mods:
        if not isinstance(getattr(mod, "quant_method", None), UnquantizedLinearMethod):
            return False
        weight = getattr(mod, "weight", None)
        if weight is None or weight.ndim != 2 or weight.dtype not in (
            torch.float16, torch.bfloat16, torch.float32,
        ):
            return False
        if getattr(mod, "bias", None) is not None:
            return False
        if any(
            hasattr(mod, attr)
            for attr in ("weight_scale", "weight_scale_inv", "input_scale")
        ):
            return False
        dtypes.add(weight.dtype)
    return (
        bool(mods)
        and len(dtypes) == 1
        and len({m.weight.shape[1] for m in mods}) == 1
        and len({m.weight.device for m in mods}) == 1
    )


def _quantile_balancing_enabled(config) -> bool:
    method = getattr(config, "moe_router_expert_bias_update_method", "sign")
    topk_method = getattr(config, "topk_method", "noaux_tc")
    return method == "quantile" or topk_method in ("quantile_balancing", "quantile")


# ──────────────────────────────────────────────────────────────────────────────
# LLM 组件
# ──────────────────────────────────────────────────────────────────────────────


def _sglang_rope_scaling(config) -> dict:
    """把 HF config.rope_scaling 传给 sglang get_rope，并始终带上 MRoPE。

    原生 4k/32k：rope_scaling 为空 → rope_type=default + mrope_section
    （MRotaryEmbedding）。
    extend 评测：config 写 yarn + factor + original_max → YaRNScalingMRotaryEmbedding。
    mrope_interleaved 必须 True（交错 THW），与训练一致。
    """
    section = list(getattr(config, "mrope_section", [12, 10, 10]))
    scaling = getattr(config, "rope_scaling", None) or {}
    if not isinstance(scaling, dict):
        scaling = {}
    rope_type = scaling.get("rope_type") or scaling.get("type") or "default"
    out = {
        "rope_type": rope_type,
        "mrope_section": list(scaling["mrope_section"]) if scaling.get("mrope_section") else section,
        "mrope_interleaved": True,
    }
    if rope_type == "yarn":
        for key in (
            "factor",
            "original_max_position_embeddings",
            "extrapolation_factor",
            "attn_factor",
            "beta_fast",
            "beta_slow",
            "mscale",
            "mscale_all_dim",
        ):
            if key in scaling:
                out[key] = scaling[key]
    return out


class YoutuVLMLP(nn.Module):
    """Dense SiLU MLP（用于 first_k_dense_replace 之前的层，或作为 shared expert）。

    当作为 shared expert 时传 intermediate_size 覆盖 + reduce_results=False，
    由调用方在 MoE 末尾统一做 TP all-reduce。
    """

    def __init__(
        self,
        config,
        intermediate_size: Optional[int] = None,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
        reduce_results: bool = True,
    ):
        super().__init__()
        intermediate_size = config.intermediate_size if intermediate_size is None else intermediate_size
        self.gate_up_proj = MergedColumnParallelLinear(
            config.hidden_size,
            [intermediate_size] * 2,
            bias=False,
            quant_config=quant_config,
            prefix=add_prefix("gate_up_proj", prefix),
        )
        self.down_proj = RowParallelLinear(
            intermediate_size,
            config.hidden_size,
            bias=False,
            quant_config=quant_config,
            reduce_results=reduce_results,
            prefix=add_prefix("down_proj", prefix),
        )
        self.act_fn = SiluAndMul()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gate_up, _ = self.gate_up_proj(x)
        x = self.act_fn(gate_up)
        x, _ = self.down_proj(x)
        return x


class YoutuVLGate(nn.Module):
    """MoE router: sigmoid + Quantile Balancing or noaux_tc correction bias.

    Supports both upstream [E] bias and MMOE [2, E] text/VL bias rows.
    QB stores ``qb_beta`` (fp32 buffer) and selects in the raw-logit domain.
    """

    def __init__(self, config, prefix: str = ""):
        super().__init__()
        # HF computes router logits in fp32.  Hold the weight in fp32 rather
        # than casting a [E, hidden] copy on every call of every MoE layer.
        self.weight = nn.Parameter(
            torch.empty(
                (config.n_routed_experts, config.hidden_size), dtype=torch.float32
            )
        )
        self.use_expert_bias = getattr(
            config, "moe_router_enable_expert_bias", True
        )
        self.use_quantile_balancing = _quantile_balancing_enabled(config)
        if self.use_quantile_balancing and not self.use_expert_bias:
            raise ValueError("Quantile Balancing requires expert bias to be enabled.")
        bias_shape = (
            (2, config.n_routed_experts)
            if getattr(config, "moe_router_modality_aware_expert_bias", False)
            else (config.n_routed_experts,)
        )
        if not self.use_expert_bias:
            self.qb_beta = None
            self.e_score_correction_bias = None
        elif self.use_quantile_balancing:
            self.register_buffer(
                "qb_beta", torch.zeros(bias_shape, dtype=torch.float32)
            )
            self.e_score_correction_bias = None
        else:
            self.e_score_correction_bias = nn.Parameter(
                torch.empty(bias_shape, dtype=torch.float32)
            )
            self.qb_beta = None

    def _apply(self, fn):
        super()._apply(fn)
        for name in ("weight", "qb_beta", "e_score_correction_bias"):
            tensor = getattr(self, name, None)
            if isinstance(tensor, torch.Tensor) and tensor.dtype != torch.float32:
                tensor.data = tensor.data.float()
        return self

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        if _FUSED_GATE_GEMV:
            fused = gate_gemv(hidden_states, self.weight)
            if fused is not None:
                return fused
        return F.linear(hidden_states.float(), self.weight, None)

    def correction_bias_for(
        self, router_logits: torch.Tensor, modality_id: Optional[torch.Tensor]
    ) -> torch.Tensor:
        """Return [E] or per-token [T, E] sign-method correction bias."""
        if self.e_score_correction_bias is None:
            raise RuntimeError("sign-method routing requires e_score_correction_bias.")
        return select_bias_rows(
            self.e_score_correction_bias.float(),
            router_logits.shape[0],
            modality_id,
        )


class YoutuVLMultiModalSharedExperts(nn.Module):
    """Dual shared experts selected by token modality.

    SGLang forwards flattened hidden states [tokens, hidden]; modality_id is a
    flattened int8 tensor where 0=text, 1=vision, -1=padding.  Decode steps and
    text-only callers default to all-text.
    """

    def __init__(
        self,
        config,
        intermediate_size: int,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.text = YoutuVLMLP(
            config,
            intermediate_size=intermediate_size,
            quant_config=quant_config,
            prefix=add_prefix("text", prefix),
            reduce_results=False,
        )
        self.vision = YoutuVLMLP(
            config,
            intermediate_size=intermediate_size,
            quant_config=quant_config,
            prefix=add_prefix("vision", prefix),
            reduce_results=False,
        )

    def forward(
        self, hidden_states: torch.Tensor, modality_id: Optional[torch.Tensor]
    ) -> torch.Tensor:
        if modality_id is None:
            modality_id = torch.zeros(
                hidden_states.shape[0], dtype=torch.int8, device=hidden_states.device
            )
        modality_id = modality_id.reshape(-1).to(device=hidden_states.device)
        if modality_id.shape[0] != hidden_states.shape[0]:
            raise ValueError(
                "modality_id must align with flattened hidden states, got "
                f"{tuple(modality_id.shape)} vs {tuple(hidden_states.shape)}"
            )
        text_out = self.text(hidden_states)
        vision_out = self.vision(hidden_states)
        text_mask = (modality_id == 0).unsqueeze(-1).to(dtype=text_out.dtype)
        vision_mask = (modality_id == 1).unsqueeze(-1).to(dtype=vision_out.dtype)
        return text_out * text_mask + vision_out * vision_mask


class YoutuVLMoE(nn.Module):
    """sigmoid routing MoE + 1 shared expert（参考 deepseek_v2.DeepseekV2MoE 简化）。

    QB uses global top-k; sign-method routing uses the local grouped-topk formula.
    shared expert 以 reduce_results=False 的独立 MLP 实现，输出在 all-reduce 之前并入。
    """

    def __init__(
        self,
        config,
        layer_id: int,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.hidden_size = config.hidden_size
        self.layer_id = layer_id
        self.routed_scaling_factor = config.routed_scaling_factor
        self.tp_size = get_parallel().moe_tp_size
        self.ep_size = get_parallel().moe_ep_size
        self.n_shared_experts = getattr(config, "n_shared_experts", 0)
        self.top_k = config.num_experts_per_tok
        self.n_group = config.n_group
        self.topk_group = config.topk_group
        self.norm_topk_prob = config.norm_topk_prob
        self.use_expert_bias = getattr(
            config, "moe_router_enable_expert_bias", True
        )
        self.use_quantile_balancing = _quantile_balancing_enabled(config)
        self.moe_latent_size = getattr(config, "moe_latent_size", None)
        expert_hidden_size = self.moe_latent_size or config.hidden_size

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
                self.latent_rmsnorm = RMSNorm(
                    self.moe_latent_size, eps=config.rms_norm_eps
                )

        self.gate = YoutuVLGate(config, prefix=add_prefix("gate", prefix))

        self.experts = FusedMoE(
            num_experts=config.n_routed_experts,
            top_k=config.num_experts_per_tok,
            hidden_size=expert_hidden_size,
            intermediate_size=config.moe_intermediate_size,
            layer_id=layer_id,
            quant_config=quant_config,
            routed_scaling_factor=config.routed_scaling_factor,
            prefix=add_prefix("experts", prefix),
        )

        # Shared expert path.  Tiny MMOE checkpoints use dual text/vision shared
        # branches; both are dense MLPs selected by token modality before the
        # final EP/TP all-reduce.
        if self.n_shared_experts is not None and self.n_shared_experts > 0:
            shared_intermediate = getattr(
                config, "moe_shared_experts_intermediate_size",
                config.moe_intermediate_size * self.n_shared_experts,
            )
            if getattr(config, "enable_multimodal_shared_experts", False):
                self.shared_experts = YoutuVLMultiModalSharedExperts(
                    config,
                    intermediate_size=shared_intermediate,
                    quant_config=quant_config,
                    prefix=add_prefix("shared_experts", prefix),
                )
            else:
                self.shared_experts = YoutuVLMLP(
                    config,
                    intermediate_size=shared_intermediate,
                    quant_config=quant_config,
                    prefix=add_prefix("shared_experts", prefix),
                    reduce_results=False,
                )
        else:
            self.shared_experts = None

        # The shared expert and the routed experts read independent inputs and
        # are only combined at the very end, so the shared branch can run on a
        # side stream underneath ``fused_moe_kernel`` instead of in front of it.
        # Streams must be leased here: creating one is a driver call that cannot
        # happen inside cuda-graph capture.  A dedicated name keeps this clear of
        # the "alt"/"utu_gate" pair the attention blocks fork onto.
        self._shared_alt_stream = (
            get_stream("utu_shared_expert")
            if self.shared_experts is not None
            and _SHARED_EXPERT_OVERLAP
            and torch.cuda.is_available()
            else None
        )
        # Past this token count the routed GEMMs already fill the SMs, so the
        # fork buys nothing and the two stream syncs are pure cost.  Same
        # threshold the KDA projection overlap uses.
        self._shared_bs_limit = (
            (128 if is_blackwell_supported() else 64)
            if self._shared_alt_stream is not None
            else 0
        )

        # Track ownership of the dispatcher's skip-mapping flag.
        self._remap_dispatcher = None

    def _local_expert_range(self) -> Optional[Tuple[int, int]]:
        """Take over only the standard dispatcher's affine local-id mapping."""
        dispatcher = getattr(self.experts, "dispatcher", None)
        previous = self._remap_dispatcher
        if previous is not None:
            # Re-evaluate after sharding/backend changes, releasing only flags
            # this adapter owns. Any lazily built table may now be stale.
            previous.skip_local_expert_mapping = False
            previous.local_expert_mapping = None
            self._remap_dispatcher = None
        if (
            not _FUSED_EXPERT_REMAP
            or not isinstance(dispatcher, StandardDispatcher)
            or dispatcher.skip_local_expert_mapping
            or dispatcher.moe_ep_size <= 1
            or getattr(dispatcher, "use_aiter_moe_runner", False)
            or dispatcher.num_local_shared_experts
            or not type(self.experts.quant_method).__name__.startswith("Unquantized")
            or _sgl_standard_dispatch._MASK_DP_PAD_MOE
        ):
            return None
        count = dispatcher.num_local_routed_experts
        dispatcher.skip_local_expert_mapping = True
        self._remap_dispatcher = dispatcher
        return dispatcher.moe_ep_rank * count, count

    def _route(
        self, hidden_states: torch.Tensor, router_logits: torch.Tensor, modality_id: Optional[torch.Tensor]
    ) -> StandardTopKOutput:
        """QB global top-k or MG-aligned sigmoid grouped top-k."""
        local_expert_range = self._local_expert_range()
        if self.use_quantile_balancing:
            if self.gate.qb_beta is None:
                raise RuntimeError("QB routing requires qb_beta.")
            topk_weights, topk_ids = qb_route(
                router_logits,
                self.gate.qb_beta,
                modality_id,
                top_k=self.top_k,
                renormalize=self.norm_topk_prob,
                scaling=(
                    self.routed_scaling_factor
                    if self.experts.should_fuse_routed_scaling_factor_in_topk
                    else None
                ),
                local_expert_range=local_expert_range,
            )
            return StandardTopKOutput(topk_weights, topk_ids, router_logits)

        scores = router_logits.sigmoid()
        if self.gate.e_score_correction_bias is None:
            scores_for_choice = scores
        else:
            correction_bias = self.gate.correction_bias_for(
                router_logits, modality_id
            )
            if correction_bias.dim() == 1:
                scores_for_choice = scores + correction_bias.unsqueeze(0)
            else:
                scores_for_choice = scores + correction_bias

        num_tokens, num_experts = scores_for_choice.shape
        group_scores = (
            scores_for_choice.view(num_tokens, self.n_group, num_experts // self.n_group)
            .topk(self.top_k // self.topk_group, dim=-1)[0]
            .sum(dim=-1)
        )
        group_idx = torch.topk(group_scores, k=self.topk_group, dim=-1, sorted=False)[1]
        group_mask = torch.zeros_like(group_scores)
        group_mask.scatter_(1, group_idx, 1)
        score_mask = (
            group_mask.unsqueeze(-1)
            .expand(num_tokens, self.n_group, num_experts // self.n_group)
            .reshape(num_tokens, num_experts)
        )
        masked_scores = scores_for_choice.masked_fill(~score_mask.bool(), float("-inf"))
        topk_ids = torch.topk(masked_scores, k=self.top_k, dim=-1, sorted=False)[1]
        topk_weights = scores.gather(1, topk_ids)
        if self.norm_topk_prob:
            topk_weights = topk_weights / (topk_weights.sum(dim=-1, keepdim=True) + 1e-20)
        if self.experts.should_fuse_routed_scaling_factor_in_topk:
            topk_weights = topk_weights * self.routed_scaling_factor
        topk_ids = topk_ids.to(torch.int32)
        if local_expert_range is not None:
            topk_ids = to_local_expert_ids(topk_ids, local_expert_range)
        return StandardTopKOutput(
            topk_weights.to(torch.float32), topk_ids, router_logits
        )

    def _shared_expert_forward(
        self, hidden_states: torch.Tensor, modality_id: Optional[torch.Tensor]
    ) -> torch.Tensor:
        """Run the shared branch with its own token modality mask."""
        if isinstance(self.shared_experts, YoutuVLMultiModalSharedExperts):
            return self.shared_experts(hidden_states, modality_id)
        return self.shared_experts(hidden_states)

    def forward(
        self, hidden_states: torch.Tensor, modality_id: Optional[torch.Tensor] = None,
        shared_modality_id: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        hidden_states = hidden_states.view(-1, self.hidden_size)
        router_logits = self.gate(hidden_states)
        topk_output = self._route(hidden_states, router_logits, modality_id)

        # The shared and routed branches read independent inputs and only meet
        # at the final add, so under capture the shared branch goes on a side
        # stream to run underneath fused_moe_kernel.  Everywhere else (eager
        # prefill, uncaptured decode) it stays in front of the routed path,
        # where FusedMoE's inplace aliasing requires it to read hidden_states
        # before the routed experts overwrite them.
        overlap_shared = (
            self.shared_experts is not None
            and self._shared_alt_stream is not None
            and get_is_capture_mode()
            and 0 < hidden_states.shape[0] <= self._shared_bs_limit
        )

        shared_out = None
        if self.shared_experts is not None:
            if overlap_shared:
                alt = self._shared_alt_stream
                alt.wait_stream(torch.cuda.current_stream())
                with torch.cuda.stream(alt):
                    shared_out = self._shared_expert_forward(hidden_states, shared_modality_id)
            else:
                shared_out = self._shared_expert_forward(hidden_states, shared_modality_id)

        expert_input = hidden_states
        if self.fc1_latent_proj is not None:
            expert_input = self.fc1_latent_proj(hidden_states)

        # While the shared branch is in flight the routed path must stop
        # aliasing its output onto hidden_states -- with inplace set,
        # ``fused_moe.py`` does a bare ``out_hidden_states = hidden_states``,
        # which would have fused_moe_kernel writing the very buffer the side
        # stream is reading.  The runner holds this config by reference, so
        # flipping it here reaches the kernel; restoring it afterwards keeps the
        # eager prefill path on the aliasing version it was measured with.
        prev_inplace = self.experts.moe_runner_config.inplace
        if overlap_shared:
            self.experts.moe_runner_config.inplace = False
        try:
            final_hidden_states = self.experts(expert_input, topk_output)
        finally:
            self.experts.moe_runner_config.inplace = prev_inplace
        if self.latent_rmsnorm is not None:
            final_hidden_states = self.latent_rmsnorm(final_hidden_states)
        if self.fc2_latent_proj is not None:
            final_hidden_states = self.fc2_latent_proj(final_hidden_states)

        if shared_out is not None:
            if overlap_shared:
                torch.cuda.current_stream().wait_stream(self._shared_alt_stream)
            final_hidden_states = final_hidden_states + shared_out

        # Newer SGLang releases derive reduce-scatter/all-reduce-fusion flags
        # from ForwardFlags and expose only ``is_tp_path``.  Omitting the two
        # optional False values also preserves the behavior of older releases.
        if self.ep_size > 1 and not should_skip_post_experts_all_reduce(
            is_tp_path=False,
        ):
            final_hidden_states = moe_expert_parallel_all_reduce(final_hidden_states)
        if self.tp_size > 1 and not should_skip_post_experts_all_reduce(
            is_tp_path=True,
        ):
            final_hidden_states = moe_tensor_model_parallel_all_reduce(
                final_hidden_states
            )
        return final_hidden_states


def _is_kda_layer(config, layer_id: int) -> bool:
    """Whether ``layer_id`` follows the Megatron KDA branch.

    The converted HF config keeps the training-side binary pattern: ``1`` is
    KDA and ``0`` is full MLA.  Keep this predicate local so the SGLang adapter
    remains usable with a remote-code config that has not imported the HF
    modeling module.
    """

    pattern = getattr(config, "linear_attention_pattern", None)
    if pattern is None:
        pattern = [1, 1, 1, 0] * (config.num_hidden_layers // 4)
    if len(pattern) != config.num_hidden_layers:
        raise ValueError(
            "linear_attention_pattern must have one item per decoder layer; "
            f"got {len(pattern)} for {config.num_hidden_layers} layers."
        )
    return (
        getattr(config, "experimental_attention_variant", None) == "kda"
        and int(pattern[layer_id]) == 1
    )


class YoutuVLCausalConv1dWeights(nn.Module):
    """Depth-wise causal-conv parameter container with HF-compatible naming.

    ``KDAAttnBackend`` owns the causal-conv execution and receives this
    parameter as a `[channels, kernel]` view.  Keeping the registered
    parameter at `conv1d.weight` in native Conv1d layout `[channels, 1, kernel]`
    makes the converted HF checkpoint load without any name or shape rewrite.

    ``dtype=None`` falls back to the ambient default (BF16 during model
    construction).  The fused decode kernel requires FP32 conv weights --
    ``KDAAttnBackend.covered`` rejects any other dtype -- which is why Kimi
    declares its ``qkv_conv1d`` with ``params_dtype=torch.float32``.
    """

    def __init__(
        self, channels: int, kernel_size: int, dtype: Optional[torch.dtype] = None
    ):
        super().__init__()
        self.weight = nn.Parameter(torch.empty(channels, 1, kernel_size, dtype=dtype))


class YoutuVLMLARotaryEmbedding(nn.Module):
    """Megatron MLA RoPE ordering on top of SGLang MRoPE.

    Megatron's MLA path first changes `[d0, d1, d2, d3, ...]` into
    `[d0, d2, ..., d1, d3, ...]`, then applies Neox half-rotation.  SGLang's
    generic MLA assumes its input is already in that layout, while UTU's
    separate ``q_b_proj`` / ``kv_a_proj`` outputs are not.  Kimi K3 does not
    need this conversion; UTU does.
    """

    def __init__(self, rotary_emb: nn.Module):
        super().__init__()
        self.base_rotary_emb = rotary_emb

    @property
    def cos_sin_cache(self):
        return self.base_rotary_emb.cos_sin_cache

    @property
    def is_neox_style(self):
        return self.base_rotary_emb.is_neox_style

    def forward(
        self, positions: torch.Tensor, query: torch.Tensor, key: torch.Tensor, **kwargs
    ):
        # DeepseekMLAForwardMixin supplies MLA RoPE tensors as [T, H, D].
        # SGLang's MRotaryEmbedding native path accepts that shape, but its
        # CUDA Triton path (selected for 2-D MRoPE positions) intentionally
        # operates on flattened [T, H * D] Q/K tensors.  Flatten before
        # dispatching to the base embedding and restore the MLA shapes
        # afterwards.  This is required for both MQA K ([T, 1, D]) and the
        # TP-local Q heads; otherwise triton_mrope_fused fails to unpack q.shape.
        query_shape = query.shape
        key_shape = key.shape
        pair = (
            deinterleave_rope_pair(query, key) if _FUSED_ROPE_REORDER else None
        )
        if pair is not None:
            query, key = pair
        else:
            query = torch.cat((query[..., 0::2], query[..., 1::2]), dim=-1)
            key = torch.cat((key[..., 0::2], key[..., 1::2]), dim=-1)
        if query.ndim > 2:
            query = query.flatten(start_dim=1)
        if key.ndim > 2:
            key = key.flatten(start_dim=1)
        query, key = self.base_rotary_emb(positions, query, key, **kwargs)
        return query.reshape(query_shape), key.reshape(key_shape)


class YoutuVLKDAAttention(nn.Module):
    """Kimi-style KDA layer backed by SGLang's radix linear-attention cache.

    This is the same KDA recurrence/cache path used by SGLang's Kimi K3.  UTU
    differs in checkpoint layout only: q/k/v are already fused as
    ``qkv_proj``. The output gate follows ``config.use_full_rank_gate``:
    full-rank ``g_proj`` or FLA's low-rank ``g_a_proj`` / ``g_b_proj``.
    """

    def __init__(
        self,
        config,
        layer_id: int,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.layer_id = layer_id
        self.hidden_size = config.hidden_size
        self.num_heads = config.num_attention_heads
        self.head_dim = config.head_dim
        self.projection_size = self.num_heads * self.head_dim
        self.attn_tp_size = get_parallel().attn_tp_size
        self.attn_tp_rank = get_parallel().attn_tp_rank
        if self.num_heads % self.attn_tp_size:
            raise ValueError(
                f"KDA num_attention_heads={self.num_heads} must be divisible by "
                f"attn_tp_size={self.attn_tp_size}."
            )
        self.local_num_heads = self.num_heads // self.attn_tp_size
        self.use_full_rank_gate = getattr(config, "use_full_rank_gate", True)

        self.qkv_proj = QKVParallelLinear(
            self.hidden_size,
            self.head_dim,
            self.num_heads,
            self.num_heads,
            bias=False,
            quant_config=quant_config,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            v_head_size=self.head_dim,
            prefix=add_prefix("qkv_proj", prefix),
        )
        self.f_a_proj = ReplicatedLinear(
            self.hidden_size,
            self.head_dim,
            bias=False,
            quant_config=quant_config,
            prefix=add_prefix("f_a_proj", prefix),
        )
        self.f_b_proj = ColumnParallelLinear(
            self.head_dim,
            self.projection_size,
            bias=False,
            quant_config=quant_config,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("f_b_proj", prefix),
        )
        self.b_proj = ColumnParallelLinear(
            self.hidden_size,
            self.num_heads,
            bias=False,
            quant_config=quant_config,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("b_proj", prefix),
        )
        if self.use_full_rank_gate:
            self.g_proj = ColumnParallelLinear(
                self.hidden_size,
                self.projection_size,
                bias=False,
                quant_config=quant_config,
                tp_rank=self.attn_tp_rank,
                tp_size=self.attn_tp_size,
                prefix=add_prefix("g_proj", prefix),
            )
        else:
            # Match FLA KimiDeltaAttention:
            #   hidden -> head_dim -> num_heads * head_dim (+ bias).
            # The first projection is replicated and the second is sharded by
            # output heads, exactly as the Megatron training implementation.
            self.g_a_proj = ReplicatedLinear(
                self.hidden_size,
                self.head_dim,
                bias=False,
                quant_config=quant_config,
                prefix=add_prefix("g_a_proj", prefix),
            )
            self.g_b_proj = ColumnParallelLinear(
                self.head_dim,
                self.projection_size,
                bias=True,
                quant_config=quant_config,
                tp_rank=self.attn_tp_rank,
                tp_size=self.attn_tp_size,
                prefix=add_prefix("g_b_proj", prefix),
            )

        self.conv1d = YoutuVLCausalConv1dWeights(
            3 * self.projection_size // self.attn_tp_size,
            config.short_conv_kernel_size,
            dtype=torch.float32 if _FUSED_KDA_DECODE else None,
        )
        # Conv channels are ordered [all Q, all K, all V].  They must be
        # sharded independently per block, exactly like QKVParallelLinear;
        # slicing the flat concatenation would incorrectly give rank 0 only Q
        # channels (and rank 1 a Q/K boundary).
        local_projection_size = self.projection_size // self.attn_tp_size

        def _load_qkv_conv_weight(param: torch.Tensor, loaded_weight: torch.Tensor):
            if loaded_weight.shape == param.shape:
                param.data.copy_(loaded_weight)
                return
            expected = 3 * self.projection_size
            if loaded_weight.shape[0] != expected:
                raise ValueError(
                    "Unexpected KDA conv1d weight shape: expected first dimension "
                    f"{expected} or local {param.shape[0]}, got "
                    f"{tuple(loaded_weight.shape)}."
                )
            start = self.attn_tp_rank * local_projection_size
            shards = [
                loaded_weight.narrow(0, block * self.projection_size + start, local_projection_size)
                for block in range(3)
            ]
            param.data.copy_(torch.cat(shards, dim=0))

        set_weight_attrs(self.conv1d.weight, {"weight_loader": _load_qkv_conv_weight})
        self.A_log = nn.Parameter(torch.empty(self.local_num_heads, dtype=torch.float32))
        self.dt_bias = nn.Parameter(
            torch.empty(
                self.projection_size // self.attn_tp_size,
                dtype=torch.float32,
            )
        )
        set_weight_attrs(self.A_log, {"weight_loader": sharded_weight_loader(0)})
        set_weight_attrs(self.dt_bias, {"weight_loader": sharded_weight_loader(0)})

        self.out_norm = FusedRMSNormGated(
            self.head_dim, eps=config.rms_norm_eps, activation="sigmoid"
        )
        self.out_proj = RowParallelLinear(
            self.projection_size,
            self.hidden_size,
            bias=False,
            quant_config=quant_config,
            reduce_results=False,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("out_proj", prefix),
        )
        self.attn = RadixLinearAttention(
            layer_id=layer_id,
            num_q_heads=self.local_num_heads,
            num_k_heads=self.local_num_heads,
            num_v_heads=self.local_num_heads,
            head_q_dim=self.head_dim,
            head_k_dim=self.head_dim,
            head_v_dim=self.head_dim,
            conv_weights=self.conv1d.weight.squeeze(1),
            A_log=self.A_log,
            dt_bias=self.dt_bias,
        )
        self.attn.lower_bound = getattr(config, "kda_gate_lower_bound", None)
        self._kda_fused_decode_ready = False

        # Merged projections, built by fuse_projections() after weight loading.
        self._qkvg_w: Optional[torch.Tensor] = None
        self._qkvg_sizes: List[int] = []
        self._bfa_w: Optional[torch.Tensor] = None
        self._bfa_fa_size = 0
        self._bfa_b_size = 0
        # Kimi K3 runs the skinny [f_a|b] + f_b chain on a side stream so it
        # overlaps the wide [q,k,v,g] GEMM; both read only hidden_states.  Must
        # be a different stream from the MLA layernorm one, since an MLA layer
        # forks both within a single forward.
        self._bfa_alt_stream = (
            get_stream("utu_gate") if torch.cuda.is_available() else None
        )
        # Above this token count the GEMMs already fill the SMs and the overlap
        # only adds sync overhead.
        self._bfa_bs_limit = (
            (128 if is_blackwell_supported() else 64)
            if self._bfa_alt_stream is not None
            else 0
        )

    def fuse_projections(self) -> None:
        """Merge loaded local QKV/gate and replicated f_a/local beta weights."""
        if self._qkvg_w is None and self.use_full_rank_gate:
            # The low-rank gate keeps the split path: g_b_proj carries a bias
            # and consumes g_a's output rather than hidden_states.
            mods = [self.qkv_proj, self.g_proj]
            if _mergeable(mods):
                self._qkvg_w, self._qkvg_sizes = _merge_weights_as_views(mods)

        if self._bfa_w is None:
            mods = [self.f_a_proj, self.b_proj]
            if _mergeable(mods):
                self._bfa_w, sizes = _merge_weights_as_views(mods, pad_rows_to=8)
                self._bfa_fa_size, self._bfa_b_size = sizes

    def prepare_fused_decode(self) -> None:
        """Prepare FP32 static inputs; backend coverage checks choose fused execution."""
        if not _FUSED_KDA_DECODE:
            return
        layer = self.attn
        w = layer.conv_weights
        seg = self.local_num_heads * self.head_dim
        if (
            w is None
            or w.ndim != 2
            or tuple(w.shape) != (3 * seg, 4)
            or w.dtype != torch.float32
            or layer.A_log is None
            or layer.A_log.numel() != self.local_num_heads
            or layer.A_log.dtype != torch.float32
            or layer.dt_bias is None
            or tuple(layer.dt_bias.shape) != (seg,)
            or layer.dt_bias.dtype != torch.float32
        ):
            def _desc(t):
                return None if t is None else f"{tuple(t.shape)}/{t.dtype}"

            print(
                "[UTU] fused KDA decode disabled for unexpected static layout: "
                f"conv={_desc(w)} (want {(3 * seg, 4)}/torch.float32), "
                f"A_log={_desc(layer.A_log)} (want {(self.local_num_heads,)}/torch.float32), "
                f"dt_bias={_desc(layer.dt_bias)} (want {(seg,)}/torch.float32)",
                flush=True,
            )
            return

        wt = w.t().contiguous()
        bias = getattr(layer, "bias", None)
        conv_bias = (
            bias.float().contiguous()
            if bias is not None
            else torch.zeros(3 * seg, dtype=torch.float32, device=w.device)
        )
        layer._k3_fused_decode_args = (
            wt[:, :seg].contiguous(),
            wt[:, seg : 2 * seg].contiguous(),
            wt[:, 2 * seg :].contiguous(),
            conv_bias,
            layer.A_log.detach().reshape(-1),
            self.out_norm.weight.data.float().contiguous(),
            float(self.out_norm.eps),
        )
        self._kda_fused_decode_ready = True

    def _project_qkv_gate(self, hidden_states: torch.Tensor):
        if self._qkvg_w is not None:
            fused = F.linear(hidden_states, self._qkvg_w)
            mixed_qkv, output_gate = torch.split(fused, self._qkvg_sizes, dim=-1)
            return mixed_qkv, output_gate
        mixed_qkv, _ = self.qkv_proj(hidden_states)
        if self.use_full_rank_gate:
            output_gate, _ = self.g_proj(hidden_states)
        else:
            output_gate, _ = self.g_b_proj(self.g_a_proj(hidden_states)[0])
        return mixed_qkv, output_gate

    def _project_beta_forget(self, hidden_states: torch.Tensor):
        if self._bfa_w is not None:
            n_fa, n_b = self._bfa_fa_size, self._bfa_b_size
            bfa = F.linear(hidden_states, self._bfa_w)
            forget_gate, _ = self.f_b_proj(bfa[..., :n_fa])
            return bfa[..., n_fa : n_fa + n_b], forget_gate
        beta, _ = self.b_proj(hidden_states)
        forget_gate, _ = self.f_b_proj(self.f_a_proj(hidden_states)[0])
        return beta, forget_gate

    def _project_inputs(self, hidden_states: torch.Tensor):
        """``[q,k,v]``, beta, forget gate and output gate for one token batch."""
        if (
            self._bfa_w is not None
            and self._bfa_alt_stream is not None
            and get_is_capture_mode()
            and 0 < hidden_states.shape[0] <= self._bfa_bs_limit
        ):
            alt = self._bfa_alt_stream
            current = torch.cuda.current_stream()
            alt.wait_stream(current)
            with torch.cuda.stream(alt):
                beta, forget_gate = self._project_beta_forget(hidden_states)
            mixed_qkv, output_gate = self._project_qkv_gate(hidden_states)
            current.wait_stream(alt)
            return mixed_qkv, beta, forget_gate, output_gate

        mixed_qkv, output_gate = self._project_qkv_gate(hidden_states)
        beta, forget_gate = self._project_beta_forget(hidden_states)
        return mixed_qkv, beta, forget_gate, output_gate

    def forward(
        self,
        positions: torch.Tensor,
        hidden_states: torch.Tensor,
        forward_batch: ForwardBatch,
        zero_allocator=None,
    ) -> torch.Tensor:
        del positions, zero_allocator
        mixed_qkv, beta, forget_gate, output_gate = self._project_inputs(hidden_states)

        if not forward_batch.forward_mode.is_decode():
            forget_gate = forget_gate.unflatten(-1, (-1, self.head_dim))
            # KDA chunk prefill expects a pre-activated beta; decode and verify
            # apply sigmoid inside their recurrent kernels (matching Kimi K3).
            if not forward_batch.forward_mode.is_target_verify():
                beta = beta.float().sigmoid()
            forget_gate = forget_gate.unsqueeze(0)
        beta = beta.unsqueeze(0)

        fused_onorm = self._kda_fused_decode_ready and (
            forward_batch.forward_mode.is_decode()
            or forward_batch.forward_mode.is_target_verify()
        )
        if fused_onorm:
            self.attn._k3_onorm_gate = output_gate
            self.attn._k3_onorm_consumed = False

        try:
            core_attn_out = self.attn(
                forward_batch,
                mixed_qkv=mixed_qkv,
                a=forget_gate,
                b=beta,
            )
        finally:
            if fused_onorm:
                self.attn._k3_onorm_gate = None
        if fused_onorm:
            fused_onorm = self.attn._k3_onorm_consumed
        if not fused_onorm:
            output_gate = output_gate.unflatten(-1, (-1, self.head_dim))
            core_attn_out = self.out_norm(core_attn_out, output_gate)
        core_attn_out = core_attn_out.squeeze(0).flatten(-2)
        output, _ = self.out_proj(core_attn_out)
        if self.attn_tp_size > 1:
            output = get_parallel().attn_tp_group.all_reduce(output)
        return output


class YoutuVLMLAAttention(DeepseekV2AttentionMLA):
    """UTU MLA with separate q/kv latent projections and a *head-wise* gate.

    SGLang's Kimi K3 wrapper gates the full `[heads, v_dim]` output
    channel-wise.  UTU's HF/Megatron implementation instead predicts one gate
    per head, hence `g_proj: hidden -> num_heads` and a broadcast over
    `v_head_dim` before ``o_proj``.
    """

    def __init__(
        self,
        config,
        layer_id: int,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        nn.Module.__init__(self)
        self.layer_id = layer_id
        self.hidden_size = config.hidden_size
        self.qk_nope_head_dim = config.qk_nope_head_dim
        self.qk_rope_head_dim = config.qk_rope_head_dim
        self.qk_head_dim = self.qk_nope_head_dim + self.qk_rope_head_dim
        self.v_head_dim = config.v_head_dim
        self.q_lora_rank = config.q_lora_rank
        self.kv_lora_rank = config.kv_lora_rank
        self.quant_config = quant_config
        self.is_nextn = False
        self.num_heads = config.num_attention_heads
        self.attn_tp_rank = get_parallel().attn_tp_rank
        self.attn_tp_size = get_parallel().attn_tp_size
        if self.num_heads % self.attn_tp_size:
            raise ValueError(
                f"MLA num_attention_heads={self.num_heads} must be divisible by "
                f"attn_tp_size={self.attn_tp_size}."
            )
        self.num_local_heads = self.num_heads // self.attn_tp_size
        self.scaling = self.qk_head_dim**-0.5
        self.rope_theta = config.rope_theta
        self.max_position_embeddings = config.max_position_embeddings
        self.kv_cache_dtype = get_model().kv_cache_dtype

        # The standard DeepSeek MLA implementation fuses q_a and kv_a into one
        # replicated GEMM.  UTU's checkpoint stores them separately, so retain
        # separate modules while reusing DeepseekMLAForwardMixin below.
        self.q_a_proj = ReplicatedLinear(
            self.hidden_size,
            self.q_lora_rank,
            bias=False,
            quant_config=quant_config,
            prefix=add_prefix("q_a_proj", prefix),
        )
        self.q_a_layernorm = RMSNorm(self.q_lora_rank, eps=config.rms_norm_eps)
        self.q_b_proj = ColumnParallelLinear(
            self.q_lora_rank,
            self.num_heads * self.qk_head_dim,
            bias=False,
            quant_config=quant_config,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("q_b_proj", prefix),
        )
        self.kv_a_proj_with_mqa = ReplicatedLinear(
            self.hidden_size,
            self.kv_lora_rank + self.qk_rope_head_dim,
            bias=False,
            quant_config=quant_config,
            prefix=add_prefix("kv_a_proj_with_mqa", prefix),
        )
        self.kv_a_layernorm = RMSNorm(self.kv_lora_rank, eps=config.rms_norm_eps)
        self.kv_b_proj = ColumnParallelLinear(
            self.kv_lora_rank,
            self.num_heads * (self.qk_nope_head_dim + self.v_head_dim),
            bias=False,
            quant_config=quant_config,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("kv_b_proj", prefix),
        )
        self.o_proj = RowParallelLinear(
            self.num_heads * self.v_head_dim,
            self.hidden_size,
            bias=False,
            quant_config=quant_config,
            reduce_results=False,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("o_proj", prefix),
        )
        self.g_proj = ColumnParallelLinear(
            self.hidden_size,
            self.num_heads,
            bias=False,
            quant_config=quant_config,
            tp_rank=self.attn_tp_rank,
            tp_size=self.attn_tp_size,
            prefix=add_prefix("g_proj", prefix),
        )

        rope_scaling = _sglang_rope_scaling(config)
        self.rotary_emb = YoutuVLMLARotaryEmbedding(
            get_rope(
                self.qk_rope_head_dim,
                rotary_dim=self.qk_rope_head_dim,
                max_position=self.max_position_embeddings,
                base=self.rope_theta,
                is_neox_style=True,
                rope_scaling=rope_scaling,
            )
        )
        self.attn_mqa = RadixAttention(
            self.num_local_heads,
            self.kv_lora_rank + self.qk_rope_head_dim,
            self.scaling,
            num_kv_heads=1,
            layer_id=layer_id,
            v_head_dim=self.kv_lora_rank,
            quant_config=quant_config,
            prefix=add_prefix("attn_mqa", prefix),
        )
        # Decode context parallelism shards the KV *sequence* across the DCP
        # sub-group, then all-gathers Q so each rank evaluates every head over
        # its own shard -- so this instance is declared with the gathered head
        # count, not the local one.  The absorbed forward inherited from
        # DeepseekMLAForwardMixin looks this attribute up by name whenever
        # is_dcp_mla_decode_phase() holds; without it, a DCP run boots cleanly
        # and then dies on the first decode.
        if get_parallel().dcp_enabled:
            self.attn_mqa_for_dcp_decode = RadixAttention(
                self.num_local_heads * get_parallel().attn_dcp_size,
                self.kv_lora_rank + self.qk_rope_head_dim,
                self.scaling,
                num_kv_heads=1,
                layer_id=layer_id,
                v_head_dim=self.kv_lora_rank,
                quant_config=quant_config,
                prefix=add_prefix("attn_mqa", prefix),
            )
        self.attn_mha = RadixAttention(
            self.num_local_heads,
            self.qk_head_dim,
            self.scaling,
            num_kv_heads=self.num_local_heads,
            layer_id=layer_id,
            v_head_dim=self.v_head_dim,
            quant_config=quant_config,
            prefix=add_prefix("attn_mha", prefix),
        )
        self.attn_mha.kv_b_proj = None
        self.w_kc = None
        self.w_vc = None
        self.w_kc_qrep = None
        self.q_b_proj_qrep_weight = None
        self.w_scale = 1.0
        self.w_scale_k = None
        self.w_scale_v = None
        self.use_deep_gemm_bmm = False
        self.current_attention_backend = None
        # Lets forward_mla overlap the q_a and kv_a layernorms during capture.
        # The other alt-stream branches there all require ``use_dsa``, which
        # this model never enables, so this is the only effect.
        self.alt_stream = get_stream("alt") if torch.cuda.is_available() else None
        # Kimi K3 keeps the output-gate GEMM on a *second* stream, because a
        # single MLA forward forks both this and the layernorm overlap above.
        self._gate_alt_stream = (
            get_stream("utu_gate") if torch.cuda.is_available() else None
        )
        self._gate_bs_limit = (
            (128 if is_blackwell_supported() else 64)
            if self._gate_alt_stream is not None
            else 0
        )
        self.use_dsa = False
        self.dsa_enable_prefill_cp = False
        self.mla_enable_prefill_cp = False
        self.skip_topk = None
        self.next_skip_topk = None
        self.use_deepseek_yarn_rope = False
        self.has_fused_proj = False
        self.is_packed_weight = False
        self._use_min_latency_fused_a_gemm = False
        self._use_min_latency_q_b_gemm = False
        self._q_b_proj_verified_shape = False
        self.fused_a_gemm_backend = "auto"

        # DeepseekV2AttentionMLA's dispatcher/mixins use these initialization
        # hooks but do not require the fused q_a+kv_a module.
        self.init_mha_forward()
        self.init_mla_forward()
        self.init_mla_fused_rope_rocm_forward()
        self.init_mla_fused_rope_cpu_forward()
        # ROCm's fused MLA path requires the DeepSeek-specific
        # ``fused_qkv_a_proj_with_mqa`` layout.  UTU deliberately keeps
        # separate q_a/kv_a checkpoint tensors, so always use the generic
        # absorbed MLA route there.
        self.rocm_fused_decode_mla = False
        self.fused_a_weight = None
        self._install_head_wise_output_gate()

    def fuse_a_projections(self) -> None:
        """Share storage between separate checkpoint projections and their fused GEMM."""
        if self.fused_a_weight is not None:
            return
        mods = [self.q_a_proj, self.kv_a_proj_with_mqa]
        if _mergeable(mods):
            self.fused_a_weight, _ = _merge_weights_as_views(mods)

    def prepare_qkv_latent(
        self, hidden_states: torch.Tensor, forward_batch: ForwardBatch
    ) -> torch.Tensor:
        del forward_batch
        if self.fused_a_weight is not None:
            return F.linear(hidden_states, self.fused_a_weight)
        q, _ = self.q_a_proj(hidden_states)
        kv, _ = self.kv_a_proj_with_mqa(hidden_states)
        return torch.cat([q, kv], dim=-1)

    # UTU needs the Megatron MLA even/odd reorder before MRoPE.  Do not let
    # backend-specific fused paths bypass ``YoutuVLMLARotaryEmbedding`` and
    # apply ordinary DeepSeek MLA RoPE to the un-reordered tensors.
    def _fuse_rope_for_trtllm_mla(self, forward_batch: ForwardBatch) -> bool:
        del forward_batch
        return False

    def _skip_rope_for_dsa_tilelang_fused(self) -> bool:
        return False

    def _skip_rope_for_aiter_fused_mla(self) -> bool:
        return False

    def _install_head_wise_output_gate(self) -> None:
        original_o_proj_forward = self.o_proj.forward

        def _gated_o_proj_forward(x, *args, **kwargs):
            gate_hidden_states = self._gate_hidden_states
            self._gate_hidden_states = None
            precomputed = self._gate_precomputed
            self._gate_precomputed = None
            if precomputed is not None:
                # wait_stream rather than an explicit event, so the breakable
                # cuda-graph runner can track the join across segments.
                torch.cuda.current_stream().wait_stream(precomputed[1])
            if gate_hidden_states is not None and not isinstance(x, tuple):
                gate = (
                    precomputed[0]
                    if precomputed is not None
                    else self.g_proj(gate_hidden_states)[0]
                )
                fused = (
                    sigmoid_gate_mul(
                        x, gate, self.num_local_heads, self.v_head_dim
                    )
                    if _FUSED_OUTPUT_GATE
                    else None
                )
                if fused is not None:
                    x = fused
                else:
                    gate = torch.sigmoid(gate.float()).to(dtype=x.dtype)
                    x = x.view(-1, self.num_local_heads, self.v_head_dim)
                    x = (x * gate.unsqueeze(-1)).flatten(-2)
            output, bias = original_o_proj_forward(x, *args, **kwargs)
            if self.attn_tp_size > 1:
                output = get_parallel().attn_tp_group.all_reduce(output)
            return output, bias

        self._gate_hidden_states = None
        # (gate, producing stream), or None when the lazy path computes it in
        # the wrapper instead.
        self._gate_precomputed = None
        self.o_proj.forward = _gated_o_proj_forward

    def _precompute_output_gate(self, hidden_states: torch.Tensor) -> None:
        """Compute the MLA output gate on a side stream during full graph capture."""
        self._gate_precomputed = None
        if (
            self._gate_alt_stream is not None
            and get_is_capture_mode()
            # Under breakable capture the attention-core break would put the
            # record and the wait in different graph segments.
            and not is_in_breakable_cuda_graph()
            and 0 < hidden_states.shape[0] <= self._gate_bs_limit
        ):
            alt = self._gate_alt_stream
            alt.wait_stream(torch.cuda.current_stream())
            with torch.cuda.stream(alt):
                gate, _ = self.g_proj(hidden_states)
            self._gate_precomputed = (gate, alt)

    def forward(
        self,
        positions: torch.Tensor,
        hidden_states: torch.Tensor,
        forward_batch: ForwardBatch,
        zero_allocator=None,
        **kwargs,
    ) -> torch.Tensor:
        self._gate_hidden_states = hidden_states
        self._precompute_output_gate(hidden_states)
        try:
            return super().forward(
                positions,
                hidden_states,
                forward_batch,
                zero_allocator,
                **kwargs,
            )
        finally:
            # Empty-token/exception paths may bypass o_proj.  Join before
            # dropping the reference, or the allocator could recycle the gate
            # while the side stream is still writing it.
            self._gate_hidden_states = None
            stale = self._gate_precomputed
            self._gate_precomputed = None
            if stale is not None:
                torch.cuda.current_stream().wait_stream(stale[1])


class YoutuVLAttention(nn.Module):
    """GQA + QKNorm + MRoPE（interleaved, half-RoPE）。参考 qwen3_moe.Qwen3MoeAttention 简化。"""

    def __init__(
        self,
        config,
        layer_id: int,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.layer_id = layer_id
        self.hidden_size = config.hidden_size
        self.total_num_heads = config.num_attention_heads
        self.total_num_kv_heads = config.num_key_value_heads
        self.head_dim = getattr(
            config, "head_dim", config.hidden_size // config.num_attention_heads
        )
        self.scaling = self.head_dim**-0.5

        attn_tp_size = get_parallel().attn_tp_size
        assert self.total_num_heads % attn_tp_size == 0
        self.num_heads = self.total_num_heads // attn_tp_size
        self.tp_size = attn_tp_size
        if self.total_num_kv_heads >= attn_tp_size:
            assert self.total_num_kv_heads % attn_tp_size == 0
        else:
            assert attn_tp_size % self.total_num_kv_heads == 0
        self.num_kv_heads = max(1, self.total_num_kv_heads // attn_tp_size)
        self.q_size = self.num_heads * self.head_dim
        self.kv_size = self.num_kv_heads * self.head_dim

        self.qkv_proj = QKVParallelLinear(
            self.hidden_size,
            self.head_dim,
            self.total_num_heads,
            self.total_num_kv_heads,
            bias=getattr(config, "attention_bias", False),
            quant_config=quant_config,
            prefix=add_prefix("qkv_proj", prefix),
        )
        self.o_proj = RowParallelLinear(
            self.total_num_heads * self.head_dim,
            self.hidden_size,
            bias=getattr(config, "attention_bias", False),
            quant_config=quant_config,
            reduce_results=False,
            prefix=add_prefix("o_proj", prefix),
        )

        self.q_norm = RMSNorm(self.head_dim, eps=config.rms_norm_eps)
        self.k_norm = RMSNorm(self.head_dim, eps=config.rms_norm_eps)

        # MRoPE：mrope_section 触发 MRoPE；yarn 时走 YaRNScalingMRotaryEmbedding。
        # partial_rotary_factor=0.5 使 rotary_dim = head_dim*0.5 = 64，
        # 且要求 sum(mrope_section)=rotary_dim//2=32（[12,10,10] 满足）。
        # mrope_interleaved 必须为 True（交错布局 THWTHW...），与 MG 训练
        # vlm_patch/models/interleaved_mrope.py::InterleavedMultimodalRotaryEmbedding
        # 及 utu_vl_30b_v4 一致；之前误用 False（块布局）导致训练/推理位码不一致→乱码。
        rope_scaling = _sglang_rope_scaling(config)
        self.rotary_emb = get_rope(
            self.head_dim,
            rotary_dim=self.head_dim,
            max_position=getattr(config, "max_position_embeddings", 4096),
            base=getattr(config, "rope_theta", 100000.0),
            is_neox_style=True,
            rope_scaling=rope_scaling,
            partial_rotary_factor=float(getattr(config, "rotary_percent", 0.5)),
        )

        self.attn = RadixAttention(
            self.num_heads,
            self.head_dim,
            self.scaling,
            num_kv_heads=self.num_kv_heads,
            layer_id=layer_id,
            prefix=add_prefix("attn", prefix),
        )

    def forward(
        self,
        positions: torch.Tensor,
        hidden_states: torch.Tensor,
        forward_batch: ForwardBatch,
        **kwargs,
    ) -> torch.Tensor:
        qkv, _ = self.qkv_proj(hidden_states)
        q, k, v = qkv.split([self.q_size, self.kv_size, self.kv_size], dim=-1)

        q = self.q_norm(q.view(-1, self.num_heads, self.head_dim)).view(
            -1, self.q_size
        )
        k = self.k_norm(k.view(-1, self.num_kv_heads, self.head_dim)).view(
            -1, self.kv_size
        )

        # positions: MRoPE 下为 (3, seq_len)
        q, k = self.rotary_emb(positions, q, k)

        attn_output = self.attn(q, k, v, forward_batch)
        output, _ = self.o_proj(attn_output)
        if self.tp_size > 1:
            output = tensor_model_parallel_all_reduce(output)
        return output


class YoutuVLDecoderLayer(nn.Module):
    """参考 qwen3_moe.Qwen3MoeDecoderLayer（去掉 deepstack / fused 优化）。"""

    def __init__(
        self,
        config,
        layer_id: int,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.layer_id = layer_id
        self.hidden_size = config.hidden_size

        if getattr(config, "experimental_attention_variant", None) == "kda":
            attn_cls = (
                YoutuVLKDAAttention
                if _is_kda_layer(config, layer_id)
                else YoutuVLMLAAttention
            )
        else:
            attn_cls = YoutuVLAttention
        self.self_attn = attn_cls(
            config=config,
            layer_id=layer_id,
            quant_config=quant_config,
            prefix=add_prefix("self_attn", prefix),
        )

        first_k_dense = getattr(config, "first_k_dense_replace", 1)
        if layer_id >= first_k_dense:
            self.mlp = YoutuVLMoE(
                config=config,
                layer_id=layer_id,
                quant_config=quant_config,
                prefix=add_prefix("mlp", prefix),
            )
        else:
            self.mlp = YoutuVLMLP(
                config=config,
                quant_config=quant_config,
                prefix=add_prefix("mlp", prefix),
            )

        self.input_layernorm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)
        self.post_attention_layernorm = RMSNorm(
            config.hidden_size, eps=config.rms_norm_eps
        )

    def forward(
        self,
        positions: torch.Tensor,
        hidden_states: torch.Tensor,
        forward_batch: ForwardBatch,
        residual: Optional[torch.Tensor],
        modality_id: Optional[torch.Tensor] = None,
        shared_modality_id: Optional[torch.Tensor] = None,
        zero_allocator: Optional[BumpAllocator] = None,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        # sglang 风格：residual 在下一层开头并入 layernorm
        if residual is None:
            residual = hidden_states
            hidden_states = self.input_layernorm(hidden_states)
        else:
            hidden_states, residual = self.input_layernorm(hidden_states, residual)

        qkv_latent_func = getattr(self.self_attn, "prepare_qkv_latent", None)
        if qkv_latent_func is not None:
            get_attn_tp_context().set_attn_inputs(
                AttentionInputs(hidden_states, forward_batch, qkv_latent_func)
            )
        try:
            hidden_states = self.self_attn(
                positions=positions,
                hidden_states=hidden_states,
                forward_batch=forward_batch,
                zero_allocator=zero_allocator,
            )
        finally:
            if qkv_latent_func is not None:
                get_attn_tp_context().clear_attn_inputs()

        hidden_states, residual = self.post_attention_layernorm(
            hidden_states, residual
        )
        if isinstance(self.mlp, YoutuVLMoE):
            hidden_states = self.mlp(
                hidden_states, modality_id=modality_id,
                shared_modality_id=shared_modality_id,
            )
        else:
            hidden_states = self.mlp(hidden_states)
        return hidden_states, residual


class YoutuVLLMModel(nn.Module):
    """UTU-VL Tiny MoE Pro LLM 骨干（参考 qwen3_vl_moe.Qwen3MoeLLMModel，去 deepstack）。"""

    def __init__(
        self,
        config,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.config = config
        self.hidden_size = config.hidden_size
        self.pp_group = get_pp_group()

        self.embed_tokens = VocabParallelEmbedding(
            config.vocab_size, config.hidden_size
        )

        self.layers = nn.ModuleList(
            [
                YoutuVLDecoderLayer(
                    config=config,
                    layer_id=i,
                    quant_config=quant_config,
                    prefix=add_prefix(f"layers.{i}", prefix),
                )
                for i in range(config.num_hidden_layers)
            ]
        )
        self.start_layer = 0
        self.end_layer = config.num_hidden_layers

        self.norm = RMSNorm(config.hidden_size, eps=config.rms_norm_eps)

    def get_input_embeddings(self) -> nn.Module:
        return self.embed_tokens

    def forward(
        self,
        input_ids: torch.Tensor,
        positions: torch.Tensor,
        forward_batch: ForwardBatch,
        input_embeds: Optional[torch.Tensor] = None,
        pp_proxy_tensors: Optional[PPProxyTensors] = None,
        modality_id: Optional[torch.Tensor] = None,
        shared_modality_id: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        if self.pp_group.is_first_rank:
            hidden_states = (
                input_embeds if input_embeds is not None else self.embed_tokens(input_ids)
            )
            residual = None
        else:
            assert pp_proxy_tensors is not None
            hidden_states = pp_proxy_tensors["hidden_states"]
            residual = pp_proxy_tensors["residual"]

        zero_allocator = BumpAllocator(
            buffer_size=(self.end_layer - self.start_layer) * 2,
            dtype=torch.float32,
            device=hidden_states.device,
        )
        for layer in self.layers[self.start_layer : self.end_layer]:
            hidden_states, residual = layer(
                positions=positions,
                hidden_states=hidden_states,
                forward_batch=forward_batch,
                residual=residual,
                modality_id=modality_id,
                shared_modality_id=shared_modality_id,
                zero_allocator=zero_allocator,
            )

        if not self.pp_group.is_last_rank:
            return PPProxyTensors(
                {"hidden_states": hidden_states, "residual": residual}
            )

        hidden_states, _ = self.norm(hidden_states, residual)
        return hidden_states


# ──────────────────────────────────────────────────────────────────────────────
# 顶层多模态模型
# ──────────────────────────────────────────────────────────────────────────────


class YoutuVLMoEForConditionalGeneration(nn.Module):
    """UTU-VL Tiny MoE Pro sglang 推理模型。

    复用 sglang 的 Qwen3VLMoeVisionModel 作为 ViT；LLM 骨干为自定义 YoutuVLLMModel。
    权重命名映射使 HF checkpoint 的 `model.language_model.*` / `model.visual.*` /
    `lm_head.*` 直接对齐 sglang 模块的 `model.*` / `visual.*` / `lm_head.*`。
    """

    def __init__(
        self,
        config,
        quant_config: Optional[QuantizationConfig] = None,
        prefix: str = "",
    ):
        super().__init__()
        self.pp_group = get_pp_group()
        self.quant_config = quant_config
        self.config = config

        # utu 的 vision_config 没有 deepstack_visual_indexes，补默认空列表以防
        # Qwen3VLMoeVisionModel 或框架访问。
        if not hasattr(config.vision_config, "deepstack_visual_indexes"):
            config.vision_config.deepstack_visual_indexes = []

        self.visual = Qwen3VLMoeVisionModel(
            config.vision_config,
            quant_config=None,
            norm_eps=getattr(config, "rms_norm_eps", 1e-6),
            prefix=add_prefix("model.visual", prefix),
            use_data_parallel=False,
        )

        self.model = YoutuVLLMModel(
            config=config,
            quant_config=quant_config,
            prefix=add_prefix("model.language_model", prefix),
        )

        if self.pp_group.is_last_rank:
            self.lm_head = ParallelLMHead(
                config.vocab_size,
                config.hidden_size,
                quant_config=quant_config,
                prefix=add_prefix("lm_head", prefix),
            )
        else:
            self.lm_head = nn.Identity()  # 占位，PP 中间 rank 不用

        # utu 始终启用 MRoPE：rope_parameters 含 mrope_section（sglang 框架据此
        # 自动计算 forward_batch.mrope_positions）。
        rope_parameters = getattr(config, "rope_parameters", None) or {}
        self.is_mrope_enabled = "mrope_section" in rope_parameters

        self.modality_granularity = modality_granularity(config)
        self.needs_modality_id = self.modality_granularity is not None
        if self.needs_modality_id:
            self._enable_vl_modality(config, self.modality_granularity)
        self.needs_shared_modality_id = (
            self.modality_granularity == GRANULARITY_SAMPLE
            and getattr(config, "enable_multimodal_shared_experts", False)
        )
        if self.needs_shared_modality_id:
            self._enable_vl_modality(config, GRANULARITY_TOKEN, VL_SHARED_MODALITY)

        self.logits_processor = LogitsProcessor(config)
        self.capture_aux_hidden_states = False

    @staticmethod
    def _enable_vl_modality(config, granularity: str, modality=VL_MODALITY) -> None:
        """Allocate stable masks for the configured prefill/decode/speculative graph sizes."""
        server_args = get_global_server_args()
        candidates = [
            int(getattr(server_args, "max_prefill_tokens", 0) or 0),
            int(getattr(server_args, "chunked_prefill_size", 0) or 0),
        ]

        graph_config = getattr(server_args, "cuda_graph_config", None)
        draft_tokens = max(
            1, int(getattr(server_args, "speculative_num_draft_tokens", 0) or 0)
        )
        for phase, tokens_per_unit in (("prefill", 1), ("decode", draft_tokens)):
            phase_config = getattr(graph_config, phase, None)
            sizes = getattr(phase_config, "bs", None) or ()
            candidates.extend(int(size) * tokens_per_unit for size in sizes)

        device = (
            torch.device("cuda", torch.cuda.current_device())
            if torch.cuda.is_available()
            else torch.device("cpu")
        )
        # int8, so even a very loose bound costs a few hundred kilobytes.
        modality.enable(
            max(max(candidates), 16384),
            device,
            granularity=granularity,
            image_token_id=getattr(config, "image_token_id", None),
            video_token_id=getattr(config, "video_token_id", None),
        )

    # ── PP 层范围 ──────────────────────────────────────────────────────────────
    @property
    def start_layer(self) -> int:
        return getattr(self.model, "start_layer", 0)

    @property
    def end_layer(self) -> int:
        return getattr(self.model, "end_layer", self.config.num_hidden_layers)

    # ── 多模态 embedding 入口（供 general_mm_embed_routine 调用）──────────────
    def get_image_feature(self, items: List[MultimodalDataItem]) -> torch.Tensor:
        pixel_values = torch.cat([item.feature for item in items], dim=0).type(
            self.visual.dtype
        )
        image_grid_thw = torch.concat([item.image_grid_thw for item in items], dim=0)
        return self.visual(pixel_values, grid_thw=image_grid_thw)

    def get_video_feature(self, items: List[MultimodalDataItem]) -> torch.Tensor:
        pixel_values = torch.cat([item.feature for item in items], dim=0).type(
            self.visual.dtype
        )
        video_grid_thw = torch.concat([item.video_grid_thw for item in items], dim=0)
        return self.visual(pixel_values, grid_thw=video_grid_thw)

    def get_input_embeddings(self) -> nn.Module:
        return self.model.embed_tokens

    def pad_input_ids(self, input_ids: List[int], mm_inputs):
        pattern = MultiModalityDataPaddingPatternMultimodalTokens()
        return pattern.pad_input_tokens(input_ids, mm_inputs)

    def prepare_context_parallel_metadata_for_dcp(
        self,
        seq_lens: torch.Tensor,
        extend_prefix_lens: torch.Tensor,
        extend_prefix_lens_cpu: torch.Tensor,
        extend_seq_lens: torch.Tensor,
        req_pool_indices: torch.Tensor,
        req_to_token: torch.Tensor,
        seq_lens_sum: int,
        kv_buffer_shape: torch.Size,
        kv_cache_dtype,
        kv_cache_device,
        create_chunked_prefix_cache_kv_indices_fn,
    ):
        """Use the upstream planner to gather prefix KV shards for DCP extend."""
        from sglang.srt.layers.dcp.planner import (
            prepare_decode_context_parallel_metadata,
        )

        return prepare_decode_context_parallel_metadata(
            seq_lens=seq_lens,
            extend_prefix_lens=extend_prefix_lens,
            extend_prefix_lens_cpu=extend_prefix_lens_cpu,
            extend_seq_lens=extend_seq_lens,
            req_pool_indices=req_pool_indices,
            req_to_token=req_to_token,
            seq_lens_sum=seq_lens_sum,
            kv_buffer_shape=kv_buffer_shape,
            kv_cache_dtype=kv_cache_dtype,
            kv_cache_device=kv_cache_device,
            create_chunked_prefix_cache_kv_indices_fn=create_chunked_prefix_cache_kv_indices_fn,
        )

    def build_decoder_modality_id(
        self, input_ids: torch.Tensor, forward_batch: ForwardBatch,
        modality=VL_MODALITY,
    ) -> Optional[torch.Tensor]:
        """Read a stable graph mask during capture, or derive the live eager mask."""
        if not self.needs_modality_id:
            return None
        num_tokens = input_ids.shape[0]
        if get_is_capture_mode():
            return modality.graph_view(num_tokens)
        return modality.eager_ids(forward_batch, num_tokens, input_ids.device)

    # ── 前向 ─────────────────────────────────────────────────────────────────
    @torch.no_grad()
    def forward(
        self,
        input_ids: torch.Tensor,
        positions: torch.Tensor,
        forward_batch: ForwardBatch,
        get_embedding: bool = False,
        pp_proxy_tensors: Optional[PPProxyTensors] = None,
    ):
        if self.is_mrope_enabled:
            positions = forward_batch.mrope_positions

        decoder_modality_id = self.build_decoder_modality_id(input_ids, forward_batch)
        shared_modality_id = (
            self.build_decoder_modality_id(input_ids, forward_batch, VL_SHARED_MODALITY)
            if self.needs_shared_modality_id else decoder_modality_id
        )

        hidden_states = general_mm_embed_routine(
            input_ids=input_ids,
            forward_batch=forward_batch,
            language_model=self.model,
            multimodal_model=self,
            positions=positions,
            pp_proxy_tensors=pp_proxy_tensors,
            modality_id=decoder_modality_id,
            shared_modality_id=shared_modality_id,
        )

        if self.pp_group.is_last_rank and not get_embedding:
            return self.logits_processor(
                input_ids, hidden_states, self.lm_head, forward_batch, None
            )
        return hidden_states

    # ── 权重加载（参考 qwen3_vl_moe.Qwen3VLMoeForConditionalGeneration.load_weights）
    def load_weights(self, weights: Iterable[Tuple[str, torch.Tensor]]):
        stacked_params_mapping = [
            # (param_name, shard_name, shard_id)
            (".qkv_proj", ".q_proj", "q"),
            (".qkv_proj", ".k_proj", "k"),
            (".qkv_proj", ".v_proj", "v"),
            ("gate_up_proj", "up_proj", 1),
            ("gate_up_proj", "gate_proj", 0),
        ]

        expert_params_mapping = FusedMoE.make_expert_params_mapping(
            ckpt_gate_proj_name="gate_proj",
            ckpt_down_proj_name="down_proj",
            ckpt_up_proj_name="up_proj",
            num_experts=self.config.n_routed_experts,
        )

        ignore_suffixes = (
            ".bias",
            "_bias",
            ".k_scale",
            "_k_scale",
            ".v_scale",
            "_v_scale",
            ".weight_scale",
            "_weight_scale",
            ".input_scale",
            "_input_scale",
        )

        params_dict = dict(self.named_parameters())
        buffers_dict = dict(self.named_buffers())
        # e_score_correction_bias may be a 1-D or [2, E] buffer/parameter.
        params_dict.update(buffers_dict)

        for name, loaded_weight in weights:
            # HF 命名 model.language_model.* -> sglang model.*
            name = name.replace(r"model.language_model.", r"model.")
            # 跳过 utu v3 残留 / mtp / deepstack 权重
            if "softmax_offset" in name or ".mtp" in name or name.startswith("mtp"):
                continue
            if "deepstack_merger_list" in name:
                continue

            layer_id = get_layer_id(name)
            if (
                "visual" not in name
                and layer_id is not None
                and (
                    layer_id < self.model.start_layer
                    or layer_id >= self.model.end_layer
                )
            ):
                continue

            used = False
            for param_name, weight_name, shard_id in stacked_params_mapping:
                if weight_name not in name:
                    continue
                # 跳过 expert 的 stacked（由 expert_params_mapping 处理）
                if "mlp.experts" in name:
                    continue
                if "visual" in name:
                    continue
                name = name.replace(weight_name, param_name)
                if name.endswith(ignore_suffixes) and name not in params_dict:
                    continue
                if name not in params_dict:
                    continue
                param = params_dict[name]
                param.weight_loader(param, loaded_weight, shard_id)
                used = True
                break

            if used:
                continue

            is_expert_weight = False
            for mapping in expert_params_mapping:
                # shared_experts weights are handled by stacked/fallthrough paths,
                # not by routed expert mapping.
                if "shared_experts" in name:
                    continue
                param_name, weight_name, expert_id, shard_id = mapping
                if weight_name not in name:
                    continue
                if "visual" in name:
                    continue
                is_expert_weight = True
                name_mapped = name.replace(weight_name, param_name)
                if (
                    name_mapped.endswith(ignore_suffixes)
                    and name_mapped not in params_dict
                ):
                    continue
                if name_mapped not in params_dict:
                    continue
                param = params_dict[name_mapped]
                weight_loader = param.weight_loader
                weight_loader(
                    param,
                    loaded_weight,
                    name_mapped,
                    shard_id=shard_id,
                    expert_id=expert_id,
                )
                name = name_mapped
                used = True
                break

            if used:
                continue

            if is_expert_weight:
                # expert 权重但不属于本 rank，跳过
                continue

            # 视觉权重对齐 sglang VisionAttention 命名
            if "visual" in name:
                name = name.replace(r"attn.qkv.", r"attn.qkv_proj.")
                name = name.replace(r"model.visual.", r"visual.")
            # 顶层 visual.* 已含 visual 前缀（sglang 模块即 self.visual）
            if name.startswith("model.visual."):
                name = name.replace(r"model.visual.", r"visual.")

            if name.endswith(ignore_suffixes) and name not in params_dict:
                continue

            if name in params_dict:
                param = params_dict[name]
                weight_loader = getattr(param, "weight_loader", default_weight_loader)
                weight_loader(param, loaded_weight)
            else:
                # 静默跳过未匹配项（如视觉 proj.bias 若不存在）
                pass


        self.post_load_weights()

    def post_load_weights(self):
        """Refresh absorbed MLA matrices and fused projections before graph capture."""
        for layer_id in range(self.model.start_layer, self.model.end_layer):
            self_attn = self.model.layers[layer_id].self_attn
            if isinstance(self_attn, YoutuVLKDAAttention):
                self_attn.fuse_projections()
                self_attn.prepare_fused_decode()
                continue
            if not isinstance(self_attn, YoutuVLMLAAttention):
                continue
            w_kc, w_vc = self_attn.kv_b_proj.weight.unflatten(
                0,
                (-1, self_attn.qk_nope_head_dim + self_attn.v_head_dim),
            ).split([self_attn.qk_nope_head_dim, self_attn.v_head_dim], dim=1)
            self_attn.w_kc = w_kc.transpose(1, 2).contiguous().transpose(1, 2)
            self_attn.w_vc = w_vc.contiguous().transpose(1, 2)
            if hasattr(self_attn.kv_b_proj, "weight_scale"):
                self_attn.w_scale = self_attn.kv_b_proj.weight_scale
            self_attn.fuse_a_projections()


EntryClass = YoutuVLMoEForConditionalGeneration
