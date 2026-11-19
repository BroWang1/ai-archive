"""
This module applies all necessary runtime patches.


Patches applied:
    1. ZeRO-3 key rename + expert fuse + buffer loading
       Handles both inner format (original) and outer format (pre-converted) checkpoints.
       - Key renaming: mlp.router.gate -> mlp.gate, etc.
       - Per-expert -> 3D fuse: experts.N.gate_proj -> experts.gate_up_proj
       - Buffer loading: e_score_correction_bias (ZeRO-3 only handles parameters)
    2. Tokenizer file copy (CustomSaveCallback)
       Ensures each checkpoint directory is self-contained for inference.
"""

import os
import re
import logging
import shutil
from typing import Optional

import torch

logger = logging.getLogger(__name__)

# ============================================================================
# Patch 1: Key rename + expert fuse + buffer loading for ZeRO-3
#
# The checkpoint may be in either inner format (original) or outer format
# (pre-converted by convert_ckpt_to_outer.py). This patch handles both:
#   - Key renaming: mlp.router.gate -> mlp.gate, etc.
#   - Per-expert -> 3D fuse: experts.N.gate_proj -> experts.gate_up_proj
#   - Buffer loading: e_score_correction_bias (ZeRO-3 only handles parameters)
#
# If the checkpoint is already in outer format, the rename/fuse logic is
# effectively a no-op (no matching keys to transform).
# ============================================================================

# Key renames: checkpoint inner format -> model format
_CKPT_KEY_RENAMES = [
    ("mlp.router.gate.", "mlp.gate."),
    ("mlp.expert_bias", "mlp.e_score_correction_bias"),
    ("mlp.shared_mlp.", "mlp.shared_experts."),
    # Also handle even older checkpoints that use mlp.gate.wg
    ("mlp.gate.wg.", "mlp.gate."),
]

# Regex to match per-expert keys in checkpoint
# e.g. model.layers.10.mlp.experts.5.gate_proj.weight
_EXPERT_KEY_RE = re.compile(
    r"^(.*\.mlp\.experts\.)(\d+)\.(gate_proj|up_proj|down_proj)\.weight$"
)


