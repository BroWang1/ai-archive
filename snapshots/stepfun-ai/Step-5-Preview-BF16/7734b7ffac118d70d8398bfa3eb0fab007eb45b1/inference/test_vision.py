"""Focused regressions for the standalone Step-5 vision integration.

Run from inference/: python -m pytest -q test_vision.py
"""
import json
from unittest.mock import patch

import pytest
import torch
from safetensors import safe_open
from safetensors.torch import load_file, save_file

from convert import _shard_for, pre_shard
from generate import _load_rank_config, _load_rank_model, load_image_inputs, parse_args, validate_prompt_ids
from model import (
    STEP5_TP_LAYOUT_VERSION, Step5Config, Step5ForCausalLM,
    Step5ForConditionalGeneration, Step5VLConfig, config_from_dict,
)
from vision_encoder import EncoderRope2D, Step5VisionEncoder


def tiny_config(**kwargs):
    text = dict(
        hidden_size=32, intermediate_size=64, num_hidden_layers=1,
        num_nextn_predict_layers=3, vocab_size=64, num_attention_heads=4,
        num_attention_groups=2, head_dim=8, max_position_embeddings=128,
        layer_types=["sliding_attention"] * 4, sliding_window=16, yarn_only_types=["full_attention"],
        use_moe=False, sparse_config={"enabled": False, "num_provider_groups": 2},
        tp_layout_version=STEP5_TP_LAYOUT_VERSION,
    )
    text.update(kwargs.pop("text", {}))
    vision = dict(width=16, layers=2, heads=2, image_size=32, patch_size=4,
                  mlp_ratio=2, use_ln_pre=True, use_ln_post=False)
    vision.update(kwargs.pop("vision", {}))
    return Step5VLConfig(text_config=text, vision_config=vision,
                         image_token_id=70, image_token_len=4, patch_token_len=1, **kwargs)


def initialized_model(config):
    model = Step5ForConditionalGeneration(config)
    # TP linear layers allocate empty checkpoint storage; seed every parameter
    # explicitly because these tests exercise random fixtures, not trained weights.
    with torch.no_grad():
        for name, parameter in model.named_parameters():
            if "norm" in name and name.endswith("weight"):
                parameter.zero_()
            elif name.endswith("weight_scale_inv"):
                parameter.uniform_(0.5, 1.5)
            elif parameter.dtype == torch.float8_e4m3fn:
                parameter.copy_(torch.randn(parameter.shape) * 0.02)
            else:
                parameter.normal_(0, 0.02)
    return model


def test_configuration_and_quantization_roundtrip():
    quant = {"quant_method": "fp8", "modules_to_not_convert": [
        "vision_model.transformer.resblocks.3.attn.q_proj", "model.layers.4.moe.gate",
        "model.layers.88.moe.experts.w13_weight", "model.layers.89.moe.up_proj",
    ]}
    config = tiny_config(quantization_config=quant, tp_size=2)
    assert config.text_config.bf16_expert_layers == [88, 89]
    assert not hasattr(config, "quantization_config")
    assert not hasattr(config.text_config, "quantization_config")
    serialized = json.loads(json.dumps(config.to_dict()))
    restored = config_from_dict(serialized)
    assert restored.model_type == "step5_vl"
    assert restored.architectures == ["Step5ForConditionalGeneration"]
    assert restored.text_config.tp == 2
    assert restored.text_config.num_nextn_predict_layers == 3
    assert len(restored.text_config.to_dict()["layer_types"]) == 4
    assert restored.text_config.bf16_expert_layers == [88, 89]
    assert restored.to_dict()["quantization_config"] == quant
    assert isinstance(config_from_dict(restored.text_config.to_dict()), Step5Config)


def test_vision_shape_rectangular_cls_and_optional_layer_scale():
    config = tiny_config(vision={"use_cls_token": True, "ls_init_value": None}).vision_config
    encoder = Step5VisionEncoder(config).eval()
    output = encoder(torch.randn(2, 3, 16, 24))
    assert output.shape == (2, 24, 16)
    assert torch.isfinite(output).all()
    with pytest.raises(ValueError, match="positive multiples"):
        encoder(torch.randn(1, 3, 15, 16))
    with pytest.raises(ValueError, match="exceeds configured"):
        encoder(torch.randn(1, 3, 36, 32))


