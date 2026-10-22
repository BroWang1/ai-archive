# coding=utf-8
"""sglang 启动入口（UTU-VL Tiny MoE Pro 专用）。

为什么不用 ``python -m sglang.launch_server`` 直接启动？
  UTU-VL Tiny MoE Pro 的 ``YoutuVLMoEConfig.text_config`` 属性返回 ``self``（vLLM 兼容别名）。
  sglang 的 ``normalize_rope_scaling_compat``（hf_transformers_patches._patch）会递归
  遍历 ``text_config`` 等子配置，遇到 ``text_config is self`` 会无限递归 →
  ``RecursionError``。该函数在 ``ServerArgs.__init__ → ModelConfig → get_hf_text_config``
  阶段就被调用，**早于**外部 package 扫描（即早于 ``youtu_vl_moe.py`` 被 import），
  所以不能靠模型模块里的 monkeypatch 修复。

  本入口在 sglang 任何 config 加载之前，把 ``normalize_rope_scaling_compat`` 替换为
  带 ``visited`` 防环的等价实现（对其它模型行为不变），然后再走标准的
  ``prepare_server_args → run_server`` 流程。

用法（由 serve_youtu_vl_moe_sglang.sh 调用）：
  python -m sglang_adapt.launch <MODEL_PATH> --tp-size 8 ...
"""

import sys
import os

from sglang.srt.utils.hf_transformers import common as _common
from sglang.srt.utils import hf_transformers_patches as _patches
from sglang_adapt.linear_attn_registry import (
    apply_linear_attn_registration,
    log_resolved_schedule_settings,
)
from sglang_adapt.fa3_dcp import apply_fa3_dcp_patch
from sglang_adapt.kda_decode import apply_kda_fused_decode_h4_patch

_SUB_ATTRS = (
    "text_config",
    "llm_config",
    "language_config",
    "vision_config",
    "thinker_config",
)


def _safe_normalize(config) -> None:
    visited = set()

    def _patch(cfg):
        cid = id(cfg)
        if cid in visited:
            return
        visited.add(cid)
        rs = getattr(cfg, "rope_scaling", None)
        if isinstance(rs, dict) and "rope_type" in rs and "type" not in rs:
            rs["type"] = rs["rope_type"]
        for attr in _SUB_ATTRS:
            try:
                sub = getattr(cfg, attr, None)
            except Exception:
                sub = None
            if sub is not None and sub is not cfg:
                _patch(sub)

    _patch(config)


def apply_compat_patch() -> None:
    """把 sglang 的 normalize_rope_scaling_compat 替换为防环版本（幂等）。"""
    _patches.normalize_rope_scaling_compat = _safe_normalize
    _common.normalize_rope_scaling_compat = _safe_normalize


def apply_moe_align_small_numel_patch() -> None:
    """Use the upstream single-CTA align kernel for numel <= SMALL_NUMEL_LIMIT."""

    if os.environ.get("UTU_SMALL_NUMEL_MOE_ALIGN", "0") != "1":
        return
    import importlib

    mod = importlib.import_module(
        "sglang.srt.layers.moe.moe_runner.triton_utils.moe_align_block_size"
    )
    # 非 CUDA 或该版本没有这条快速路径时保持原状。
    if not getattr(mod, "_is_cuda", False) or not hasattr(mod, "SMALL_NUMEL_LIMIT"):
        return
    mod._CUDA_SMALL_BATCH_MAX_BUCKETS = 0


def apply_native_mrope_patch() -> None:
    """可选：强制 MRotaryEmbedding 走 forward_native（PyTorch 参考实现）而非 triton kernel。

    与 30b v4 适配保持一致：v4 用 SGLang 默认 triton MRoPE kernel 正常工作，本适配
    默认同样走 triton kernel（不在运行时改 MRoPE 实现）。MRoPE 的配置（half rope
    rotary_dim=64、mrope_section=[12,10,10]、mrope_interleaved=True）已在
    youtu_vl_moe.py 的 get_rope(...) 里和 v4 完全一致。

    仅当显式设 UTU_NATIVE_MROPE=1 时才用 PyTorch native 实现（用于对照排查）。
    """
    import os as _os
    if _os.environ.get("UTU_NATIVE_MROPE", "0") != "1":
        print("[UTU] native MRoPE patch NOT applied (default: SGLang triton kernel, same as v4).", flush=True)
        return
    from sglang.srt.layers.rotary_embedding.mrope import MRotaryEmbedding

    def _forward_cuda_native(self, positions, query, key, fused_set_kv_buffer_arg=None):
        return self.forward_native(positions, query, key, fused_set_kv_buffer_arg)

    MRotaryEmbedding.forward_cuda = _forward_cuda_native
    print("[UTU] native MRoPE patch applied (triton kernel disabled, matches HF/MG).", flush=True)