def _apply_buffer_loading_patch():
    """Patch the DeepSpeed ZeRO-3 state_dict loader to handle:
    1. Key renaming (inner checkpoint format -> model format)
    2. Per-expert -> 3D fused expert tensors
    3. Manual buffer loading (e_score_correction_bias etc.)

    ZeRO-3's _load_state_dict_into_zero3_model only handles named_parameters.
    Buffers like e_score_correction_bias must be loaded manually.
    """
    try:
        from transformers.integrations.deepspeed import (
            _load_state_dict_into_zero3_model as _orig_load_zero3,
        )
        import transformers.integrations.deepspeed as _ds_mod
        import transformers.modeling_utils as _mu_mod
    except ImportError:
        logger.warning(
            "Could not import transformers.integrations.deepspeed; "
            "buffer loading patch NOT applied."
        )
        return

    def _patched_load_zero3(model_to_load, state_dict, *args, **kwargs):
        # Step 1: Key rename + per-expert collection
        new_sd = {}
        expert_groups = {}  # prefix -> {expert_idx -> {proj_name -> tensor}}

        for k, v in state_dict.items():
            m = _EXPERT_KEY_RE.match(k)
            if m:
                # Per-expert key: collect for fusion
                prefix = m.group(1)
                expert_idx = int(m.group(2))
                proj_name = m.group(3)
                if prefix not in expert_groups:
                    expert_groups[prefix] = {}
                if expert_idx not in expert_groups[prefix]:
                    expert_groups[prefix][expert_idx] = {}
                expert_groups[prefix][expert_idx][proj_name] = v
            else:
                # Non-expert key: apply simple renames
                new_k = k
                for old_sub, new_sub in _CKPT_KEY_RENAMES:
                    if old_sub in new_k:
                        new_k = new_k.replace(old_sub, new_sub)
                new_sd[new_k] = v

        # Step 2: Fuse expert groups into 3D tensors
        if expert_groups:
            for prefix in sorted(expert_groups.keys()):
                experts = expert_groups[prefix]
                num_experts = max(experts.keys()) + 1
                gate_up_list = []
                down_list = []
                for i in range(num_experts):
                    if i not in experts:
                        logger.warning(
                            "HYV4 Patch 1: Missing expert %d in %s", i, prefix
                        )
                        continue
                    exp = experts[i]
                    if "gate_proj" in exp and "up_proj" in exp:
                        gate_up_list.append(
                            torch.cat([exp["gate_proj"], exp["up_proj"]], dim=0)
                        )
                    if "down_proj" in exp:
                        down_list.append(exp["down_proj"])
                if gate_up_list:
                    new_sd[f"{prefix}gate_up_proj"] = torch.stack(gate_up_list, dim=0)
                if down_list:
                    new_sd[f"{prefix}down_proj"] = torch.stack(down_list, dim=0)
            logger.info(
                "HYV4 Patch 1: Fused %d expert groups from per-expert to 3D format.",
                len(expert_groups)
            )
            del expert_groups

        # Step 3: Load parameters via original ZeRO-3 loader
        result = _orig_load_zero3(model_to_load, new_sd, *args, **kwargs)

        # Step 4: Manually load buffers (e.g. e_score_correction_bias)
        # ZeRO-3's loader only handles named_parameters, not named_buffers.
        buffers_loaded = 0
        for name, buf in model_to_load.named_buffers():
            if name in new_sd:
                src_tensor = new_sd[name]
                if isinstance(src_tensor, torch.Tensor):
                    buf.data.copy_(src_tensor.to(buf.dtype))
                    buffers_loaded += 1
                    if isinstance(result, tuple) and len(result) >= 2:
                        if isinstance(result[1], set):
                            result[1].discard(name)
        if buffers_loaded > 0:
            logger.info(
                "HYV4 Patch 1: Manually loaded %d buffers into model.",
                buffers_loaded
            )

        del new_sd
        return result

    _ds_mod._load_state_dict_into_zero3_model = _patched_load_zero3
    _mu_mod._load_state_dict_into_zero3_model = _patched_load_zero3
    logger.info(
        "HYV4 patch applied: ZeRO-3 key rename + expert fuse + buffer loading."
    )

# ============================================================================
# Patch 2: Tokenizer file copy callback
#
# Ensures each checkpoint directory is self-contained for inference by
# copying all tokenizer-related files from the original tokenizer path.
# ============================================================================

# Tokenizer files that should be copied to each checkpoint
_TOKENIZER_FILES = [
    "config.json",
    "generation_config.json",
    "tokenizer_config.json",
    "tokenizer.json",
    "chat_template.jinja",
    "preprocessor_config.json",
    "processor_config.json",
    "video_preprocessor_config.json",
    "hy.tiktoken",
    "tokenization_hy.py",
    "special_tokens_map.json",
]

def _copy_tokenizer_to_checkpoint(tokenizer_dir: str, checkpoint_dir: str):
    """Copy tokenizer files from tokenizer_dir to checkpoint_dir."""
    for fname in _TOKENIZER_FILES:
        src = os.path.join(tokenizer_dir, fname)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(checkpoint_dir, fname))

# ============================================================================
# LLaMA Factory Callback: integrates patch 2 (tokenizer copy) into the
# training loop.
# ============================================================================