def test_rope_coordinates_and_cls_subset():
    rope = EncoderRope2D(8, 8, 8, use_cls_token=True)
    q = torch.ones(1, 1, 7, 8)
    result, _ = rope(q, q, (2, 3))
    assert torch.equal(result[:, :, 0], q[:, :, 0])
    inv = 10000 ** (-torch.arange(0, 4, 2).float() / 4)
    coords = [(0, 0)] + [(x + 1, y + 1) for y in range(2) for x in range(3)]
    angles = torch.stack([torch.cat([x * inv, y * inv]).repeat_interleave(2) for x, y in coords])
    sign = torch.tensor([-1., 1.] * 4)
    expected = angles.cos() + sign * angles.sin()
    torch.testing.assert_close(result[0, 0], expected)


def test_crop_order_and_precomputed_embeddings():
    model = Step5ForConditionalGeneration(tiny_config()).eval()
    overview = torch.randn(2, 4, 32)
    crops = torch.randn(3, 1, 32)
    with patch.object(model, "_encode_images", side_effect=[overview, crops]):
        actual = model.get_multimodal_embeddings(
            pixel_values=torch.zeros(2, 3, 32, 32),
            patch_pixel_values=torch.zeros(3, 3, 16, 16), num_patches=[2, 1],
        )
    expected = torch.cat([crops[0], crops[1], overview[0], crops[2], overview[1]])
    torch.testing.assert_close(actual, expected)
    assert model.get_multimodal_embeddings(image_embeds=overview).shape == (8, 32)
    with pytest.raises(ValueError, match="mutually exclusive"):
        model.get_multimodal_embeddings(pixel_values=torch.empty(1), image_embeds=overview)
    with pytest.raises(ValueError, match="sum\\(num_patches\\)"):
        model.get_multimodal_embeddings(pixel_values=torch.zeros(2, 3, 32, 32), num_patches=[1, 0])
    with pytest.raises(ValueError, match="nonnegative integer"):
        model.get_multimodal_embeddings(pixel_values=torch.zeros(2, 3, 32, 32), num_patches=[0.5, 0])
    with pytest.raises(ValueError, match="overview images"):
        model.get_multimodal_embeddings(num_patches=[0])


def make_checkpoint(path, config):
    path.mkdir()
    model = initialized_model(config)
    state = model.state_dict()
    for i in range(config.text_config.num_hidden_layers,
                   config.text_config.num_hidden_layers + config.text_config.num_nextn_predict_layers):
        state[f"model.layers.{i}.mtp_block.unused.weight"] = torch.ones(1)
    save_file(state, str(path / "model.safetensors"))
    (path / "config.json").write_text(json.dumps(config.to_dict()))
    (path / "model.safetensors.index.json").write_text(json.dumps({
        "weight_map": {key: "model.safetensors" for key in state},
    }))
    return model


def test_conversion_and_strict_loader(tmp_path):
    original = make_checkpoint(tmp_path / "source", tiny_config())
    assert pre_shard(str(tmp_path / "source"), str(tmp_path / "unwritten"), 1, check_only=True) == 0
    assert not (tmp_path / "unwritten").exists()
    assert pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 1) == 0
    directory = str(tmp_path / "converted" / "tp1")
    config = _load_rank_config(directory, 0)
    loaded = _load_rank_model(directory, 0, config, torch.device("cpu"))
    assert isinstance(loaded, Step5ForConditionalGeneration)
    for key, tensor in original.state_dict().items():
        torch.testing.assert_close(loaded.state_dict()[key], tensor)
    with torch.inference_mode():
        pixels = torch.randn(1, 3, 32, 32)
        # Nonpersistent 2D RoPE buffers must be rebuilt after HF meta loading.
        expected_features = original.get_multimodal_embeddings(pixel_values=pixels)
        actual_features = loaded.get_multimodal_embeddings(pixel_values=pixels)
        assert torch.isfinite(actual_features).all()
        torch.testing.assert_close(actual_features, expected_features, rtol=0, atol=0)
    weight = original.vision_model.transformer.resblocks[0].attn.out_proj.weight
    assert _shard_for("vision_model.transformer.resblocks.0.attn.out_proj.weight")(weight, None, 2, 1, config).shape == weight.shape


