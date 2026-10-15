"""Validate complete Step-5 vision and projector outputs.

Only vision/projector tensors are loaded. Text generation is covered separately
by test_vision.py and the TP fixture smoke. No serving stack is required.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time
import types

import torch
from safetensors import safe_open

from model import Step5ForConditionalGeneration, config_from_dict
from vision_encoder import Step5VisionConfig


def load_reference(path):
    # Supply the reference's config import without installing the full HF model.
    # Its encoder mathematics are imported unchanged from the supplied file.
    package = types.ModuleType("_step5_vision_reference")
    package.__path__ = [str(Path(path).parent)]
    sys.modules[package.__name__] = package
    config_module = types.ModuleType(package.__name__ + ".configuration_step3p7")
    config_module.StepRoboticsVisionEncoderConfig = Step5VisionConfig
    sys.modules[config_module.__name__] = config_module
    spec = importlib.util.spec_from_file_location(package.__name__ + ".vision_encoder", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.StepRoboticsVisionEncoder


@torch.inference_mode()
def validate(checkpoint, reference_encoder, device):
    started = time.monotonic()
    root = Path(checkpoint)
    raw = json.loads((root / "config.json").read_text())
    config = config_from_dict(raw)
    # Keep the complete vision config and projection width. Avoid allocating the
    # 92-layer language model for a vision-only numerical comparison.
    scaffold = copy.deepcopy(raw)
    scaffold["text_config"].update(
        num_hidden_layers=0, num_nextn_predict_layers=0, layer_types=[],
        use_moe=False, moe_layer_list=[], vocab_size=16,
    )
    scaffold_config = config_from_dict(scaffold)
    reference_cls = load_reference(reference_encoder)
    with torch.device(device):
        model = Step5ForConditionalGeneration(scaffold_config).eval()
        reference = reference_cls(config.vision_config).to(dtype=torch.bfloat16).eval()
    index = json.loads((root / "model.safetensors.index.json").read_text())["weight_map"]
    keys = sorted(k for k in index if k.startswith(("vision_model.", "vit_large_projector.")))
    state = {}
    for shard in sorted({index[k] for k in keys}):
        with safe_open(root / shard, framework="pt", device="cpu") as handle:
            for key in keys:
                if index[key] == shard:
                    state[key] = handle.get_tensor(key)
    vision_state = {k.removeprefix("vision_model."): v for k, v in state.items() if k.startswith("vision_model.")}
    projector_state = {k.removeprefix("vit_large_projector."): v for k, v in state.items() if k.startswith("vit_large_projector.")}
    model.vision_model.load_state_dict(vision_state, strict=True)
    model.vit_large_projector.load_state_dict(projector_state, strict=True)
    reference.load_state_dict(vision_state, strict=True)
    print(f"Loaded {len(keys)} real vision/projector tensors", flush=True)
    del state, vision_state, projector_state
    torch.manual_seed(1709)
    results = []
    for label, side, batch, expected_tokens in (
        ("overview", config.vision_config.image_size, 1, config.image_token_len),
        ("crops", 504, 2, config.patch_token_len),
    ):
        pixels = torch.randn(batch, 3, side, side, device=device, dtype=torch.bfloat16)
        expected = reference(pixels)
        actual = model.vision_model(pixels)
        encoder_error = float((actual.float() - expected.float()).abs().max())
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        grid = side // config.vision_config.patch_size
        expected = expected.transpose(1, 2).reshape(batch, -1, grid, grid)
        expected = reference.vit_downsampler2(reference.vit_downsampler1(expected))
        expected = model.vit_large_projector(expected.flatten(2).transpose(1, 2))
        actual = model._encode_images(pixels)
        assert actual.shape == (batch, expected_tokens, config.text_config.hidden_size)
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        assert torch.isfinite(actual).all()
        row = dict(case=label, input_shape=list(pixels.shape), output_shape=list(actual.shape),
                   encoder_max_abs_error=encoder_error,
                   projected_max_abs_error=float((actual.float() - expected.float()).abs().max()))
        results.append(row)
        print(json.dumps(row), flush=True)
    torch.cuda.synchronize(device)
    return dict(status="PASS", scope="complete real vision tower and projector; no full language-model generation",
                checkpoint=str(root), config_sha256=hashlib.sha256((root / "config.json").read_bytes()).hexdigest(),
                reference_sha256=hashlib.sha256(Path(reference_encoder).read_bytes()).hexdigest(),
                tensor_count=len(keys), dtype="bfloat16", device=torch.cuda.get_device_name(device),
                cases=results, elapsed_seconds=time.monotonic() - started)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--reference-encoder", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = validate(args.checkpoint, args.reference_encoder, torch.device(args.device))
    Path(args.output).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