try:
    from transformers import TrainerCallback
    from transformers.trainer_utils import PREFIX_CHECKPOINT_DIR

    class HYV4PatchCallback(TrainerCallback):
        """
        LLaMA Factory compatible callback that applies HYV4-specific patches.

        Add to your YAML or pass to Trainer:
            callbacks: [hy_v4_patches.HYV4PatchCallback]
        """

        def __init__(self, tokenizer_dir: Optional[str] = None):
            """
            Args:
                tokenizer_dir: Path to the original tokenizer directory.
                    If None, will try to use model_name_or_path from training args.
            """
            self._tokenizer_dir = tokenizer_dir

        def on_save(self, args, state, control, **kwargs):
            # --- Patch 2: Copy tokenizer files ---
            if torch.distributed.is_initialized() and torch.distributed.get_rank() != 0:
                return control

            checkpoint_dir = os.path.join(
                args.output_dir,
                f"{PREFIX_CHECKPOINT_DIR}-{state.global_step}",
            )

            # Determine tokenizer directory
            tokenizer_dir = self._tokenizer_dir
            if tokenizer_dir is None:
                # Try common locations
                tokenizer_dir = getattr(args, "tokenizer_name_or_path", None)
                if tokenizer_dir is None:
                    tokenizer_dir = getattr(args, "model_name_or_path", None)

            if tokenizer_dir and os.path.isdir(tokenizer_dir):
                _copy_tokenizer_to_checkpoint(tokenizer_dir, checkpoint_dir)
                logger.info(
                    "HYV4: Copied tokenizer files from %s to %s",
                    tokenizer_dir, checkpoint_dir
                )

            return control

except ImportError:
    logger.warning(
        "transformers not available; HYV4PatchCallback not defined."
    )

# ============================================================================
# Patch 3: Memory-efficient model loading for ZeRO-3 and FSDP1
#
# Previous approach: shard-by-shard manual loading that bypassed model class's
# from_pretrained, causing VL key prefix mapping to be lost (model.layers ->
# model.language_model.layers, vit. -> model.vision_tower., etc.).
#
# New approach (aligned with ms-swift): ensure HfDeepSpeedConfig is set before
# calling the original from_pretrained, so transformers' native ZeRO-3 loading
# path handles key mapping automatically via the model class internals.
#
# ZeRO-3 path:
#   1. Check if is_deepspeed_zero3_enabled() is already True
#   2. If not, detect DeepSpeed config and create HfDeepSpeedConfig
#   3. Call original from_pretrained — transformers handles efficient loading
#      (meta tensors + shard-by-shard scatter) natively when ZeRO-3 is active
#   4. Key renames (Patch 1) are applied via the patched
#      _load_state_dict_into_zero3_model hook
#
# FSDP1 path:
#   - local_rank 0: load real weights to CPU via original from_pretrained
#   - other ranks: create model on meta device (zero CPU memory)
#   - FSDP's sync_module_states broadcasts weights from rank 0
# ============================================================================

