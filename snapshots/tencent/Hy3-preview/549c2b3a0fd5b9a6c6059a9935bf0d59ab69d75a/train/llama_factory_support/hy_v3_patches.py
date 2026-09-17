"""
HYV3 monkey-patches for LLaMA Factory + DeepSpeed ZeRO-3 training.

This module applies all necessary runtime patches so that HYV3 (MoE)
can be trained correctly under LLaMA Factory with DeepSpeed ZeRO-3.

Usage:
    Import this module **before** calling `llamafactory-cli train`:

        import hy_v3_patches          # applies patches on import
        # ... then start training

    Or add to the LLaMA Factory YAML via a custom entry-point wrapper.

Patches applied:
    1. ZeRO-3 buffer loading (e_score_correction_bias etc.)
       Key renaming + expert fusing is now done offline by convert_ckpt_to_outer.py
    2. Router forward dtype fix (MoE router gate dtype alignment for ZeRO-3)
    3. gradient_checkpointing   (use_reentrant=True for ZeRO-3)
    4. Tokenizer file copy      (CustomSaveCallback)
    5. (Removed) -- was per-expert ModuleList, now using native 3D Parameters
    6. Save-time reverse key rename + 3D -> per-expert unfuse
"""

import os
import re
import logging
import shutil
from typing import Optional

import torch
import torch.nn as _nn
import torch.nn.functional as _F

logger = logging.getLogger(__name__)

# ============================================================================
# Patch 1: Buffer loading for ZeRO-3
#
# The checkpoint is expected to be in outer format (pre-converted by
# convert_ckpt_to_outer.py). Key renaming and expert fusing are no longer
# needed at load time.
#
# However, ZeRO-3's _load_state_dict_into_zero3_model only handles
# named_parameters, not named_buffers (e.g. e_score_correction_bias).
# We still need to manually load buffers from the state_dict.
# ============================================================================


