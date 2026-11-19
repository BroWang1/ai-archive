"""
LLaMA Factory training entry-point wrapper.

This script:
  1. Registers the chat template
  2. Applies all monkey-patches (checkpoint key rename, dtype fix, etc.)
  3. Injects HYV4PatchCallback into the training loop
  4. Calls run_exp() to start LLaMA Factory training

"""

import sys
import os

# Add current directory to path so patches can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Step 1: Register HYV4 template (must be before training starts)
import hy_v4_template  # noqa: F401

# Step 2: Apply checkpoint key rename patch (must be before model loading)
import hy_v4_patches  # noqa: F401

# Step 3: Inject HYV4PatchCallback into LLaMA Factory's training flow
from llamafactory.train.sft.workflow import run_sft as _orig_run_sft


def _patched_run_sft(
    model_args, data_args, training_args,
    finetuning_args, generating_args, callbacks=None
):
    """Wrap run_sft to inject HYV4PatchCallback."""
    if callbacks is None:
        callbacks = []

    # Determine tokenizer directory for the save callback
    tokenizer_dir = getattr(model_args, "model_name_or_path", None)
    callbacks.append(
        hy_v4_patches.HYV4PatchCallback(tokenizer_dir=tokenizer_dir)
    )

    return _orig_run_sft(
        model_args, data_args, training_args,
        finetuning_args, generating_args,
        callbacks=callbacks
    )


# Monkey-patch the SFT workflow
import llamafactory.train.sft.workflow as _sft_wf
_sft_wf.run_sft = _patched_run_sft


def _apply_safe_pin_memory_patch():
    """Make CUDA pin_memory fault-tolerant for DeepSpeed ZeRO-3.

    DeepSpeed ZeRO-3 calls get_accelerator().pin_memory(tensor) during
    _create_param_groups_fp16_flat_cpu_memory to create pinned (page-locked)
    CPU buffers for parameter offloading.  This call is hard-coded and NOT
    controlled by the config's ``pin_memory: false`` setting.

    On some nodes, pin_memory() can sporadically fail with
    ``CUDA error: invalid argument`` due to transient driver/cgroup issues.
    This patch wraps the CUDA accelerator's pin_memory method so that if
    the call fails, it falls back to returning the original (unpinned)
    tensor instead of crashing the entire training job.
    """
    try:
        from deepspeed.accelerator.cuda_accelerator import CUDA_Accelerator

        _orig_pin_memory = CUDA_Accelerator.pin_memory

        def _safe_pin_memory(self, tensor):
            try:
                return _orig_pin_memory(self, tensor)
            except Exception as e:
                import torch
                rank = torch.distributed.get_rank() if torch.distributed.is_initialized() else 0
                print(f"[HYV4 Patch] WARNING: pin_memory() failed on rank {rank}: {e}. "
                      f"Falling back to unpinned CPU tensor.", flush=True)
                return tensor

        CUDA_Accelerator.pin_memory = _safe_pin_memory
        print("[HYV4 Patch] Patched CUDA_Accelerator.pin_memory with "
              "fault-tolerant fallback.", flush=True)
    except ImportError:
        pass


def _apply_dtype_safe_linear_patch():
    """Fix dtype mismatch in DeepSpeed ZeRO-3 linear wrapper.

    Under ZeRO-3, the all-gathered weight may be in a different dtype than
    the input activation (e.g. ViT outputs bf16 but lm_head weight is fp32).
    This patch ensures input is cast to match weight dtype before F.linear.
    """
    import torch.nn.functional as _F
    _orig_F_linear = _F.linear

    def _dtype_safe_linear(input, weight, bias=None):
        if input.dtype != weight.dtype:
            input = input.to(weight.dtype)
        return _orig_F_linear(input, weight, bias)

    _F.linear = _dtype_safe_linear
    print("[HYV4 Patch] Applied dtype-safe F.linear wrapper for ZeRO-3.", flush=True)