def _apply_shard_loading_patch():
    """Monkey-patch AutoModelForCausalLM and AutoModelForImageTextToText
    from_pretrained to ensure efficient loading for ZeRO-3 and FSDP1."""
    import sys
    import json as _json
    import transformers

    _orig_from_pretrained = transformers.AutoModelForCausalLM.from_pretrained
    _AutoVL = getattr(transformers, 'AutoModelForImageTextToText', None)
    _orig_vl_from_pretrained = _AutoVL.from_pretrained if _AutoVL is not None else None

    def _is_vl_config(config):
        """Detect whether the config corresponds to a VL (vision-language) model."""
        if config is None:
            return False
        model_type = getattr(config, 'model_type', '')
        if 'vl' in model_type.lower():
            return True
        if hasattr(config, 'vision_config') or hasattr(config, 'text_config'):
            return True
        return False

    def _is_fsdp_requested():
        """Check if FSDP is being used (not DeepSpeed)."""
        accel_fsdp = str(os.environ.get("ACCELERATE_USE_FSDP", "")).lower()
        if accel_fsdp in {"1", "true", "yes"}:
            return True
        return "--fsdp" in sys.argv

    def _disable_router_logits_if_needed(model):
        """Disable output_router_logits to avoid unnecessary memory usage."""
        if hasattr(model, 'config') and getattr(model.config, 'output_router_logits', False):
            model.config.output_router_logits = False
            logger.info("[HYV4 Patch 3] Disabled output_router_logits.")
        return model

    def _disable_engram(config):
        """Disable Engram layers in config for training.

        Engram tables are very large (~32 GB per layer in bf16) and cause
        ZeRO-3 all-gather to hang or OOM during training.  The checkpoint
        stores engram_layer_head_vocab_sizes as nested lists which also
        triggers TypeError in the current modeling code.  Following the
        deepspeed_support/train_vl.py approach, we simply set
        engram_layer_ids to None so no Engram layers are created.
        """
        if config is None:
            return config
        text_cfg = getattr(config, 'text_config', config)
        if hasattr(text_cfg, 'engram_layer_ids') and text_cfg.engram_layer_ids is not None:
            old_val = text_cfg.engram_layer_ids
            text_cfg.engram_layer_ids = None
            print(f"[HYV4 Patch] Disabled Engram (set engram_layer_ids=None) for training.", flush=True)
        return config

    def _fsdp_load(pretrained_model_name_or_path, *args, **kwargs):
        """FSDP-safe loading: rank 0 loads to CPU, others use meta device."""
        kwargs = dict(kwargs)
        kwargs.setdefault("low_cpu_mem_usage", True)

        local_rank = int(os.environ.get("LOCAL_RANK", "0"))
        if local_rank != 0:
            logger.info(
                "[HYV4 Patch 3] FSDP mode: local_rank=%d != 0, "
                "creating model on meta device (zero CPU memory). "
                "Weights will be synced from rank 0 by FSDP.",
                local_rank,
            )
            config = transformers.AutoConfig.from_pretrained(
                pretrained_model_name_or_path,
                trust_remote_code=kwargs.get("trust_remote_code", False),
            )
            _disable_engram(config)
            kwargs["config"] = config
            torch_dtype = kwargs.get("torch_dtype", None)
            if torch_dtype is None:
                torch_dtype = getattr(config, "torch_dtype", torch.bfloat16)
            if not isinstance(torch_dtype, torch.dtype):
                torch_dtype = torch.bfloat16
            with torch.device("meta"):
                _AutoCls = _AutoVL if (_AutoVL is not None and _is_vl_config(config)) else transformers.AutoModelForCausalLM
                model = _AutoCls.from_config(
                    config,
                    torch_dtype=torch_dtype,
                    trust_remote_code=kwargs.get("trust_remote_code", False),
                )
            return _disable_router_logits_if_needed(model)

        # local_rank 0: load real weights to CPU
        logger.info(
            "[HYV4 Patch 3] FSDP mode: local_rank=0, loading real weights to CPU."
        )
        config = transformers.AutoConfig.from_pretrained(
            pretrained_model_name_or_path,
            trust_remote_code=kwargs.get("trust_remote_code", False),
        )
        _disable_engram(config)
        kwargs["config"] = config
        kwargs["device_map"] = {"": "cpu"}
        _fallback_fn = _orig_vl_from_pretrained if (_AutoVL is not None and _is_vl_config(config)) else _orig_from_pretrained
        model = _fallback_fn(pretrained_model_name_or_path, *args, **kwargs)
        return _disable_router_logits_if_needed(model)

        # ZeRO-3 not yet enabled
    def _patched_from_pretrained(pretrained_model_name_or_path, *args, **kwargs):
        """Patched from_pretrained that ensures efficient loading for ZeRO-3 and FSDP1."""
        model_path = pretrained_model_name_or_path

        # Only intercept local directory paths with safetensors files
        if not (isinstance(model_path, str) and os.path.isdir(model_path)):
            config = kwargs.get("config")
            if config is None:
                config = transformers.AutoConfig.from_pretrained(
                    model_path,
                    trust_remote_code=kwargs.get("trust_remote_code", False),
                )
            _disable_engram(config)
            kwargs["config"] = config
            _fallback_fn = _orig_vl_from_pretrained if (_AutoVL is not None and _is_vl_config(config)) else _orig_from_pretrained
            return _fallback_fn(pretrained_model_name_or_path, *args, **kwargs)

        index_file = os.path.join(model_path, "model.safetensors.index.json")
        single_file = os.path.join(model_path, "model.safetensors")
        if not (os.path.isfile(index_file) or os.path.isfile(single_file)):
            config = kwargs.get("config")
            if config is None:
                config = transformers.AutoConfig.from_pretrained(
                    model_path,
                    trust_remote_code=kwargs.get("trust_remote_code", False),
                )
            _disable_engram(config)
            kwargs["config"] = config
            _fallback_fn = _orig_vl_from_pretrained if (_AutoVL is not None and _is_vl_config(config)) else _orig_from_pretrained
            return _fallback_fn(pretrained_model_name_or_path, *args, **kwargs)

        # FSDP path: rank-aware loading
        if _is_fsdp_requested():
            return _fsdp_load(pretrained_model_name_or_path, *args, **kwargs)

        # ZeRO-3 path: ensure HfDeepSpeedConfig is set, then use native from_pretrained
        from transformers.integrations.deepspeed import is_deepspeed_zero3_enabled

        if is_deepspeed_zero3_enabled():
            config = kwargs.get("config")
            if config is None:
                config = transformers.AutoConfig.from_pretrained(
                    model_path,
                    trust_remote_code=kwargs.get("trust_remote_code", False),
                )
            _disable_engram(config)
            kwargs["config"] = config
            _load_fn = _orig_vl_from_pretrained if (_AutoVL is not None and _is_vl_config(config)) else _orig_from_pretrained
            model = _load_fn(pretrained_model_name_or_path, *args, **kwargs)
            return _disable_router_logits_if_needed(model)

        # ZeRO-3 not yet enabled — try to detect and set HfDeepSpeedConfig
        # This handles the case where from_pretrained is called before
        # TrainingArguments has set up the DeepSpeed config.
        ds_config_path = os.environ.get("DEEPSPEED_CONFIG_FILE", None)
        if ds_config_path is None:
            ds_config_path = os.environ.get("DEEPSPEED_CONFIG", None)
        if ds_config_path is None:
            for i, arg in enumerate(sys.argv):
                if arg == '--deepspeed' and i + 1 < len(sys.argv):
                    ds_config_path = sys.argv[i + 1]
                    break

        if ds_config_path is not None and os.path.isfile(ds_config_path):
            with open(ds_config_path, "r") as f:
                ds_config = _json.load(f)
            zero_stage = ds_config.get("zero_optimization", {}).get("stage", 0)
            if zero_stage == 3:
                from transformers.integrations.deepspeed import HfDeepSpeedConfig
                _ds_config_obj = HfDeepSpeedConfig(ds_config_path)  # noqa: F841

                config = kwargs.get("config")
                if config is None:
                    config = transformers.AutoConfig.from_pretrained(
                        model_path,
                        trust_remote_code=kwargs.get("trust_remote_code", False),
                    )
                _disable_engram(config)
                kwargs["config"] = config
                _load_fn = _orig_vl_from_pretrained if (_AutoVL is not None and _is_vl_config(config)) else _orig_from_pretrained
                model = _load_fn(pretrained_model_name_or_path, *args, **kwargs)
                return _disable_router_logits_if_needed(model)

        # Fallback: no DeepSpeed ZeRO-3 detected, use FSDP-style loading
        logger.info(
            "[HYV4 Patch 3] No ZeRO-3 config detected, using FSDP-style fallback."
        )
        return _fsdp_load(pretrained_model_name_or_path, *args, **kwargs)

    # Apply the monkey-patch to both CausalLM and VL auto classes
    transformers.AutoModelForCausalLM.from_pretrained = staticmethod(_patched_from_pretrained)
    if hasattr(transformers, 'AutoModelForImageTextToText'):
        transformers.AutoModelForImageTextToText.from_pretrained = staticmethod(_patched_from_pretrained)
    logger.info(
        "HYV4 Patch 3 applied: efficient model loading for ZeRO-3 and FSDP1. "
        "ZeRO-3 uses native from_pretrained (key mapping by model class). "
        "Patched: AutoModelForCausalLM + AutoModelForImageTextToText."
    )


