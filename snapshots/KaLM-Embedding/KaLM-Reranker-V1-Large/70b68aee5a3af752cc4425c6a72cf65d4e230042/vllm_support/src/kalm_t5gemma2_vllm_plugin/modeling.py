from __future__ import annotations

import math
import os
from typing import Iterable

import torch
import torch.nn as nn
from transformers.modeling_outputs import BaseModelOutput
from vllm.model_executor.layers.pooler import DispatchPooler
from vllm.multimodal import MULTIMODAL_REGISTRY

from .constants import (
    DEFAULT_DECODER_PAD_TO_MULTIPLE_OF,
    DEFAULT_ENCODER_CHUNK_SIZE,
    NO_TOKEN_ID,
    TEXT_MODALITY,
    YES_TOKEN_ID,
)
from .modeling_score import T5Gemma2ForScoreClassification
from .processing import (
    TextEncoderDummyInputsBuilder,
    TextEncoderProcessingInfo,
    TextEncoderProcessor,
)


def _as_token_rows(value: object) -> list[torch.Tensor]:
    if isinstance(value, torch.Tensor):
        if value.ndim == 1:
            return [value]
        if value.ndim == 2:
            return [row for row in value]
        raise ValueError(f"encoder_input_ids must be 1D/2D, got {value.shape}.")
    if isinstance(value, list):
        return [
            item.flatten()
            if isinstance(item, torch.Tensor)
            else torch.tensor(item, dtype=torch.long)
            for item in value
        ]
    raise TypeError(f"Unsupported encoder_input_ids type: {type(value)!r}")


def _split_by_position_zero(
    input_ids: torch.Tensor,
    positions: torch.Tensor,
) -> tuple[list[torch.Tensor], list[int]]:
    flat_ids = input_ids.flatten()
    starts = (positions.flatten() == 0).nonzero(as_tuple=False).flatten().tolist()
    if not starts:
        return [], []
    starts.append(int(flat_ids.numel()))
    rows: list[torch.Tensor] = []
    last_indices: list[int] = []
    for start, end in zip(starts[:-1], starts[1:]):
        if end > start:
            rows.append(flat_ids[start:end])
            last_indices.append(end - 1)
    return rows, last_indices


def _debug(message: str) -> None:
    if os.environ.get("KALM_VLLM_DEBUG") == "1":
        print(f"[kalm-vllm-debug] {message}", flush=True)


