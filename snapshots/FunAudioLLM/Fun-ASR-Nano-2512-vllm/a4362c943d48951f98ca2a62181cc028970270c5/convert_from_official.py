#!/usr/bin/env python3
"""Convert the pinned official Fun-ASR-Nano checkpoint to safetensors."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import torch
from safetensors.torch import save_file


SOURCE_REVISION = "272c57b82523ada6fd87095e955f8e29100979ab"
SOURCE_SHA256 = "55ae0d2fee369f0f11cce0795f6927934ad17cf11b278a7e56a51272074160bb"
EXPECTED_TENSORS = 1261


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(16 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Pinned official model.pt")
    parser.add_argument("output", type=Path, help="Output model.safetensors")
    args = parser.parse_args()

    actual_source_hash = sha256(args.source)
    if actual_source_hash != SOURCE_SHA256:
        raise SystemExit(
            f"source SHA-256 mismatch: expected {SOURCE_SHA256}, got {actual_source_hash}"
        )

    checkpoint = torch.load(args.source, map_location="cpu", weights_only=True)
    state_dict = checkpoint.get("state_dict", checkpoint)
    if len(state_dict) != EXPECTED_TENSORS:
        raise SystemExit(
            f"tensor count mismatch: expected {EXPECTED_TENSORS}, got {len(state_dict)}"
        )
    if not all(isinstance(value, torch.Tensor) for value in state_dict.values()):
        raise SystemExit("checkpoint contains non-tensor state-dict values")

    lora_keys = [key for key in state_dict if "lora" in key.lower()]
    if lora_keys:
        raise SystemExit(f"unexpected LoRA tensors: {lora_keys[:10]}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Keep provenance in MODEL_PROVENANCE.json. safetensors serializes metadata
    # map keys in nondeterministic order, which would make whole-file hashes vary.
    save_file(state_dict, args.output)
    print(f"wrote {args.output}")
    print(f"sha256 {sha256(args.output)}")
    print(f"tensors {len(state_dict)}")


if __name__ == "__main__":
    main()