# ============================================================================
# Auto-apply patches on import
# ============================================================================

# Patch 1: ZeRO-3 key rename + expert fuse + buffer loading
_apply_buffer_loading_patch()

# Patch 3: Memory-efficient shard-by-shard loading
_apply_shard_loading_patch()

# Patch 4: Unify model dtype before FSDP wrap
# FSDP1 requires all parameters in the same FSDP unit to have uniform dtype.
# After LoRA injection, adapter params are float32 while base model is bfloat16.
# This patch casts all parameters to bf16 before FSDP wraps the model.
def _apply_fsdp_dtype_patch():
    """Monkey-patch Trainer to cast model to bf16 before FSDP wrap."""
    try:
        from transformers import Trainer

        _orig_prepare_for_training = Trainer._prepare_for_training

        def _patched_prepare_for_training(self, *args, **kwargs):
            # Cast all model parameters to bf16 before FSDP wrap and disable
            # mixed precision to prevent Accelerate from upcasting bf16→fp32.
            if getattr(self.args, 'fsdp', False):
                model = self.model
                dtype_counts = {}
                for p in model.parameters():
                    dt = str(p.dtype)
                    dtype_counts[dt] = dtype_counts.get(dt, 0) + 1

                if len(dtype_counts) > 1:
                    logger.info(
                        "[HYV4 Patch 4] Mixed dtypes detected before FSDP wrap: %s. "
                        "Casting all parameters to bfloat16.",
                        dtype_counts
                    )
                    for p in model.parameters():
                        if p.dtype != torch.bfloat16:
                            p.data = p.data.to(torch.bfloat16)
                else:
                    logger.info(
                        "[HYV4 Patch 4] All params already uniform dtype: %s",
                        dtype_counts
                    )

                # Disable FSDP mixed precision to prevent Accelerate from
                # upcasting bf16 params to fp32 during wrap. Since all params
                # are already bf16 (cast above), we don't need FSDP's mixed
                # precision policy. This saves ~2x GPU memory per shard.
                try:
                    if hasattr(self, 'accelerator'):
                        # Level 1: Set accelerator state _mixed_precision to "no"
                        # Note: mixed_precision is a property, must set _mixed_precision
                        if hasattr(self.accelerator, 'state'):
                            old_mp = getattr(self.accelerator.state, '_mixed_precision', None)
                            self.accelerator.state._mixed_precision = "no"
                            logger.info(
                                "[HYV4 Patch 4] Set accelerator.state._mixed_precision='no' "
                                "(was: %s) to prevent bf16→fp32 upcast.", old_mp
                            )
                        # Level 2: Clear the FSDP plugin's mixed_precision_policy
                        fsdp_plugin = getattr(self.accelerator.state, 'fsdp_plugin', None)
                        if fsdp_plugin is not None:
                            if hasattr(fsdp_plugin, 'mixed_precision_policy'):
                                fsdp_plugin.mixed_precision_policy = None
                            if hasattr(fsdp_plugin, 'kwargs'):
                                fsdp_plugin.kwargs.pop('mixed_precision', None)
                            logger.info(
                                "[HYV4 Patch 4] Cleared fsdp_plugin mixed_precision_policy."
                            )
                    else:
                        logger.warning(
                            "[HYV4 Patch 4] self.accelerator not found, cannot disable mixed precision."
                        )
                    # Level 3: Environment variable (for any lazy initialization)
                    os.environ["ACCELERATE_MIXED_PRECISION"] = "no"
                except Exception as e:
                    logger.warning(
                        "[HYV4 Patch 4] Failed to disable mixed precision: %s", e
                    )

            # ---- Fix PEFT + FSDP _no_split_modules mismatch ----
            # PEFT's fsdp_auto_wrap_policy iterates _no_split_modules and calls
            # get_module_class_from_name() for each class name. If a class is
            # listed but not instantiated in the model (e.g. HYV4FlashEngramLayer
            # when engram is disabled), the lookup returns None and PEFT raises:
            #   "Could not find the transformer layer class to wrap in the model."
            # Fix: collect all actual module class names and prune _no_split_modules.
            try:
                actual_cls_names = {m.__class__.__name__ for m in self.model.modules()}
                # Walk through all sub-models (PeftModel wraps the base model)
                for sub in self.model.modules():
                    if hasattr(sub, '_no_split_modules') and sub._no_split_modules:
                        original = list(sub._no_split_modules)
                        pruned = [c for c in original if c in actual_cls_names]
                        if len(pruned) < len(original):
                            removed = set(original) - set(pruned)
                            sub._no_split_modules = pruned
                            logger.info(
                                "[HYV4 Patch 4] Pruned _no_split_modules: removed %s "
                                "(not found in model). Remaining: %s",
                                removed, pruned
                            )
            except Exception as e:
                logger.warning(
                    "[HYV4 Patch 4] Failed to prune _no_split_modules: %s", e
                )

            return _orig_prepare_for_training(self, *args, **kwargs)

        Trainer._prepare_for_training = _patched_prepare_for_training
        logger.info(
            "HYV4 Patch 4 applied: unify model dtype to bf16 before FSDP wrap."
        )
    except (ImportError, AttributeError) as e:
        logger.warning("[HYV4 Patch 4] Could not apply dtype patch: %s", e)