@MULTIMODAL_REGISTRY.register_processor(
    TextEncoderProcessor,
    info=TextEncoderProcessingInfo,
    dummy_inputs=TextEncoderDummyInputsBuilder,
)
class T5Gemma2VllmScoreClassification(nn.Module):
    is_pooling_model = True
    supports_multimodal = True
    score_type = "cross-encoder"
    attn_type = "encoder_decoder"
    default_seq_pooling_type = "LAST"
    default_tok_pooling_type = "ALL"

    def __init__(self, *, vllm_config, prefix: str = "") -> None:
        super().__init__()
        self.vllm_config = vllm_config
        self.model_config = vllm_config.model_config
        self.config = self.model_config.hf_config
        self.config.num_labels = 1
        self.config.yes_token_id = int(
            getattr(self.config, "yes_token_id", YES_TOKEN_ID)
        )
        self.config.no_token_id = int(
            getattr(self.config, "no_token_id", NO_TOKEN_ID)
        )
        self.config.encoder_chunk_size = getattr(
            self.config,
            "encoder_chunk_size",
            DEFAULT_ENCODER_CHUNK_SIZE,
        )
        self.encoder_chunk_size = self.config.encoder_chunk_size
        self.config.decoder_pad_to_multiple_of = int(
            getattr(
                self.config,
                "decoder_pad_to_multiple_of",
                DEFAULT_DECODER_PAD_TO_MULTIPLE_OF,
            )
        )
        self.decoder_pad_to_multiple_of = self.config.decoder_pad_to_multiple_of
        self.pad_token_id = int(getattr(self.config, "pad_token_id", 0) or 0)

        self.score_model = T5Gemma2ForScoreClassification.from_pretrained(
            self.model_config.model,
            trust_remote_code=True,
            dtype=self.model_config.dtype,
        )
        self.score_model.config.yes_token_id = self.config.yes_token_id
        self.score_model.config.no_token_id = self.config.no_token_id
        self.score_model.config.num_labels = 1
        self.score_model.config.encoder_chunk_size = self.encoder_chunk_size
        self.score_model.yes_token_id = self.config.yes_token_id
        self.score_model.no_token_id = self.config.no_token_id
        self.score_model.encoder_chunk_size = self.encoder_chunk_size
        self.score_model._validate_score_config()
        self.score_model.eval()

        pooler_config = self.model_config.pooler_config
        assert pooler_config is not None
        self.pooler = DispatchPooler.for_seq_cls(pooler_config)

    def get_language_model(self):
        return self

    def get_num_mm_encoder_tokens(self, num_tokens: int) -> int:
        if self.encoder_chunk_size is None:
            return int(num_tokens)
        return int(math.ceil(num_tokens / int(self.encoder_chunk_size)))

    def embed_input_ids(self, input_ids: torch.Tensor, *args, **kwargs) -> torch.Tensor:
        return self.score_model.get_input_embeddings()(input_ids)

    def load_weights(self, weights: Iterable[tuple[str, torch.Tensor]]) -> set[str]:
        # The semantic wrapper loads the same checkpoint directly.
        for _ in weights:
            pass
        return set(self.state_dict().keys())

    def embed_multimodal(self, **kwargs: object) -> list[torch.Tensor]:
        if "encoder_input_ids" not in kwargs:
            raise ValueError(f"Missing {TEXT_MODALITY} encoder_input_ids.")
        rows = _as_token_rows(kwargs["encoder_input_ids"])
        device = next(self.score_model.parameters()).device
        outputs: list[torch.Tensor] = []
        with torch.inference_mode():
            for row in rows:
                input_ids = row.to(device=device, dtype=torch.long).unsqueeze(0)
                attention_mask = torch.ones_like(input_ids)
                raw_encoder_outputs = self.score_model.get_encoder()(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    return_dict=True,
                )
                hidden = raw_encoder_outputs.last_hidden_state
                if self.encoder_chunk_size is not None:
                    hidden, _ = self.score_model._pool_encoder_chunks(
                        hidden,
                        attention_mask,
                        int(self.encoder_chunk_size),
                    )
                item = hidden.squeeze(0).contiguous()
                _debug(f"encoder output shape={tuple(item.shape)}")
                outputs.append(item)
        return outputs

    def _pad_decoder_rows(
        self,
        rows: list[torch.Tensor],
        device: torch.device,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        max_len = max(int(row.numel()) for row in rows)
        if self.decoder_pad_to_multiple_of > 1:
            multiple = self.decoder_pad_to_multiple_of
            max_len = int(math.ceil(max_len / multiple) * multiple)
        batch = torch.full(
            (len(rows), max_len),
            self.pad_token_id,
            dtype=torch.long,
            device=device,
        )
        mask = torch.zeros_like(batch)
        for index, row in enumerate(rows):
            row = row.to(device=device, dtype=torch.long)
            length = int(row.numel())
            batch[index, :length] = row
            mask[index, :length] = 1
        return batch, mask

    @staticmethod
    def _pad_encoder_outputs(
        encoder_outputs: list[torch.Tensor],
        device: torch.device,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        max_len = max(int(item.shape[0]) for item in encoder_outputs)
        hidden_size = int(encoder_outputs[0].shape[-1])
        batch = torch.zeros(
            (len(encoder_outputs), max_len, hidden_size),
            dtype=encoder_outputs[0].dtype,
            device=device,
        )
        mask = torch.zeros(
            (len(encoder_outputs), max_len),
            dtype=torch.long,
            device=device,
        )
        for index, item in enumerate(encoder_outputs):
            item = item.to(device=device)
            length = int(item.shape[0])
            batch[index, :length] = item
            mask[index, :length] = 1
        return batch, mask

    def forward(
        self,
        input_ids: torch.Tensor | None,
        positions: torch.Tensor,
        intermediate_tensors=None,
        inputs_embeds: torch.Tensor | None = None,
        encoder_outputs: list[torch.Tensor] | torch.Tensor | None = None,
        **kwargs,
    ) -> torch.Tensor:
        if input_ids is None:
            raise ValueError("Decoder input_ids are required.")
        decoder_rows, last_indices = _split_by_position_zero(input_ids, positions)
        hidden = input_ids.new_zeros((input_ids.numel(), 1), dtype=torch.float32)
        if not decoder_rows:
            return hidden
        if encoder_outputs is None:
            return hidden

        encoder_list = (
            [item for item in encoder_outputs]
            if isinstance(encoder_outputs, torch.Tensor)
            else list(encoder_outputs)
        )
        if len(encoder_list) != len(decoder_rows):
            raise ValueError(
                "Mismatched encoder/decoder batch sizes: "
                f"{len(encoder_list)} vs {len(decoder_rows)}."
            )

        device = next(self.score_model.parameters()).device
        decoder_batch, decoder_mask = self._pad_decoder_rows(decoder_rows, device)
        encoder_batch, encoder_mask = self._pad_encoder_outputs(encoder_list, device)
        with torch.inference_mode():
            outputs = self.score_model(
                encoder_outputs=BaseModelOutput(last_hidden_state=encoder_batch),
                attention_mask=encoder_mask,
                decoder_input_ids=decoder_batch,
                decoder_attention_mask=decoder_mask,
            )
            margins = outputs.logits.squeeze(-1).to(hidden.device, dtype=hidden.dtype)
            _debug(f"margins={margins.float().tolist()}")
        for row_index, last_index in enumerate(last_indices):
            hidden[last_index, 0] = margins[row_index]
        return hidden


__all__ = ["T5Gemma2VllmScoreClassification"]
