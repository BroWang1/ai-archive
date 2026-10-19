# Copyright 2026 Ant Group. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
"""Serializable Ming V3 ASR frontend, independent of the serving engine.

The numerical frontend is adapted from SGLang's ``bailing_audio_frontend.py``
(Apache-2.0), which implements the OpenAI Whisper Slaney-normalized mel bank.
"""

import math
from functools import lru_cache
from numbers import Integral, Real

import numpy as np
import torch
from transformers.feature_extraction_sequence_utils import SequenceFeatureExtractor
from transformers.feature_extraction_utils import BatchFeature

from .audio_spec import MingAudioSpec


@lru_cache(maxsize=2)
def _mel_filters(n_mels):
    frequencies = torch.linspace(0, 8000, 201, dtype=torch.float64)
    linear_scale = 200.0 / 3.0
    log_start = 1000.0 / linear_scale
    log_step = math.log(6.4) / 27.0
    mel_max = log_start + math.log(8.0) / log_step
    mels = torch.linspace(0, mel_max, n_mels + 2, dtype=torch.float64)
    centers = linear_scale * mels
    logarithmic = mels >= log_start
    centers[logarithmic] = 1000.0 * torch.exp(
        log_step * (mels[logarithmic] - log_start)
    )
    widths = centers[1:] - centers[:-1]
    ramps = centers[:, None] - frequencies[None, :]
    lower = -ramps[:-2] / widths[:-1, None]
    upper = ramps[2:] / widths[1:, None]
    bank = torch.maximum(
        torch.zeros((), dtype=torch.float64), torch.minimum(lower, upper)
    )
    # Match the canonical Whisper bank's intermediate FP32 rounding before
    # Slaney normalization; casting only at the end changes the coefficients.
    bank = bank.float()
    bank *= (2.0 / (centers[2:] - centers[:-2]))[:, None]
    return bank.float()


