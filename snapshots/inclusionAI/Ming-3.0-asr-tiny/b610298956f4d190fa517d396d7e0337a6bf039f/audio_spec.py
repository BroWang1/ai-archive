# Copyright 2026 SGLang Team
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Model-owned Ming audio geometry; no scheduler, tokenizer, or model imports."""

from dataclasses import dataclass


@dataclass(frozen=True)
class MingAudioSpec:
    """Immutable preprocessing and encoder/projector length contract.

    ``chunk_frames`` is measured before the encoder's stride-two convolution.
    Chunk output lengths must be rounded separately, including the final chunk.
    """

    n_mels: int = 128
    sample_rate: int = 16000
    n_fft: int = 400
    hop_length: int = 160
    chunk_frames: int = 3000
    kernels: tuple[int, ...] = (3,)
    strides: tuple[int, ...] = (2,)
    paddings: tuple[int, ...] = (1,)

    def __post_init__(self):
        if self.n_mels not in (80, 128):
            raise ValueError("Ming audio requires 80 or 128 mel bins")
        if (self.sample_rate, self.n_fft, self.hop_length) != (16000, 400, 160):
            raise ValueError("Ming checkpoints require the 16 kHz Whisper frontend")
        if self.chunk_frames <= 0:
            raise ValueError("chunk_frames must be positive")
        if not (len(self.kernels) == len(self.strides) == len(self.paddings)):
            raise ValueError(
                "audio downsampler kernel/stride/padding lists must have the same length"
            )
        if any(k <= 0 for k in self.kernels) or any(s <= 0 for s in self.strides):
            raise ValueError("audio downsampler kernels and strides must be positive")
        if any(p < 0 for p in self.paddings):
            raise ValueError("audio downsampler paddings must be nonnegative")

    @classmethod
    def from_config(cls, config):
        def get(name, default=None):
            return (
                config.get(name, default)
                if isinstance(config, dict)
                else getattr(config, name, default)
            )

        encoder = get("whisper_encoder_config") or {}
        kernels = tuple(
            get("downsampler_kernel_size_list") or [get("ds_kernel_size", 3)]
        )
        strides = tuple(get("downsampler_stride_list") or [get("ds_stride", 2)])
        paddings = get("downsampler_padding_list")
        spec = cls(
            n_mels=encoder.get("n_mels", get("n_mels", 128)),
            chunk_frames=get("chunk_frames", 3000),
            kernels=kernels,
            strides=strides,
            paddings=tuple(
                paddings if paddings is not None else [k // 2 for k in kernels]
            ),
        )
        context = encoder.get("n_ctx", get("n_audio_ctx", 3000))
        if (spec.chunk_frames + 1) // 2 > context:
            raise ValueError("audio chunk exceeds encoder positional context")
        return spec

    def embedding_length(self, mel_length):
        """Length of one chunk; accepts an integer or an integer tensor."""
        length = (mel_length + 1) // 2
        for kernel, stride, padding in zip(self.kernels, self.strides, self.paddings):
            length = (length + 2 * padding - kernel) // stride + 1
        return length

    def chunks(self, mel_length: int) -> tuple[int, ...]:
        if mel_length <= 0:
            raise ValueError("audio mel length must be positive")
        full, remainder = divmod(mel_length, self.chunk_frames)
        return (self.chunk_frames,) * full + ((remainder,) if remainder else ())

    def token_count(self, mel_length: int) -> int:
        lengths = [self.embedding_length(n) for n in self.chunks(mel_length)]
        if any(n <= 0 for n in lengths):
            raise ValueError("audio chunk is too short for the configured downsampler")
        return sum(lengths)


@dataclass(frozen=True)
class MingAudioMetadata:
    """Versioned model metadata transported opaquely by the generic engine."""

    mel_lengths: tuple[int, ...]
    token_lengths: tuple[int, ...]
    version: int = 1

    def __post_init__(self):
        if self.version != 1:
            raise ValueError(f"Unsupported Ming audio metadata version: {self.version}")
        if not self.mel_lengths or len(self.mel_lengths) != len(self.token_lengths):
            raise ValueError("Ming audio metadata must describe each clip")
        if any(n <= 0 for n in (*self.mel_lengths, *self.token_lengths)):
            raise ValueError("Ming audio lengths must be positive")

    def to_dict(self):
        return {
            "version": self.version,
            "mel_lengths": list(self.mel_lengths),
            "token_lengths": list(self.token_lengths),
        }

    @classmethod
    def from_dict(cls, value):
        return cls(
            tuple(value["mel_lengths"]), tuple(value["token_lengths"]), value["version"]
        )
