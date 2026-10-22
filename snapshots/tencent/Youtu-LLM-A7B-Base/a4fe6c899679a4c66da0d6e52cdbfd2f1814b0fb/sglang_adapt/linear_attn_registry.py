"""Early SGLang bootstrap for the UTU-VL KDA + MLA hybrid architecture.

This module is intentionally imported by :mod:`sglang_adapt.launch` before
``prepare_server_args``.  At that point SGLang must already know that
``YoutuVLMoEForConditionalGeneration`` owns a KDA radix state cache and that
its full-attention layers use MLA's latent KV-cache layout.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


_ARCH = "YoutuVLMoEForConditionalGeneration"
_MODEL_TYPE = "youtu_vl_moe"


class _YoutuConfigMatcherMeta(type):
    """Match both local and Transformers dynamic-module config classes.

    ``trust_remote_code=True`` gives Transformers precedence to ``auto_map``;
    consequently a local ``AutoConfig.register`` alone cannot guarantee the
    class identity used by SGLang's registry ``isinstance`` check.  Match on
    the stable model type and patch the dynamic class with KDA cache helpers
    just before it is consumed.
    """

    def __instancecheck__(cls, instance) -> bool:
        if getattr(instance, "model_type", None) != _MODEL_TYPE:
            return False
        _patch_youtu_config(type(instance))
        return True


class YoutuVLMoEConfigMatcher(metaclass=_YoutuConfigMatcherMeta):
    """Registry-only virtual config type; see :class:`_YoutuConfigMatcherMeta`."""


def _load_youtu_config_class():
    """Load the sibling remote-code config without importing HF modeling."""

    module_name = "configuration_youtu_vl_moe"
    module = sys.modules.get(module_name)
    if module is None:
        config_path = Path(__file__).resolve().parent.parent / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(module_name, config_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load UTU-VL config module from {config_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return module.YoutuVLMoEConfig


def _patch_youtu_config(config_cls) -> None:
    """Add the linear-attention properties expected by SGLang's cache pools."""

    if not hasattr(config_cls, "is_kda_layer"):

        def is_kda_layer(self, layer_idx: int) -> bool:
            pattern = getattr(self, "linear_attention_pattern", None)
            if pattern is None:
                pattern = [1, 1, 1, 0] * (self.num_hidden_layers // 4)
            return (
                getattr(self, "experimental_attention_variant", None) == "kda"
                and int(pattern[layer_idx]) == 1
            )

        config_cls.is_kda_layer = is_kda_layer

    if not hasattr(config_cls, "linear_layer_ids"):
        config_cls.linear_layer_ids = property(
            lambda self: [
                idx
                for idx in range(self.num_hidden_layers)
                if self.is_kda_layer(idx)
            ]
        )
    if not hasattr(config_cls, "full_attention_layer_ids"):
        config_cls.full_attention_layer_ids = property(
            lambda self: [
                idx
                for idx in range(self.num_hidden_layers)
                if not self.is_kda_layer(idx)
            ]
        )
    if not hasattr(config_cls, "mamba2_cache_params"):

        @property
        def mamba2_cache_params(self):
            from sglang.srt.configs.mamba_utils import (
                KimiLinearCacheParams,
                KimiLinearStateShape,
            )
            from sglang.srt.runtime_context import get_parallel

            shape = KimiLinearStateShape.create(
                tp_world_size=get_parallel().attn_tp_size,
                num_heads=self.num_attention_heads,
                head_dim=self.head_dim,
                conv_kernel_size=self.short_conv_kernel_size,
            )
            return KimiLinearCacheParams(shape=shape, layers=self.linear_layer_ids)

        config_cls.mamba2_cache_params = mamba2_cache_params


def _patch_model_config_shapes() -> None:
    """Teach ModelConfig that UTU's full-attention branch is MLA.

    SGLang's built-in MLA detection is architecture-name based.  This adapter
    uses a remote-code architecture name, so patch exactly that one architecture
    after the stock derivation has initialized common fields.
    """

    from sglang.srt.configs.model_config import AttentionArch, ModelConfig

    if getattr(ModelConfig, "_youtu_vl_moe_mla_patch", False):
        return

    original = ModelConfig._derive_model_shapes

    def _derive_model_shapes(self):
        original(self)
        if _ARCH not in (getattr(self.hf_config, "architectures", None) or []):
            return
        cfg = self.hf_text_config
        _patch_youtu_config(type(cfg))
        self.head_dim = cfg.qk_nope_head_dim + cfg.qk_rope_head_dim
        self.attention_arch = AttentionArch.MLA
        self.kv_lora_rank = cfg.kv_lora_rank
        self.qk_nope_head_dim = cfg.qk_nope_head_dim
        self.qk_rope_head_dim = cfg.qk_rope_head_dim
        self.v_head_dim = cfg.v_head_dim
        self.scaling = self.head_dim**-0.5
        # Hybrid KDA + MLA pools and layer setup consume this on the
        # ModelConfig itself (not only on the HF config).
        self.full_attention_layer_ids = list(cfg.full_attention_layer_ids)

    ModelConfig._derive_model_shapes = _derive_model_shapes
    ModelConfig._youtu_vl_moe_mla_patch = True


def apply_linear_attn_registration() -> None:
    """Register UTU-VL before SGLang creates ``ServerArgs`` or ``ModelConfig``."""

    from transformers import AutoConfig
    from sglang.srt.configs.linear_attn_model_registry import (
        LinearAttnModelSpec,
        register_linear_attn_model,
    )

    config_cls = _load_youtu_config_class()
    _patch_youtu_config(config_cls)
    # ``auto_map`` still takes precedence with --trust-remote-code, but
    # registering the sibling class supports configs with the map removed and
    # lets local tooling instantiate the same config without a dynamic-module
    # cache.  The registry matcher below handles either class identity.
    try:
        AutoConfig.register(_MODEL_TYPE, config_cls, exist_ok=True)
    except TypeError:
        try:
            AutoConfig.register(_MODEL_TYPE, config_cls)
        except ValueError:
            pass

    registry_module = sys.modules[
        "sglang.srt.configs.linear_attn_model_registry"
    ]
    already_registered = any(
        _ARCH in spec.arch_names
        for spec in registry_module._LINEAR_ATTN_MODEL_REGISTRY
    )
    if not already_registered:
        register_linear_attn_model(
            LinearAttnModelSpec(
                config_class=YoutuVLMoEConfigMatcher,
                backend_class_name=(
                    "sglang.srt.layers.attention.linear.kda_backend.KDAAttnBackend"
                ),
                arch_names=[_ARCH],
                uses_mamba_radix_cache=True,
                support_mamba_cache=True,
                # UTU drives SGLang's native KDAAttnBackend with the same
                # KimiLinearStateShape (per-head SSM state plus short-conv
                # state) as the built-in Kimi-linear models, so the backend
                # already writes the radix-cache track snapshots that the
                # extra-buffer ping-pong needs on both decode and extend.
                # Declaring False forced mamba_radix_cache_strategy=no_buffer,
                # which in turn forces disable_overlap_schedule=True and
                # serializes the CPU scheduler with every forward pass.
                support_mamba_cache_extra_buffer=True,
            )
        )

    _allow_mamba_extra_buffer_arch()
    _patch_model_config_shapes()


def _allow_mamba_extra_buffer_arch() -> None:
    """Let SGLang's resolver pick ``extra_buffer`` for this architecture.

    ``supports_mamba_cache_extra_buffer`` keys off a private frozenset of
    architecture names, not the ``LinearAttnModelSpec`` field, so setting the
    field alone still resolves to ``no_buffer`` -- which forces
    ``disable_overlap_schedule=True`` and serializes the CPU scheduler with
    every forward pass.  The set is private, so tolerate its absence on
    SGLang builds that resolve this differently.
    """

    try:
        from sglang.srt.arg_groups import overrides
    except ImportError:
        return

    arch_set = getattr(overrides, "_MAMBA_EXTRA_BUFFER_ARCHS", None)
    if arch_set is None:
        print(
            "[UTU] sglang.srt.arg_groups.overrides._MAMBA_EXTRA_BUFFER_ARCHS is "
            "missing; cannot opt into the extra-buffer mamba radix cache. "
            "Check the resolved mamba_radix_cache_strategy in the startup log.",
            flush=True,
        )
        return

    overrides._MAMBA_EXTRA_BUFFER_ARCHS = arch_set | {_ARCH}


__all__ = ["apply_linear_attn_registration", "log_resolved_schedule_settings"]


def log_resolved_schedule_settings(server_args) -> None:
    """Print the scheduler/cache knobs that silently gate decode throughput.

    ``mamba_radix_cache_strategy`` and ``disable_chunked_prefix_cache`` are
    resolved by SGLang rather than passed on the command line, and both are
    worth several ms of TPOT at batch size 1.  Surface them next to the other
    ``[UTU]`` startup lines instead of making people grep a 5000-line
    ``ServerArgs`` repr.
    """

    fields = (
        "disable_overlap_schedule",
        "mamba_radix_cache_strategy",
        "disable_chunked_prefix_cache",
        "chunked_prefill_size",
        "max_prefill_tokens",
        "linear_attn_backend",
    )
    resolved = " ".join(
        f"{name}={getattr(server_args, name, '<missing>')!r}" for name in fields
    )
    print(f"[UTU] resolved schedule settings: {resolved}", flush=True)
    if getattr(server_args, "disable_overlap_schedule", False):
        print(
            "[UTU] WARNING: the overlap scheduler is off, so the CPU scheduler "
            "runs serially with every forward pass (costly at small batch "
            "sizes). Expected cause: mamba_radix_cache_strategy resolved to "
            "'no_buffer'.",
            flush=True,
        )
