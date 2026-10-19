# Adapted from OpenAI Whisper: https://github.com/openai/whisper
# MIT License
#
# Copyright (c) 2022 OpenAI
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Local Whisper-compatible audio encoder used by Ming audio models."""

import math

import torch
import torch.nn.functional as F
from torch import Tensor, nn


class _WhisperLayerNorm(nn.LayerNorm):
    def forward(self, x: Tensor) -> Tensor:
        return F.layer_norm(
            x.float(),
            self.normalized_shape,
            self.weight.float() if self.weight is not None else None,
            self.bias.float() if self.bias is not None else None,
            self.eps,
        ).to(dtype=x.dtype)


class _WhisperLinear(nn.Linear):
    def forward(self, x: Tensor) -> Tensor:
        return F.linear(
            x,
            self.weight.to(dtype=x.dtype),
            None if self.bias is None else self.bias.to(dtype=x.dtype),
        )


class _WhisperConv1d(nn.Conv1d):
    def _conv_forward(self, x: Tensor, weight: Tensor, bias: Tensor | None) -> Tensor:
        return super()._conv_forward(
            x,
            weight.to(dtype=x.dtype),
            None if bias is None else bias.to(dtype=x.dtype),
        )


def _sinusoids(length: int, channels: int, max_timescale: int = 10000) -> Tensor:
    assert channels % 2 == 0
    log_timescale_increment = math.log(max_timescale) / (channels // 2 - 1)
    inv_timescales = torch.exp(-log_timescale_increment * torch.arange(channels // 2))
    scaled_time = torch.arange(length)[:, None] * inv_timescales[None, :]
    return torch.cat([torch.sin(scaled_time), torch.cos(scaled_time)], dim=1)


class _WhisperMultiHeadAttention(nn.Module):
    def __init__(self, n_state: int, n_head: int):
        super().__init__()
        self.n_head = n_head
        self.query = _WhisperLinear(n_state, n_state)
        self.key = _WhisperLinear(n_state, n_state, bias=False)
        self.value = _WhisperLinear(n_state, n_state)
        self.out = _WhisperLinear(n_state, n_state)

    def forward(self, x: Tensor) -> Tensor:
        batch_size, sequence_length, n_state = x.shape
        head_dim = n_state // self.n_head
        q = self.query(x).view(batch_size, sequence_length, self.n_head, head_dim)
        k = self.key(x).view(batch_size, sequence_length, self.n_head, head_dim)
        v = self.value(x).view(batch_size, sequence_length, self.n_head, head_dim)
        q = q.permute(0, 2, 1, 3)
        k = k.permute(0, 2, 1, 3)
        v = v.permute(0, 2, 1, 3)
        x = F.scaled_dot_product_attention(q, k, v)
        x = x.permute(0, 2, 1, 3).flatten(start_dim=2)
        return self.out(x)


class _WhisperResidualAttentionBlock(nn.Module):
    def __init__(self, n_state: int, n_head: int):
        super().__init__()
        self.attn = _WhisperMultiHeadAttention(n_state, n_head)
        self.attn_ln = _WhisperLayerNorm(n_state)
        self.mlp = nn.Sequential(
            _WhisperLinear(n_state, n_state * 4),
            nn.GELU(),
            _WhisperLinear(n_state * 4, n_state),
        )
        self.mlp_ln = _WhisperLayerNorm(n_state)

    def forward(self, x: Tensor) -> Tensor:
        x = x + self.attn(self.attn_ln(x))
        return x + self.mlp(self.mlp_ln(x))


class WhisperAudioEncoder(nn.Module):
    """Whisper encoder with Ming's variable-length ``[B, T, n_mels]`` input."""

    def __init__(
        self, n_mels: int, n_ctx: int, n_state: int, n_head: int, n_layer: int
    ):
        super().__init__()
        self.conv1 = _WhisperConv1d(n_mels, n_state, kernel_size=3, padding=1)
        self.conv2 = _WhisperConv1d(
            n_state, n_state, kernel_size=3, stride=2, padding=1
        )
        self.register_buffer("positional_embedding", _sinusoids(n_ctx, n_state))
        self.blocks = nn.ModuleList(
            [_WhisperResidualAttentionBlock(n_state, n_head) for _ in range(n_layer)]
        )
        self.ln_post = _WhisperLayerNorm(n_state)
        self.audio_emb_dim = n_state

    def forward(self, x: Tensor) -> Tensor:
        """Encode a batch of mel spectrograms shaped ``[batch, frames, mels]``."""
        x = x.transpose(1, 2)
        x = F.gelu(self.conv1(x))
        x = F.gelu(self.conv2(x))
        x = x.permute(0, 2, 1)
        positional_embedding = self.positional_embedding[: x.shape[1], :]
        assert x.shape[1:] == positional_embedding.shape, "incorrect audio shape"
        x = (x + positional_embedding).to(dtype=x.dtype)

        for block in self.blocks:
            x = block(x)

        return self.ln_post(x)