@pytest.mark.parametrize("multimodal", [False, True])
def test_checkpoint_identity_normalizes_to_step5(tmp_path, multimodal):
    config = tiny_config()
    payload = config.to_dict() if multimodal else config.text_config.to_dict()
    payload["model_type"] = "step4_vl" if multimodal else "step4"
    payload["architectures"] = ["Step4ForConditionalGeneration" if multimodal else "Step4ForCausalLM"]
    payload["auto_map"] = {"AutoConfig": "old_config.Step4Config"}
    if multimodal:
        payload["text_config"]["model_type"] = "step4"
        payload["text_config"]["architectures"] = ["Step4ForCausalLM"]
        payload["text_config"]["auto_map"] = {"AutoConfig": "old_config.Step4Config"}
    restored = config_from_dict(payload)
    assert restored.model_type == ("step5_vl" if multimodal else "step5")
    encoded = json.dumps(restored.to_dict())
    assert "step4" not in encoded.lower()
    restored.save_pretrained(tmp_path)
    reloaded = config_from_dict(json.loads((tmp_path / "config.json").read_text()))
    assert reloaded.to_dict()["auto_map"] == restored.to_dict()["auto_map"]
    assert reloaded.to_dict()["architectures"] == restored.to_dict()["architectures"]
    assert reloaded.get_text_config().num_nextn_predict_layers == 3
    with pytest.raises(ValueError, match="unsupported model_type"):
        config_from_dict(dict(payload, model_type="unrelated_model"))


def test_legacy_checkpoint_conversion_and_shard_loading(tmp_path):
    original = make_checkpoint(tmp_path / "source", tiny_config())
    source_config = tmp_path / "source" / "config.json"
    source_config.write_text(source_config.read_text().replace("step5", "step4").replace("Step5", "Step4"))
    pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 1)
    directory = tmp_path / "converted" / "tp1"
    emitted = (directory / "config-r0.json").read_text()
    assert "step4" not in emitted.lower()
    shard = directory / "model-r0.safetensors"
    state = load_file(str(shard))
    with safe_open(str(shard), framework="pt") as handle:
        metadata = handle.metadata()
    assert metadata["step5_tp_layout"] == STEP5_TP_LAYOUT_VERSION
    assert "step4_tp_layout" not in metadata
    metadata["step4_tp_layout"] = metadata.pop("step5_tp_layout")
    save_file(state, str(shard), metadata=metadata)
    # Existing shards and their per-rank configs must remain loadable together.
    (directory / "config-r0.json").write_text(emitted.replace("step5", "step4").replace("Step5", "Step4"))
    config = _load_rank_config(str(directory), 0)
    loaded = _load_rank_model(str(directory), 0, config, torch.device("cpu"))
    for name, tensor in original.state_dict().items():
        torch.testing.assert_close(loaded.state_dict()[name], tensor, rtol=0, atol=0)
    metadata["step5_tp_layout"] = "incompatible-layout"
    save_file(state, str(shard), metadata=metadata)
    with pytest.raises(ValueError, match="step5_tp_layout metadata"):
        _load_rank_model(str(directory), 0, config, torch.device("cpu"))
    metadata["step5_tp_layout"] = STEP5_TP_LAYOUT_VERSION
    metadata["step4_tp_layout"] = "incompatible-layout"
    save_file(state, str(shard), metadata=metadata)
    with pytest.raises(ValueError, match="step4_tp_layout metadata"):
        _load_rank_model(str(directory), 0, config, torch.device("cpu"))
    metadata.pop("step5_tp_layout")
    metadata.pop("step4_tp_layout")
    save_file(state, str(shard), metadata=metadata)
    with pytest.raises(ValueError, match="missing step5_tp_layout"):
        _load_rank_model(str(directory), 0, config, torch.device("cpu"))


def tiny_moe_config(*, quantized=True):
    return tiny_config(
        text=dict(hidden_size=256, intermediate_size=256, num_hidden_layers=2,
                  layer_types=["sliding_attention"] * 5, num_attention_heads=8,
                  head_dim=32, vocab_size=128, eos_token_id=[127], use_moe=True,
                  moe_layer_list=[0, 1], moe_num_experts=8, moe_top_k=2,
                  moe_intermediate_size=256, share_expert_dim=256),
        quantization_config={"quant_method": "fp8", "modules_to_not_convert": [
            "model.layers.1.moe.experts.w13_weight",
            "model.layers.1.moe.experts.w2_weight",
            "vision_model.transformer.resblocks.0.attn.q_proj",
        ]} if quantized else None,
    )