_apply_fsdp_dtype_patch()

# Patch 5: Fix CustomSeq2SeqTrainer.create_optimizer signature
# New transformers (5.15+) calls self.create_optimizer(model) with a model arg,
# but LLaMA Factory's CustomSeq2SeqTrainer.create_optimizer(self) doesn't accept it.
def _apply_create_optimizer_patch():
    """Monkey-patch CustomSeq2SeqTrainer.create_optimizer to accept optional model arg."""
    try:
        from llamafactory.train.sft.trainer import CustomSeq2SeqTrainer

        _orig_create_optimizer = CustomSeq2SeqTrainer.create_optimizer

        def _patched_create_optimizer(self, model=None):
            return _orig_create_optimizer(self)

        CustomSeq2SeqTrainer.create_optimizer = _patched_create_optimizer
        logger.info(
            "HYV4 Patch 5 applied: CustomSeq2SeqTrainer.create_optimizer "
            "now accepts optional model argument for transformers >= 5.15."
        )
    except (ImportError, AttributeError) as e:
        logger.warning("[HYV4 Patch 5] Could not apply create_optimizer patch: %s", e)

_apply_create_optimizer_patch()

# Patch 6: Fix LLaMA Factory's _gradient_checkpointing_enable signature
# New transformers (5.16+) trainer calls model.gradient_checkpointing_enable()
# with every_n_layers and offload kwargs. But LLaMA Factory replaces this method
# with its own _gradient_checkpointing_enable that only accepts
# (self, gradient_checkpointing_kwargs, use_unsloth_gc). This causes:
#   TypeError: _gradient_checkpointing_enable() got an unexpected keyword argument 'every_n_layers'
# Fix: patch LLaMA Factory's function to accept and ignore the extra kwargs.
def _apply_gradient_checkpointing_compat_patch():
    """Patch LLaMA Factory's _gradient_checkpointing_enable to accept extra kwargs
    from new transformers (every_n_layers, offload)."""
    try:
        import llamafactory.model.model_utils.checkpointing as _lf_gc_mod

        _orig_gc_enable = _lf_gc_mod._gradient_checkpointing_enable

        def _patched_gc_enable(self, gradient_checkpointing_kwargs=None, **kwargs):
            # Filter out kwargs not accepted by the original LLaMA Factory function
            # (every_n_layers, offload from new transformers trainer)
            use_unsloth_gc = kwargs.pop("use_unsloth_gc", False)
            if kwargs:
                logger.info(
                    "[HYV4 Patch 6] Ignoring extra gradient_checkpointing kwargs "
                    "not supported by LLaMA Factory: %s", list(kwargs.keys())
                )
            return _orig_gc_enable(
                self,
                gradient_checkpointing_kwargs=gradient_checkpointing_kwargs,
                use_unsloth_gc=use_unsloth_gc,
            )

        _lf_gc_mod._gradient_checkpointing_enable = _patched_gc_enable
        logger.info(
            "HYV4 Patch 6 applied: LLaMA Factory _gradient_checkpointing_enable "
            "now accepts extra kwargs (every_n_layers, offload) from transformers >= 5.16."
        )
    except (ImportError, AttributeError) as e:
        logger.warning("[HYV4 Patch 6] Could not apply gradient checkpointing compat patch: %s", e)

