from __future__ import annotations

from collections.abc import Mapping
import hashlib
from typing import Any

import torch
from transformers.feature_extraction_utils import BatchFeature
from vllm.inputs import MultiModalDataDict, mm_enc_dec_input, mm_input
from vllm.multimodal.inputs import MultiModalFieldConfig, PlaceholderRange
from vllm.multimodal.parse import ModalityDataItems, MultiModalDataItems
from vllm.multimodal.processing import (
    BaseDummyInputsBuilder,
    BaseProcessingInfo,
    EncDecMultiModalProcessor,
    ProcessorInputs,
    TimingContext,
)

from .constants import TEXT_MODALITY


class TextTokenItems(ModalityDataItems[list[str], str]):
    def __init__(self, data: list[str]) -> None:
        super().__init__(data, TEXT_MODALITY)

    def get_count(self) -> int:
        return len(self.data)

    def get(self, index: int) -> str:
        return self.data[index]

    def get_processor_data(self) -> Mapping[str, object]:
        return {}

    def get_passthrough_data(self) -> Mapping[str, object]:
        return {}


class TextEncoderProcessingInfo(BaseProcessingInfo):
    def get_supported_mm_limits(self) -> Mapping[str, int | None]:
        return {TEXT_MODALITY: 1}

    def get_mm_max_tokens_per_item(
        self,
        seq_len: int,
        mm_counts: Mapping[str, int],
    ) -> Mapping[str, int] | None:
        return {TEXT_MODALITY: seq_len}

    def parse_mm_data(
        self,
        mm_data: MultiModalDataDict,
        *,
        validate: bool = True,
    ) -> MultiModalDataItems:
        text_data = mm_data.get(TEXT_MODALITY)
        if text_data is None:
            items = TextTokenItems([])
        elif isinstance(text_data, str):
            items = TextTokenItems([text_data])
        elif isinstance(text_data, list):
            items = TextTokenItems([str(item) for item in text_data])
        else:
            items = TextTokenItems([str(text_data)])
        if validate:
            self.validate_num_items(TEXT_MODALITY, items.get_count())
        return MultiModalDataItems({TEXT_MODALITY: items})


class TextEncoderDummyInputsBuilder(
    BaseDummyInputsBuilder[TextEncoderProcessingInfo]
):
    def get_dummy_text(self, mm_counts: Mapping[str, int]) -> str:
        return "<Document>: dummy"

    def get_dummy_mm_data(
        self,
        seq_len: int,
        mm_counts: Mapping[str, int],
        mm_options: Mapping[str, Any],
    ) -> MultiModalDataDict:
        count = mm_counts.get(TEXT_MODALITY, 0)
        return {TEXT_MODALITY: ["<Document>: dummy"] * count}


class TextEncoderProcessor(EncDecMultiModalProcessor[TextEncoderProcessingInfo]):
    skip_decoder_start_token = True

    def create_encoder_prompt(
        self,
        prompt: str | list[int],
        mm_items: MultiModalDataItems,
    ) -> str | list[int]:
        return prompt

    def _get_mm_fields_config(
        self,
        hf_inputs: BatchFeature,
        hf_processor_mm_kwargs: Mapping[str, object],
    ) -> Mapping[str, MultiModalFieldConfig]:
        return {
            "encoder_input_ids": MultiModalFieldConfig.batched(
                TEXT_MODALITY,
                keep_on_cpu=True,
            )
        }

    def _get_prompt_updates(self, *args, **kwargs):
        return []

    def apply(
        self,
        inputs: ProcessorInputs,
        timing_ctx: TimingContext,
    ):
        tokenizer = self.info.get_tokenizer()
        if isinstance(inputs.prompt, str):
            encoder_ids = tokenizer.encode(inputs.prompt, add_special_tokens=False)
            encoder_prompt_text = inputs.prompt
        else:
            encoder_ids = list(inputs.prompt)
            encoder_prompt_text = None
        if not encoder_ids:
            raise ValueError("The text encoder prompt cannot be empty.")

        tensor = torch.tensor([encoder_ids], dtype=torch.long)
        mm_kwargs = self._build_mm_kwargs(tensor)
        text_items = inputs.mm_data_items.get(TEXT_MODALITY)
        text_for_hash = (
            text_items.get(0)
            if text_items is not None and text_items.get_count() > 0
            else repr(encoder_ids)
        )
        digest = hashlib.sha256(str(text_for_hash).encode("utf-8")).hexdigest()
        mm_hashes = {TEXT_MODALITY: [f"{TEXT_MODALITY}:{digest}"]}
        mm_placeholders = {
            TEXT_MODALITY: [PlaceholderRange(offset=0, length=len(encoder_ids))]
        }
        encoder_inputs = mm_input(
            prompt_token_ids=encoder_ids,
            prompt=encoder_prompt_text,
            mm_kwargs=mm_kwargs,
            mm_hashes=mm_hashes,
            mm_placeholders=mm_placeholders,
        )
        return mm_enc_dec_input(
            encoder_inputs,
            decoder_prompt_token_ids=encoder_ids,
            decoder_prompt=encoder_prompt_text,
        )

    def _build_mm_kwargs(self, encoder_input_ids: torch.Tensor):
        return self._kwargs_from_batch_feature(
            BatchFeature({"encoder_input_ids": encoder_input_ids})
        )

    def _kwargs_from_batch_feature(self, batch: BatchFeature):
        from vllm.multimodal.inputs import MultiModalKwargsItems

        return MultiModalKwargsItems.from_hf_inputs(
            batch,
            self._get_mm_fields_config(batch, {}),
        )


__all__ = [
    "TextEncoderDummyInputsBuilder",
    "TextEncoderProcessingInfo",
    "TextEncoderProcessor",
    "TextTokenItems",
]