def _apply_skip_grad_norm_patch():
    """Skip grad norm computation for DeepSpeed ZeRO-3 + CPU offload.

    Under ZeRO-3 + CPU offload, DeepSpeed's complete_grad_norm_calculation
    all-gathers every gradient on CPU and does an ALLREDUCE to compute the
    global L2 norm. For a 770B model this is extremely slow and can cause
    NCCL timeout/deadlock at optimizer step.

    When max_grad_norm=0 (no clipping), we fully skip the norm computation
    by patching _get_norm_groups to return 0.0 immediately.
    """
    import torch
    try:
        from deepspeed.runtime.zero.stage3 import DeepSpeedZeroOptimizer_Stage3

        def _skip_get_norm_groups(self):
            return [torch.tensor(0.0)]

        DeepSpeedZeroOptimizer_Stage3._get_norm_groups = _skip_get_norm_groups
        print("[HYV4 Patch] Patched DeepSpeedZeroOptimizer_Stage3._get_norm_groups "
              "to skip grad norm computation (max_grad_norm=0).", flush=True)
    except ImportError:
        # DeepSpeed not available, skip
        pass


def _apply_empty_cache_before_save_patch():
    """Clear GPU cache before saving checkpoints to avoid OOM.

    Under ZeRO-3 with large models, GPU memory is extremely tight during
    training. When the Trainer tries to save a checkpoint, DeepSpeed needs
    to perform NCCL all_reduce operations which require GPU memory allocation.
    If the PyTorch CUDA cache is holding stale memory, this allocation can
    fail with OOM.

    This patch wraps both Trainer._save_checkpoint and Trainer.save_model
    to call torch.cuda.empty_cache() before the actual save, ensuring enough
    GPU memory is available for DeepSpeed's NCCL operations.
    """
    import torch
    try:
        from transformers import Trainer

        # Patch 1: Clear cache before _save_checkpoint (outer entry point)
        _orig_save_checkpoint = Trainer._save_checkpoint

        def _save_checkpoint_with_cache_clear(self, model, trial, **kwargs):
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return _orig_save_checkpoint(self, model, trial, **kwargs)

        Trainer._save_checkpoint = _save_checkpoint_with_cache_clear
        print("[HYV4 Patch] Patched Trainer._save_checkpoint to clear CUDA cache before save.", flush=True)

        # Patch 2: Clear cache inside save_model, right before DeepSpeed's
        # save_checkpoint call. When stage3_gather_16bit_weights_on_model_save
        # is False, save_model catches ValueError and falls back to
        # self.model_wrapped.save_checkpoint(output_dir). The NCCL all_reduce
        # inside that call can OOM if GPU cache is not cleared first.
        _orig_save_model = Trainer.save_model

        def _save_model_with_cache_clear(self, output_dir=None, _internal_call=False):
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            return _orig_save_model(self, output_dir=output_dir, _internal_call=_internal_call)

        Trainer.save_model = _save_model_with_cache_clear
        print("[HYV4 Patch] Patched Trainer.save_model to clear CUDA cache before save.", flush=True)

    except ImportError:
        pass


def main():
    """Entry point: called by torchrun in each worker process.

    Since train_lf.sh launches us via torchrun directly, all patches
    (template registration, checkpoint key rename, SFT callback injection)
    are already applied in this process.  We just call run_exp() to start
    training — no need to go through the CLI launcher.
    """
    # Apply grad norm skip patch for DeepSpeed ZeRO-3 full SFT.
    # This must be done before Trainer creates the DeepSpeed engine.
    # The patch is safe even when not using DeepSpeed (it's a no-op if
    # DeepSpeed is not imported or ZeRO-3 is not used).
    # Make pin_memory fault-tolerant to handle sporadic CUDA errors
    # on certain nodes during DeepSpeed ZeRO-3 initialization.
    # Must be applied before DeepSpeed engine is created.
    _apply_safe_pin_memory_patch()

    _apply_skip_grad_norm_patch()

    # Apply dtype-safe linear patch for VL models under ZeRO-3.
    # This fixes dtype mismatch between ViT outputs and linear layer weights.
    _apply_dtype_safe_linear_patch()

    # Clear GPU cache before checkpoint save to prevent OOM during
    # DeepSpeed's NCCL all_reduce in save_checkpoint.
    _apply_empty_cache_before_save_patch()

    from llamafactory.train.tuner import run_exp
    run_exp()


if __name__ == "__main__":
    main()
