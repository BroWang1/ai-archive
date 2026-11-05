#!/usr/bin/env python3
"""Verify the SAE weights and upload everything to the Hugging Face repo.

The repo gets the contents of this directory (model card, LICENSE, per-layer
config.json) plus one sae.safetensors per layer, taken from the training
checkpoints below and renamed on upload; nothing is copied locally.

Usage (token with write access to the ByteDance-Seed org):

    HF_TOKEN=hf_... python3 hf_model_card/upload.py
    python3 hf_model_card/upload.py --check-only   # verify weights, upload nothing
    python3 hf_model_card/upload.py --skip-check   # resume an upload without re-verifying
"""

import argparse
import sys
from pathlib import Path

CARD_DIR = Path(__file__).resolve().parent
REPO_ID = "ByteDance-Seed/Qwen3-30B-A3B-MoE-SAE"

_SUFFIX = "Qwen3-SAE/Qwen3-30B-A3B/dic_1048576/k_100/lr_8e-5_to_8e-6_decay_1200000/aux_2.0/w_5000"
_SOURCES = {
    4: f"Qwen3-30B-L4/{_SUFFIX}/global_step_1300000/weight.safetensors",
    30: f"Qwen3-30B/{_SUFFIX}/global_step_1640000/weight.safetensors",
    46: f"Qwen3-30B-L46/{_SUFFIX}/global_step_1370000/weight.safetensors",
}
# The dev box mounts the user directory at /mnt/hdfs/store, jobs see it as __MERLIN_USER_DIR__.
_SAE_ROOTS = (Path("/mnt/hdfs/__MERLIN_USER_DIR__/SAE"), Path("/mnt/hdfs/store/SAE"))

_EXPECTED = {
    "W_enc": ("float32", [2048, 1048576]),
    "b_enc": ("float32", [1048576]),
    "W_dec": ("float32", [1048576, 2048]),
    "b_dec": ("float32", [2048]),
}


def source_path(layer: int) -> Path:
    for root in _SAE_ROOTS:
        path = root / _SOURCES[layer]
        if path.exists():
            return path
    raise FileNotFoundError(f"layer {layer}: none of {[str(r) for r in _SAE_ROOTS]} holds {_SOURCES[layer]}")


def check_weight(path: Path, layer: int) -> None:
    """Header must hold exactly the four expected tensors, and W_dec rows must have unit norm."""
    import torch
    from safetensors import safe_open

    # Probe with a plain read first: an archived file on the HDFS mount raises OSError here,
    # whereas mmap-ing it in safe_open would take the process down with a bus error.
    with open(path, "rb") as probe:
        probe.read(8)
    with safe_open(str(path), framework="pt", device="cpu") as f:
        keys = set(f.keys())
        assert keys == set(_EXPECTED), f"layer {layer}: tensors {sorted(keys)} != {sorted(_EXPECTED)}"
        for name, (dtype, shape) in _EXPECTED.items():
            tensor = f.get_slice(name)
            assert list(tensor.get_shape()) == shape, f"layer {layer}: {name} shape {tensor.get_shape()} != {shape}"
            assert str(tensor.get_dtype()) == dtype, f"layer {layer}: {name} dtype {tensor.get_dtype()} != {dtype}"
        rows = torch.cat([f.get_slice("W_dec")[:256], f.get_slice("W_dec")[524288:524544]])
    norms = rows.float().norm(dim=-1)
    print(f"layer {layer}: tensors ok, ||W_dec row|| in [{norms.min():.4f}, {norms.max():.4f}] "
          f"(512 sampled rows)")
    assert norms.min() > 0.99 and norms.max() < 1.01, f"layer {layer}: W_dec rows are not unit norm"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="verify the weights and stop")
    parser.add_argument("--skip-check", action="store_true", help="upload without verifying first")
    args = parser.parse_args()

    sources = {layer: source_path(layer) for layer in _SOURCES}
    if not args.skip_check:
        for layer, path in sources.items():
            try:
                check_weight(path, layer)
            except Exception as exc:
                sys.exit(f"layer {layer}: cannot verify {path}: {type(exc).__name__}: {exc}\n"
                         "If this is an Input/output error, the file is still archived; "
                         "wait for the restore to finish and rerun.")
    if args.check_only:
        print("all weights verified, nothing uploaded.")
        return

    from huggingface_hub import HfApi

    api = HfApi()
    user = api.whoami()
    print(f"uploading to {REPO_ID} as {user.get('name')}")
    api.create_repo(REPO_ID, repo_type="model", exist_ok=True)
    api.upload_folder(
        folder_path=str(CARD_DIR),
        repo_id=REPO_ID,
        repo_type="model",
        ignore_patterns=["upload.py", "__pycache__/*"],
        commit_message="Add model card, configs and license",
    )
    for layer, path in sources.items():
        print(f"layer {layer}: uploading {path} -> layer_{layer}/sae.safetensors ...", flush=True)
        api.upload_file(
            path_or_fileobj=str(path),
            path_in_repo=f"layer_{layer}/sae.safetensors",
            repo_id=REPO_ID,
            repo_type="model",
            commit_message=f"Add layer {layer} SAE weights",
        )
    print(f"done: https://huggingface.co/{REPO_ID}")


if __name__ == "__main__":
    main()