class MingV3ASRFeatureExtractor(SequenceFeatureExtractor):
    """Extract padded ``[clips, mel_frames, mel_bins]`` features.

    Inputs are mono ``[samples]`` or channel-first ``[channels, samples]``
    waveforms, a flat list of waveforms, or ``(waveform, sampling_rate)`` pairs.
    Waveform amplitudes are used as supplied, including integer inputs; callers
    decoding PCM should supply normalized floating point samples. Stereo is
    averaged and non-16-kHz inputs use torchaudio's sinc resampler.

    Features preserve the serving frontend's BF16 rounding. NumPy output uses
    float32 to represent those same values. Lengths always count raw mel frames,
    never projected token positions. Clips are not truncated or padded to 30 s.
    """

    model_input_names = ["audio_feats", "audio_feats_lengths"]

    def __init__(
        self,
        feature_size=128,
        sampling_rate=16000,
        padding_value=0.0,
        audio_config=None,
        **kwargs,
    ):
        if sampling_rate != 16000:
            raise ValueError("Ming feature extraction requires sampling_rate=16000")
        if padding_value != 0.0:
            raise ValueError("Ming mel padding_value must be zero")
        if audio_config is None:
            audio_config = {
                "n_mels": feature_size,
                "downsampler_kernel_size_list": [3],
                "downsampler_stride_list": [2],
            }
        elif hasattr(audio_config, "to_dict"):
            audio_config = audio_config.to_dict()
        spec = MingAudioSpec.from_config(audio_config)
        self.audio_config = {
            "n_mels": spec.n_mels,
            "chunk_frames": spec.chunk_frames,
            "downsampler_kernel_size_list": list(spec.kernels),
            "downsampler_stride_list": list(spec.strides),
            "downsampler_padding_list": list(spec.paddings),
        }
        super().__init__(
            feature_size=spec.n_mels,
            sampling_rate=sampling_rate,
            padding_value=padding_value,
            **kwargs,
        )

    @property
    def spec(self):
        return MingAudioSpec.from_config(self.audio_config)

    @staticmethod
    def _is_rate_pair(value):
        return (
            isinstance(value, tuple)
            and len(value) == 2
            and isinstance(value[1], Real)
            and not isinstance(value[0], Real)
        )

    @classmethod
    def as_clips(cls, audio):
        """Normalize the public flat clip input without guessing batch axes."""
        if audio is None:
            return []
        if isinstance(audio, (torch.Tensor, np.ndarray)) or cls._is_rate_pair(audio):
            return [audio]
        if isinstance(audio, (list, tuple)):
            if not audio:
                return []
            if all(isinstance(value, Real) for value in audio):
                return [audio]
            return list(audio)
        raise ValueError(
            "audio must contain waveforms or (waveform, sampling_rate) pairs"
        )

    def _prepare_waveform(self, value, sampling_rate):
        if self._is_rate_pair(value):
            value, sampling_rate = value
        if (
            not isinstance(sampling_rate, Integral)
            or isinstance(sampling_rate, bool)
            or sampling_rate <= 0
        ):
            raise ValueError("sampling_rate must be a positive integer")
        try:
            waveform = torch.as_tensor(value)
        except (TypeError, ValueError, RuntimeError) as error:
            raise ValueError("audio must be a numeric waveform") from error
        if waveform.ndim not in (1, 2):
            raise ValueError("audio shape must be [samples] or [channels, samples]")
        if waveform.numel() == 0:
            raise ValueError("audio must not be empty")
        if waveform.is_complex() or not torch.isfinite(waveform).all():
            raise ValueError("audio must contain finite real samples")
        waveform = waveform.detach().to(device="cpu", dtype=torch.float32)
        if waveform.ndim == 2:
            waveform = waveform.mean(dim=0)
        if sampling_rate != self.sampling_rate:
            import torchaudio

            waveform = torchaudio.functional.resample(
                waveform, sampling_rate, self.sampling_rate
            )
        if waveform.numel() <= self.spec.n_fft // 2:
            raise ValueError(
                "audio is too short for Whisper reflect padding (need more than 200 samples at 16 kHz)"
            )
        if not torch.isfinite(waveform).all():
            raise ValueError(
                "audio contains non-finite values after downmix/resampling"
            )
        return waveform.contiguous()

    def _extract_mel(self, waveform):
        spec = self.spec
        spectrum = torch.stft(
            waveform,
            spec.n_fft,
            spec.hop_length,
            window=torch.hann_window(spec.n_fft),
            return_complex=True,
        )
        power = spectrum[..., :-1].abs().square()
        mel = _mel_filters(spec.n_mels) @ power
        log_mel = mel.clamp(min=1e-10).log10()
        log_mel = torch.maximum(log_mel, log_mel.max() - 8.0)
        return ((log_mel + 4.0) / 4.0).transpose(0, 1).to(torch.bfloat16)

    def __call__(
        self,
        audio,
        sampling_rate=None,
        return_tensors=None,
        padding=True,
        truncation=False,
        max_length=None,
        return_attention_mask=False,
        **kwargs,
    ):
        if kwargs:
            raise TypeError(
                f"Unsupported Ming audio options: {', '.join(sorted(kwargs))}"
            )
        if return_tensors not in (None, "pt", "np"):
            raise ValueError("Ming audio supports return_tensors='pt' or 'np'")
        if truncation or max_length is not None:
            raise ValueError(
                "Ming audio does not truncate waveforms; limit audio before processing"
            )
        if padding not in (True, False, "longest", "do_not_pad"):
            raise ValueError("Ming audio pads mel features to the longest clip")
        clips = self.as_clips(audio)
        if not clips:
            raise ValueError("audio must contain at least one nonempty waveform")
        sampling_rate = self.sampling_rate if sampling_rate is None else sampling_rate
        features = [
            self._extract_mel(self._prepare_waveform(clip, sampling_rate))
            for clip in clips
        ]
        lengths = torch.tensor([len(feature) for feature in features], dtype=torch.long)
        padded = torch.nn.utils.rnn.pad_sequence(features, batch_first=True)
        data = {"audio_feats": padded, "audio_feats_lengths": lengths}
        if return_attention_mask:
            data["audio_attention_mask"] = (
                torch.arange(padded.shape[1])[None, :] < lengths[:, None]
            ).long()
        if return_tensors != "pt":
            data = {
                key: value.float().numpy()
                if value.dtype == torch.bfloat16
                else value.numpy()
                for key, value in data.items()
            }
        return BatchFeature(data=data)


MingV3ASRFeatureExtractor.register_for_auto_class()
