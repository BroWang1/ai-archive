# Copyright 2026 Ant Group. All rights reserved.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy at http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
"""Hugging Face processor for Ming V3 ASR transcription."""

import re

import numpy as np
import torch
from transformers.feature_extraction_utils import BatchFeature
from transformers.processing_utils import ProcessingKwargs, ProcessorMixin

from .audio_spec import MingAudioSpec  # noqa: F401 - include transitive dependency in HF's local module cache
from .feature_extraction_ming_v3_asr import MingV3ASRFeatureExtractor

_AUDIO_FORMS = (
    ("<audio>", "<audioPatch>", "</audio>"),
    ("<|audio_start|>", "<|audio_pad|>", "<|audio_end|>"),
)
_PLACEHOLDER = "<AUDIO>"
_ASR_INSTRUCTION = (
    "Please recognize the language of this speech and transcribe it, "
    "placing a `\t` between the identified language and the transcribe."
)


class MingV3ASRProcessorKwargs(ProcessingKwargs, total=False):
    _defaults = {
        "text_kwargs": {
            "padding": False,
            "padding_side": "left",
            "return_attention_mask": True,
            "return_token_type_ids": False,
        },
    }


class MingV3ASRProcessor(ProcessorMixin):
    """Expand audio tokens and combine an unchanged tokenizer with log-mel.

    ``audio`` (or the compatible ``audios`` spelling) is a flat list of clips in
    prompt-placeholder order. ``audio_num_clips`` records each text request's
    clip count, including zero. Audio features and raw lengths are flattened
    independently of the text batch. Image/video inputs are not supported.

    Chat-template support is inherited from ``ProcessorMixin`` for tokenizer
    compatibility. ASR inference uses ``apply_transcription_request`` instead.
    """

    feature_extractor_class = "AutoFeatureExtractor"
    tokenizer_class = "AutoTokenizer"
    valid_processor_kwargs = MingV3ASRProcessorKwargs

    def __init__(
        self,
        feature_extractor: MingV3ASRFeatureExtractor,
        tokenizer,
        chat_template=None,
    ):
        template = tokenizer.chat_template if chat_template is None else chat_template
        super().__init__(feature_extractor, tokenizer, chat_template=template)
        vocabulary = tokenizer.get_vocab()
        self.audio_start_token, self.audio_token, self.audio_end_token = next(
            (
                form
                for form in _AUDIO_FORMS
                if all(token in vocabulary for token in form)
            ),
            (None, None, None),
        )
        if self.audio_token is None:
            raise ValueError("tokenizer lacks Ming audio start/patch/end tokens")
        self.audio_token_id = tokenizer.convert_tokens_to_ids(self.audio_token)

    @staticmethod
    def _normalize_prompt(text):
        for start, patch, end in _AUDIO_FORMS:
            text = re.sub(
                re.escape(start) + "(?:" + re.escape(patch) + ")+" + re.escape(end),
                _PLACEHOLDER,
                text,
            )
        return text

    def __call__(
        self, text=None, audio=None, *, images=None, videos=None, audios=None, **kwargs
    ):
        if images is not None or videos is not None:
            raise ValueError("MingV3ASRProcessor supports audio and text only")
        if audio is not None and audios is not None:
            raise ValueError("Pass either audio or audios, not both")
        clips = self.feature_extractor.as_clips(audio if audio is not None else audios)
        if text is None:
            if not clips:
                raise ValueError("Provide text or audio")
            text = " ".join([_PLACEHOLDER] * len(clips))
        texts = [text] if isinstance(text, str) else text
        if (
            not isinstance(texts, (list, tuple))
            or not texts
            or not all(isinstance(t, str) for t in texts)
        ):
            raise ValueError("text must be a string or a nonempty list of strings")
        texts = [self._normalize_prompt(t) for t in texts]
        clip_counts = [t.count(_PLACEHOLDER) for t in texts]
        if sum(clip_counts) != len(clips):
            raise ValueError(
                f"Audio placeholder count {sum(clip_counts)} does not match {len(clips)} clips"
            )

        options = self._merge_kwargs(
            MingV3ASRProcessorKwargs,
            tokenizer_init_kwargs=self.tokenizer.init_kwargs,
            **kwargs,
        )
        text_options = options["text_kwargs"]
        audio_options = options["audio_kwargs"]
        return_tensors = text_options.get("return_tensors")
        audio_return_tensors = audio_options.get("return_tensors")
        if (
            return_tensors is not None
            and audio_return_tensors is not None
            and return_tensors != audio_return_tensors
        ):
            raise ValueError("text and audio return_tensors must match")
        if return_tensors is None:
            return_tensors = audio_return_tensors
        if return_tensors is not None:
            text_options["return_tensors"] = return_tensors
            audio_options["return_tensors"] = return_tensors
        if text_options.get("return_overflowing_tokens"):
            raise ValueError("Audio token overflow windows are not supported")
        # Top-level max_length/truncation refer to text; audio is always chunked.
        # Explicit nested audio options retain extractor validation.
        for key in ("max_length", "truncation", "padding"):
            if key not in kwargs.get("audio_kwargs", {}):
                audio_options.pop(key, None)
        audio_inputs = self.feature_extractor(clips, **audio_options) if clips else {}
        lengths = audio_inputs.get("audio_feats_lengths", [])
        token_counts = [
            self.feature_extractor.spec.token_count(int(length)) for length in lengths
        ]

        expected_counts = []
        clip_index = 0
        for index, count in enumerate(clip_counts):
            expected_counts.append(sum(token_counts[clip_index : clip_index + count]))
            for token_count in token_counts[clip_index : clip_index + count]:
                replacement = (
                    self.audio_start_token
                    + self.audio_token * token_count
                    + self.audio_end_token
                )
                texts[index] = texts[index].replace(_PLACEHOLDER, replacement, 1)
            clip_index += count
        encoded = self.tokenizer(texts, **text_options)
        for ids, expected in zip(encoded["input_ids"], expected_counts):
            actual = sum(int(token) == self.audio_token_id for token in ids)
            if actual != expected:
                raise ValueError(
                    "Audio token count changed during tokenization; do not truncate audio placeholders"
                )
        if clips:
            if return_tensors == "pt":
                audio_inputs["audio_num_clips"] = torch.tensor(
                    clip_counts, dtype=torch.long
                )
            elif return_tensors == "np":
                audio_inputs["audio_num_clips"] = np.asarray(
                    clip_counts, dtype=np.int64
                )
            else:
                audio_inputs["audio_num_clips"] = clip_counts
        return BatchFeature(data={**encoded, **audio_inputs})

    def apply_transcription_request(
        self, audio, *, prompt=None, language_hint=None,
        audio_chunk_frames=None, return_tensors="pt",
    ):
        """Prepare one audio request in the released ASR input format.

        ``prompt`` starts with the base ASR instruction and may append topic
        and hotwords without a newline. A known language can be prefixed to
        the generated answer with ``language_hint='zh'`` or ``'en'``.
        """
        if prompt is None:
            prompt = _ASR_INSTRUCTION
        if not isinstance(prompt, str) or not prompt.startswith(_ASR_INSTRUCTION):
            raise ValueError("Prompt must start with the base ASR instruction")
        if "\n" in prompt or "\r" in prompt:
            raise ValueError("Prompt metadata must be contiguous, without newlines")
        if _PLACEHOLDER in prompt:
            raise ValueError("Prompt must not contain <AUDIO>; it is appended here")
        if audio_chunk_frames is not None:
            if (isinstance(audio_chunk_frames, bool)
                    or not isinstance(audio_chunk_frames, int)
                    or audio_chunk_frames < 1):
                raise ValueError("audio_chunk_frames must be a positive integer")
            extractor = self.feature_extractor
            original_config = extractor.audio_config
            extractor.audio_config = {**original_config, "chunk_frames": audio_chunk_frames}
            try:
                _ = extractor.spec
                inputs = self(
                    text=prompt + _PLACEHOLDER, audio=audio,
                    return_tensors=return_tensors,
                )
            finally:
                extractor.audio_config = original_config
        else:
            inputs = self(
                text=prompt + _PLACEHOLDER, audio=audio,
                return_tensors=return_tensors,
            )
        if language_hint is not None:
            label = {"zh": "Chinese\t", "en": "English\t"}.get(language_hint)
            if label is None:
                raise ValueError("language_hint must be 'zh', 'en', or None")
            if return_tensors != "pt":
                raise ValueError("language_hint requires return_tensors='pt'")
            label_ids = self.tokenizer(
                label, add_special_tokens=False, return_tensors="pt",
            )["input_ids"]
            if inputs.input_ids.shape[0] != 1:
                raise ValueError("language_hint requires exactly one audio request")
            inputs["input_ids"] = torch.cat((inputs.input_ids, label_ids), dim=1)
            if "attention_mask" in inputs:
                inputs["attention_mask"] = torch.cat(
                    (inputs.attention_mask, torch.ones_like(label_ids)), dim=1,
                )
        return inputs

    @property
    def model_input_names(self):
        return [
            "input_ids",
            "attention_mask",
            "audio_feats",
            "audio_feats_lengths",
            "audio_num_clips",
        ]


MingV3ASRProcessor.register_for_auto_class()