_apply_gradient_checkpointing_compat_patch()

# Patch 7: Fix LLaMA Factory's custom_gradient_checkpointing_func compatibility
# with transformers-hy4flash's modeling_layers.py.
#
# LLaMA Factory's custom_gradient_checkpointing_func (checkpointing.py:86) does:
#   module = func.func.__self__
# This assumes func is partial(bound_method, ...) where bound_method has __self__.
#
# But transformers-hy4flash's modeling_layers.py:121 passes:
#   partial(forward, self, **kwargs)
# where forward is a plain function (not a bound method), so func.func has no __self__.
# The module (self) is instead the first positional arg in func.args.
#
# Fix: patch get_custom_gradient_checkpointing_func to handle both cases.
def _apply_gc_func_compat_patch():
    """Patch LLaMA Factory's custom_gradient_checkpointing_func to handle
    partial(plain_function, module, ...) in addition to partial(bound_method, ...)."""
    try:
        import torch
        from functools import partial
        import llamafactory.model.model_utils.checkpointing as _lf_gc_mod

        _orig_get_custom_gc_func = _lf_gc_mod.get_custom_gradient_checkpointing_func

        def _patched_get_custom_gc_func(gradient_checkpointing_func):
            from functools import wraps, WRAPPER_ASSIGNMENTS

            @wraps(gradient_checkpointing_func, assigned=WRAPPER_ASSIGNMENTS + ("__self__",))
            def custom_gradient_checkpointing_func(func, *args, **kwargs):
                # Extract the module from func (a partial object or bound method)
                module = None
                if isinstance(func, partial):
                    if hasattr(func.func, '__self__'):
                        # Standard case: partial(bound_method, ...)
                        module = func.func.__self__
                    elif func.args and isinstance(func.args[0], torch.nn.Module):
                        # transformers-hy4flash case: partial(plain_function, module, ...)
                        module = func.args[0]
                    else:
                        # Fallback: try original behavior
                        module = func.func.__self__
                else:
                    module = func.__self__

                has_grad = False
                if any(param.requires_grad for param in module.parameters()):
                    has_grad = True
                    for arg in args:
                        if torch.is_tensor(arg) and torch.is_floating_point(arg):
                            arg.requires_grad_(True)
                            break

                if has_grad:
                    return gradient_checkpointing_func(func, *args, **kwargs)
                else:
                    return func(*args)

            return custom_gradient_checkpointing_func

        _lf_gc_mod.get_custom_gradient_checkpointing_func = _patched_get_custom_gc_func
        print("[HYV4 Patch] Patched get_custom_gradient_checkpointing_func for "
              "transformers-hy4flash compatibility (partial(forward, self, ...) support).",
              flush=True)
    except (ImportError, AttributeError) as e:
        print(f"[HYV4 Patch 7] Could not apply gc func compat patch: {e}", flush=True)

_apply_gc_func_compat_patch()

# Patch 2 (tokenizer copy) is applied via HYV4PatchCallback during training.
# Users should add HYV4PatchCallback to their Trainer callbacks.

logger.info(
    "HYV4 patches module loaded. Remember to add HYV4PatchCallback to "
    "your Trainer callbacks for tokenizer file copy on save."
)