@pytest.mark.parametrize("quantized", [False, True], ids=["bf16", "mixed_fp8_bf16"])
def test_experts_conversion_and_hf_loading(tmp_path, quantized):
    original = make_checkpoint(tmp_path / "source", tiny_moe_config(quantized=quantized))
    pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 2)
    directory = str(tmp_path / "converted" / "tp2")
    config = _load_rank_config(directory, 0)
    assert config.text_config.bf16_expert_layers == ([1] if quantized else [0, 1])
    loaded = _load_rank_model(directory, 0, config, torch.device("cpu"))
    stored = load_file(str(tmp_path / "converted" / "tp2" / "model-r0.safetensors"))
    for key, actual in loaded.state_dict().items():
        expected = stored[key]
        if key == "lm_head.weight":
            expected = expected[:64]
        assert actual.dtype == expected.dtype, key
        torch.testing.assert_close(actual.float(), expected.float(), rtol=0, atol=0, msg=key)
    if quantized:
        assert loaded.model.layers[0].moe.gate_proj.weight.dtype == torch.float8_e4m3fn
        assert loaded.model.layers[0].moe.gate_proj.weight_scale_inv.dtype == torch.float32
    else:
        assert loaded.model.layers[0].moe.gate_proj.weight.dtype == torch.bfloat16
        assert not any("weight_scale" in key for key in stored)
        assert loaded.model.layers[0].moe.gate_proj.weight_scale_inv is None
    assert loaded.model.layers[1].moe.gate_proj.weight.dtype == torch.bfloat16
    assert loaded.model.layers[1].moe.gate_proj.weight_scale_inv is None
    # Independently verify that only the expert axis was partitioned.
    torch.testing.assert_close(loaded.model.layers[0].moe.gate_proj.weight.float(),
                               original.model.layers[0].moe.gate_proj.weight[:4].float(), rtol=0, atol=0)
    with torch.inference_mode():
        pixels = torch.randn(1, 3, 32, 32)
        torch.testing.assert_close(loaded.get_multimodal_embeddings(pixel_values=pixels),
                                   original.get_multimodal_embeddings(pixel_values=pixels), rtol=0, atol=0)


@pytest.mark.parametrize("quantization", [None, {}])
def test_unquantized_moe_configuration_roundtrip(quantization):
    raw = tiny_moe_config(quantized=False).to_dict()
    raw["text_config"]["quantization_config"] = quantization
    # Derived fields from another checkpoint must not override its quantization metadata.
    raw["text_config"]["bf16_expert_layers"] = []
    config = config_from_dict(raw)
    for restored in (config, config_from_dict(config.to_dict()),
                     config_from_dict(config.text_config.to_dict())):
        text = restored.get_text_config()
        assert text.bf16_expert_layers == [0, 1]
        assert not any(text.is_fp8_expert_layer(i) for i in range(2))
        assert not hasattr(text, "quantization_config")


def test_unsupported_expert_quantization_is_rejected():
    with pytest.raises(ValueError, match="quant_method='fp8'"):
        tiny_config(quantization_config={"quant_method": "int8"})


@pytest.mark.parametrize("corruption", ["missing", "unexpected", "shape", "rank"])
def test_loader_rejects_incomplete_or_wrong_rank_shards(tmp_path, corruption):
    make_checkpoint(tmp_path / "source", tiny_config())
    pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 1)
    directory = tmp_path / "converted" / "tp1"
    shard = directory / "model-r0.safetensors"
    with safe_open(str(shard), framework="pt") as handle:
        metadata = handle.metadata()
    state = load_file(str(shard))
    key = "vision_model.conv1.weight"
    if corruption == "missing":
        del state[key]
    elif corruption == "unexpected":
        state["vision_model.unexpected.weight"] = torch.ones(1)
    elif corruption == "shape":
        state[key] = state[key][:1].clone()
    else:
        metadata["rank"] = "1"
    save_file(state, str(shard), metadata=metadata)
    config = _load_rank_config(str(directory), 0)
    with patch.object(Step5ForConditionalGeneration, "from_pretrained") as load:
        with pytest.raises(ValueError, match="key mismatch|shape|rank metadata"):
            _load_rank_model(str(directory), 0, config, torch.device("cpu"))
        load.assert_not_called()