def apply_prefill_cuda_graph_patch() -> None:
    """Allowlist this arch for breakable prefill graphs, as SGLang does for Qwen3_5Moe/Kimi.

    ``SGLANG_EXTERNAL_MM_MODEL_ARCH`` marks this arch multimodal, which loading
    requires but which also trips SGLang's generic "multimodal => no breakable
    prefill graph" rule, so even text-only prefill ran eager.  Batches the graph
    cannot serve are rejected at replay by ``can_run_graph``; the allowlist only
    permits the capture attempt.  Capture stops at 2048 tokens, SGLang's MLA
    default, so the gain is confined to short prefills.

    Off by default: the graphed prefill is reproducible but not equal to eager,
    which is the same MLA kernel-dispatch effect behind that 2048 ceiling.  Note
    an explicit ``prefill.backend=breakable`` already bypasses the guard, so this
    switch only matters when the backend is left at its default.
    """

    if os.environ.get("UTU_PREFILL_CUDA_GRAPH", "0") != "1":
        return
    from sglang.srt.configs import model_config as _mc

    archs = getattr(_mc, "multimodal_breakable_cuda_graph_supported_model_archs", None)
    if archs is None:
        return
    arch = os.environ.get(
        "SGLANG_EXTERNAL_MM_MODEL_ARCH", "YoutuVLMoEForConditionalGeneration"
    )
    if arch not in archs:
        archs.append(arch)
        print(f"[UTU] prefill CUDA graph allowlisted for {arch}.", flush=True)


def apply_vl_modality_patch() -> None:
    """Refresh the modality-id buffer before every CUDA-graph launch.

    ``CudaGraphBufferRegistry.fill_from`` is the one place every runner (eager,
    decode graph, prefill graph) mirrors the live ForwardBatch into the
    graph-resident buffers, so it is also where the modality-aware router bias
    ids must be refreshed: a replay never re-enters the model, and neither the
    Python ``mm_inputs`` list nor the sample boundaries it would need are
    captured tensors.

    Eager forwards derive their own ids; graph forwards read these buffers.
    """
    from sglang.srt.model_executor.cuda_graph_buffer_registry import (
        CudaGraphBufferRegistry,
    )
    from sglang_adapt.vl_modality import VL_MODALITY, VL_SHARED_MODALITY

    if getattr(CudaGraphBufferRegistry, "_utu_vl_modality_patch", False):
        return

    original_fill_from = CudaGraphBufferRegistry.fill_from

    def _fill_from(self, forward_batch, *, raw_num_tokens, padded_num_tokens, **kwargs):
        original_fill_from(
            self,
            forward_batch,
            raw_num_tokens=raw_num_tokens,
            padded_num_tokens=padded_num_tokens,
            **kwargs,
        )
        for modality in (VL_MODALITY, VL_SHARED_MODALITY):
            if modality.enabled:
                modality.fill(forward_batch, raw_num_tokens, padded_num_tokens)

    CudaGraphBufferRegistry.fill_from = _fill_from
    CudaGraphBufferRegistry._utu_vl_modality_patch = True
    print(
        f"[UTU] VL modality buffer patch applied "
        f"({VL_MODALITY.granularity}-level).",
        flush=True,
    )


# import 本模块即施加补丁（早于任何 ServerArgs/config 加载）
apply_compat_patch()
# ServerArgs 构造时就会判定多模态是否允许 breakable prefill graph，白名单必须更早。
apply_prefill_cuda_graph_patch()
apply_kda_fused_decode_h4_patch()
apply_moe_align_small_numel_patch()
apply_native_mrope_patch()
# KDA state cache and MLA KV-cache geometry are selected while ServerArgs
# creates ModelConfig, earlier than SGLANG_EXTERNAL_MODEL_PACKAGE discovery.
apply_linear_attn_registration()
apply_vl_modality_patch()
apply_fa3_dcp_patch()


if __name__ == "__main__":
    from sglang.srt.plugins import load_plugins
    from sglang.srt.server_args import prepare_server_args
    from sglang.launch_server import run_server

    load_plugins()
    server_args = prepare_server_args(sys.argv[1:])
    log_resolved_schedule_settings(server_args)
    run_server(server_args)
