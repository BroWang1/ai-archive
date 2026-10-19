# Copyright 2026 Ant Group. All rights reserved.
# Licensed under the Apache License, Version 2.0.
"""Standalone Ming V3 ASR audio tower and checkpoint-compatible projector.

Waveform preprocessing belongs to the feature extractor. This module consumes
raw mel clips, chunks by the trained context, and returns normalized embeddings.
Parameter names are deliberately stable for existing safetensors checkpoints.
"""

import torch
from torch import nn
from torch.nn import functional as F

from .audio_spec import MingAudioSpec
from .modeling_whisper_encoder import WhisperAudioEncoder


class Transpose(nn.Module):
    def forward(self, value):
        return value.transpose(-1, -2)


def build_audio_encoder(config):
    get = (
        config.get
        if isinstance(config, dict)
        else lambda k, d=None: getattr(config, k, d)
    )
    settings = get("whisper_encoder_config")
    if settings is None:
        settings = dict(
            n_mels=get("n_mels", 128),
            n_ctx=get("n_audio_ctx", 3000),
            n_state=get("n_audio_state", 1280),
            n_head=get("n_audio_head", 20),
            n_layer=get("n_audio_layer", 32),
        )
    return WhisperAudioEncoder(**settings)


def build_audio_projector(config, hidden_size, mlp_depth=2):
    spec = MingAudioSpec.from_config(config)
    get = (
        config.get
        if isinstance(config, dict)
        else lambda k, d=None: getattr(config, k, d)
    )
    encoder = get("whisper_encoder_config") or {}
    input_size = encoder.get("n_state", get("n_audio_state", 1280))
    layers = []
    for kernel, stride, padding in zip(spec.kernels, spec.strides, spec.paddings):
        layers.extend(
            [nn.Conv1d(input_size, hidden_size, kernel, stride, padding), nn.GELU()]
        )
        input_size = hidden_size
    layers.extend([Transpose(), nn.Linear(hidden_size, hidden_size)])
    for _ in range(2, mlp_depth):
        layers.extend([nn.GELU(), nn.Linear(hidden_size, hidden_size)])
    return nn.Sequential(*layers)


def encode_audio_clips(clips, encoder, projector, config):
    """Encode each chunk with a fixed batch shape, preserving clip order.

    Padding cannot be removed only after attention: both attention and stacked
    biased convolutions would already have changed valid positions.
    """
    if not clips:
        raise ValueError("Audio clips must not be empty")
    spec = MingAudioSpec.from_config(config)
    parameter = next(projector.parameters())
    chunks = []
    for clip in clips:
        if clip.ndim != 2 or clip.shape[1] != spec.n_mels or not clip.shape[0]:
            raise ValueError("Audio clips require positive [frames, mel_bins] shapes")
        chunks.extend(
            clip.to(device=parameter.device, dtype=parameter.dtype).split(
                spec.chunk_frames
            )
        )
    outputs = []
    # Keep the BF16 GEMM batch shape independent of neighboring requests.
    for chunk in chunks:
        encoded = encoder(chunk.unsqueeze(0))
        projected = projector(encoded.transpose(-1, -2))[0]
        if projected.shape[0] != spec.embedding_length(chunk.shape[0]):
            raise ValueError("Audio projector output violates the length contract")
        outputs.append(projected)
    return F.normalize(torch.cat(outputs), dim=-1)