def test_resume_rejects_old_text_only_shard(tmp_path):
    make_checkpoint(tmp_path / "source", tiny_config())
    pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 2)
    # A matching shard must resume successfully when converting from a TP=1 config.
    assert pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 2, start_rank=1) == 0
    shard = tmp_path / "converted" / "tp2" / "model-r0.safetensors"
    with safe_open(str(shard), framework="pt") as handle:
        metadata = handle.metadata()
    state = {key: tensor for key, tensor in load_file(str(shard)).items()
             if not key.startswith(("vision_model.", "vit_large_projector."))}
    save_file(state, str(shard), metadata=metadata)
    with patch("convert._build_rank_state") as build:
        with pytest.raises(ValueError, match="shard key mismatch"):
            pre_shard(str(tmp_path / "source"), str(tmp_path / "converted"), 2, start_rank=1)
        build.assert_not_called()


def test_cli_inputs(tmp_path):
    path = tmp_path / "images.safetensors"
    save_file({"image_embeds": torch.randn(4, 32)}, str(path))
    result = load_image_inputs(str(path), tiny_config())
    assert result["image_embeds"].shape == (4, 32)
    with pytest.raises(ValueError, match="step5_vl"):
        load_image_inputs(str(path), tiny_config().text_config)
    with pytest.raises(SystemExit):
        parse_args(["--tp-dir", ".", "--prompt", "test", "--image-inputs", str(path)])
    limits = dict(vocab_size=64, max_position_embeddings=128, max_new_tokens=1)
    validate_prompt_ids([5, 70, 6], image_token_id=70, **limits)
    with pytest.raises(ValueError, match="outside vocabulary"):
        validate_prompt_ids([5, 70, 6], **limits)
    with pytest.raises(ValueError, match="outside vocabulary"):
        validate_prompt_ids([5, 71, 6], image_token_id=70, **limits)


@pytest.mark.skipif(not torch.cuda.is_available(), reason="CUDA required for packed text inference")
def test_cuda_prefill_decode_text_parity_and_single_vision_call():
    torch.manual_seed(11)
    device = torch.device("cuda")
    config = tiny_config()
    model = initialized_model(config).to(device).eval()
    text = Step5ForCausalLM(config.text_config).to(device).eval()
    text.load_state_dict({key: value for key, value in model.state_dict().items()
                          if key.startswith(("model.", "lm_head."))}, strict=True)
    pixels = torch.randn(1, 3, 32, 32, device=device)
    ids = torch.tensor([5, 70, 70, 70, 70, 6, 7], device=device)
    lengths = torch.tensor([7], dtype=torch.int32, device=device)
    with torch.inference_mode():
        cache_a = model.allocate_cache(batch=1, max_tokens=16, device=device)
        cache_b = text.allocate_cache(batch=1, max_tokens=16, device=device)
        features = model.get_multimodal_embeddings(pixel_values=pixels)
        embeds = model.model.embed_tokens(ids.masked_fill(ids == 70, 0))
        embeds[ids == 70] = features
        actual = model(ids, cache_a, lengths, pixel_values=pixels).logits
        assert torch.isfinite(actual).all()
        expected = text(ids, cache_b, lengths, inputs_embeds=embeds).logits
        torch.testing.assert_close(actual, expected, rtol=0, atol=0)
        token = actual.argmax(-1)
        one = torch.ones(1, dtype=torch.int32, device=device)
        torch.testing.assert_close(model(token, cache_a, one, is_decode=True).logits,
                                   text(token, cache_b, one, is_decode=True).logits, rtol=0, atol=0)
        before = cache_a.lengths.clone()
        with pytest.raises(ValueError, match="placeholders"):
            model(ids, cache_a, lengths, image_embeds=features[:1])
        assert torch.equal(cache_a.lengths, before)
        with pytest.raises(ValueError, match="only accepted during prefill"):
            model(token, cache_a, one, is_decode=True, pixel_values=pixels)
        with pytest.raises(ValueError, match="require image inputs"):
            model(ids, cache_a, lengths)
        with patch.object(model.vision_model, "forward", wraps=model.vision_model.forward) as encode:
            output = model.generate_greedy([ids.tolist(), [8, 9]], max_new_tokens=3,
                                          device=device, eos_token_ids={-1}, pixel_values=pixels)
            assert [len(row) for row in output] == [3, 3]
            assert encode.call_count == 1
        assert text.generate_greedy([[5, 6]], max_new_tokens=2, device=device, eos_token_ids={-1}) == model.generate_greedy([[5, 6]], max_new_tokens=2, device=device, eos_token_ids={-1})