def _apply_buffer_loading_patch():
    """Patch the DeepSpeed ZeRO-3 state_dict loader to manually load buffers.

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
        # Load parameters via original ZeRO-3 loader
        result = _orig_load_zero3(model_to_load, state_dict, *args, **kwargs)

        # Manually load buffers (e.g. e_score_correction_bias) from state_dict.
        # ZeRO-3's loader only handles named_parameters, not named_buffers.
        buffers_loaded = 0
        for name, buf in model_to_load.named_buffers():
            if name in state_dict:
                src_tensor = state_dict[name]
                if isinstance(src_tensor, torch.Tensor):
                    buf.data.copy_(src_tensor.to(buf.dtype))
                    buffers_loaded += 1
                    if isinstance(result, tuple) and len(result) >= 2:
                        if isinstance(result[1], set):
                            result[1].discard(name)
        if buffers_loaded > 0:
            logger.info(
                "HYV3 Patch 1: Manually loaded %d buffers into model.",
                buffers_loaded
            )

        return result

    _ds_mod._load_state_dict_into_zero3_model = _patched_load_zero3
    _mu_mod._load_state_dict_into_zero3_model = _patched_load_zero3
    logger.info(
        "HYV3 patch applied: ZeRO-3 buffer loading for e_score_correction_bias."
    )

# ============================================================================
# Patch 2: Router forward dtype alignment for ZeRO-3
#
# The HYV3 MoE HYV3TopKRouter.forward() calls F.linear with .float().
# Under DeepSpeed ZeRO-3, F.linear is replaced by zero3_linear_wrap which
# internally does input.matmul(weight.t()) WITHOUT aligning dtypes.
# When ZeRO-3 stores the gate weight in bf16, the fp32 input causes a
# dtype mismatch RuntimeError.
#
# Fix: monkey-patch HYV3TopKRouter.forward to cast input to
# self.weight.dtype before F.linear, then cast the output back to float32.
# ============================================================================

_router_patch_applied = False

def _apply_router_dtype_patch():
    """Monkey-patch HYV3TopKRouter.forward to align gate input dtype with weight dtype."""
    global _router_patch_applied
    if _router_patch_applied:
        return

    try:
        from transformers.models.hy_v3.modeling_hy_v3 import HYV3TopKRouter
    except ImportError:
        try:
            from transformers.hy_v3.modeling_hy_v3 import HYV3TopKRouter
        except ImportError:
            logger.warning(
                "Could not import HYV3TopKRouter; "
                "router dtype patch NOT applied."
            )
            return

    def _patched_router_forward(
        self,
        hidden_states: torch.Tensor,
        e_score_correction_bias: torch.Tensor,
    ) -> tuple:
        hidden_states = hidden_states.reshape(-1, self.hidden_dim)
        # Cast input to match weight dtype (bf16 under ZeRO-3)
        # instead of hard-coding float32, to avoid matmul dtype mismatch.
        weight_dtype = self.weight.dtype
        router_logits = _F.linear(hidden_states.to(weight_dtype), self.weight.to(weight_dtype))
        # Cast back to float32 for numerically stable sigmoid
        router_logits = router_logits.to(torch.float32)
        routing_weights = torch.sigmoid(router_logits)

        scores_for_choice = routing_weights + e_score_correction_bias
        _, top_k_index = torch.topk(scores_for_choice, self.top_k, dim=-1, sorted=False)
        top_k_weights = routing_weights.gather(1, top_k_index)

        top_k_weights = top_k_weights / (top_k_weights.sum(dim=-1, keepdim=True) + 1e-20)
        top_k_weights = top_k_weights * self.router_scaling_factor

        return router_logits, top_k_weights, top_k_index

    HYV3TopKRouter.forward = _patched_router_forward
    _router_patch_applied = True
    logger.info("HYV3 patch applied: HYV3TopKRouter.forward dtype alignment for ZeRO-3.")

# ============================================================================
# Patch 3: gradient_checkpointing use_reentrant=True
#
# PyTorch's torch.utils.checkpoint with use_reentrant=False (the default
# in transformers) performs strict metadata checks on recomputed tensors.
# Under ZeRO-3, parameters are all-gathered during the first forward pass
# but may be partitioned back when the checkpoint recomputes, causing a
# CheckpointError.  Setting use_reentrant=True avoids this.
#
# This is applied via a Trainer callback that modifies training_args
# before training starts.
# ============================================================================

# ============================================================================
# Patch 4: Tokenizer file copy callback
#
# Ensures each checkpoint directory is self-contained for inference by
# copying all tokenizer-related files from the original tokenizer path.
# ============================================================================

# Tokenizer files that should be copied to each checkpoint
_TOKENIZER_FILES = [
    "generation_config.json",
    "hy.tiktoken",
    "tokenizer_config.json",
    "tokenization_hy.py",
    "tokenizer.json",
    "special_tokens_map.json",
    "chat_template.jinja",
]

def _copy_tokenizer_to_checkpoint(tokenizer_dir: str, checkpoint_dir: str):
    """Copy tokenizer files from tokenizer_dir to checkpoint_dir."""
    for fname in _TOKENIZER_FILES:
        src = os.path.join(tokenizer_dir, fname)
        if os.path.isfile(src):
            shutil.copy(src, os.path.join(checkpoint_dir, fname))

# ============================================================================
# Patch 6: Save-time reverse key rename + 3D -> per-expert unfuse
#
# When saving checkpoints, the model state_dict uses:
#   - 3D fused experts (experts.gate_up_proj, experts.down_proj)
#   - New naming (mlp.gate, mlp.e_score_correction_bias, mlp.shared_experts)
#
# We need to reverse both for old checkpoint compatibility:
#   - mlp.gate.           -> mlp.router.gate.
#   - mlp.e_score_correction_bias -> mlp.expert_bias
#   - mlp.shared_experts. -> mlp.shared_mlp.
#   - experts.gate_up_proj -> experts.{N}.gate_proj.weight + experts.{N}.up_proj.weight
#   - experts.down_proj    -> experts.{N}.down_proj.weight
# ============================================================================

# Reverse mapping: new model name -> old checkpoint name
_SAVE_KEY_RENAMES = [
    ("mlp.gate.", "mlp.router.gate."),
    ("mlp.e_score_correction_bias", "mlp.expert_bias"),
    ("mlp.shared_experts.", "mlp.shared_mlp."),
]

# Regex to match fused 3D expert keys
_FUSED_EXPERT_KEY_RE = re.compile(
    r"^(.*\.mlp\.experts\.)(gate_up_proj|down_proj)$"
)

_save_patch_applied = False

def _apply_save_reverse_rename_patch():
    """Monkey-patch save_pretrained to reverse-rename keys and unfuse 3D experts."""
    global _save_patch_applied
    if _save_patch_applied:
        return

    try:
        from transformers.models.hy_v3.modeling_hy_v3 import HYV3ForCausalLM
    except ImportError:
        try:
            from transformers.hy_v3.modeling_hy_v3 import HYV3ForCausalLM
        except ImportError:
            logger.warning(
                "Could not import HYV3ForCausalLM; "
                "save reverse rename patch NOT applied."
            )
            return

    _orig_save_pretrained = HYV3ForCausalLM.save_pretrained

    def _patched_save_pretrained(self, *args, **kwargs):
        state_dict = kwargs.get("state_dict", None)
        if state_dict is not None:
            reversed_sd = {}

            for k, v in state_dict.items():
                new_k = k
                # Apply simple key renames
                for new_sub, old_sub in _SAVE_KEY_RENAMES:
                    if new_sub in new_k:
                        new_k = new_k.replace(new_sub, old_sub)
                        break

                # Check if this is a fused 3D expert key
                m = _FUSED_EXPERT_KEY_RE.match(new_k)
                if m:
                    prefix = m.group(1)  # e.g. "model.layers.1.mlp.experts."
                    proj_type = m.group(2)  # "gate_up_proj" or "down_proj"

                    if proj_type == "gate_up_proj":
                        # v shape: [num_experts, 2*intermediate, hidden]
                        num_experts = v.shape[0]
                        intermediate = v.shape[1] // 2
                        for i in range(num_experts):
                            gate = v[i, :intermediate, :]
                            up = v[i, intermediate:, :]
                            reversed_sd[f"{prefix}{i}.gate_proj.weight"] = gate
                            reversed_sd[f"{prefix}{i}.up_proj.weight"] = up
                    elif proj_type == "down_proj":
                        # v shape: [num_experts, hidden, intermediate]
                        num_experts = v.shape[0]
                        for i in range(num_experts):
                            reversed_sd[f"{prefix}{i}.down_proj.weight"] = v[i]
                else:
                    reversed_sd[new_k] = v

            kwargs["state_dict"] = reversed_sd
            logger.info(
                "HYV3 Patch 6: Reverse-renamed and unfused %d -> %d "
                "state_dict keys for old checkpoint compatibility.",
                len(state_dict), len(reversed_sd)
            )
        return _orig_save_pretrained(self, *args, **kwargs)

    HYV3ForCausalLM.save_pretrained = _patched_save_pretrained

    _save_patch_applied = True
    logger.info(
        "HYV3 patch applied: save-time reverse key rename + "
        "3D -> per-expert unfuse for old ckpt compatibility."
    )

# ============================================================================
# LLaMA Factory Callback: integrates patches 3, 4 into the training loop
# ============================================================================

try:
    from transformers import TrainerCallback
    from transformers.trainer_utils import PREFIX_CHECKPOINT_DIR

    class HYV3PatchCallback(TrainerCallback):
        """
        LLaMA Factory compatible callback that applies HYV3-specific patches.

        Add to your YAML or pass to Trainer:
            callbacks: [hy_v3_patches.HYV3PatchCallback]
        """

        def __init__(self, tokenizer_dir: Optional[str] = None):
            """
            Args:
                tokenizer_dir: Path to the original tokenizer directory.
                    If None, will try to use model_name_or_path from training args.
            """
            self._tokenizer_dir = tokenizer_dir

        def on_train_begin(self, args, state, control, **kwargs):
            # --- Patch 3: gradient_checkpointing use_reentrant ---
            if getattr(args, "gradient_checkpointing", False) and getattr(args, "deepspeed", None):
                if not hasattr(args, "gradient_checkpointing_kwargs") or not args.gradient_checkpointing_kwargs:
                    args.gradient_checkpointing_kwargs = {"use_reentrant": True}
                elif "use_reentrant" not in args.gradient_checkpointing_kwargs:
                    args.gradient_checkpointing_kwargs["use_reentrant"] = True
                logger.info("HYV3 patch applied: gradient_checkpointing use_reentrant=True.")

            return control

        def on_save(self, args, state, control, **kwargs):
            # --- Patch 4: Copy tokenizer files ---
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
                    "HYV3: Copied tokenizer files from %s to %s",
                    tokenizer_dir, checkpoint_dir
                )

            return control

except ImportError:
    logger.warning(
        "transformers not available; HYV3PatchCallback not defined."
    )

# ============================================================================
# Auto-apply patches on import
# ============================================================================

# Patch 1: ZeRO-3 buffer loading (key rename + fuse now done by preprocessing)
_apply_buffer_loading_patch()

# Patch 2: Router dtype fix
_apply_router_dtype_patch()

# Patch 6: Save-time reverse key rename + 3D -> per-expert unfuse
_apply_save_reverse_rename_patch()

# Patches 3, 4 are applied via HYV3PatchCallback during training.
# Users should add HYV3PatchCallback to their Trainer callbacks.

logger.info(
    "HYV3 patches module loaded. Remember to add HYV3PatchCallback to "
    "your Trainer callbacks for full compatibility."
)
