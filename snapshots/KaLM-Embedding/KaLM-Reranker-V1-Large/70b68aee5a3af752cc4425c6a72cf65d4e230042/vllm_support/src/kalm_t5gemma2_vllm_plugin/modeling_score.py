from __future__ import annotations

from typing import Optional, Tuple

import torch
import torch.nn.functional as F
from transformers.modeling_outputs import BaseModelOutput, SequenceClassifierOutput
from transformers.models.t5gemma2.modeling_t5gemma2 import (
    T5Gemma2ForConditionalGeneration,
)

from .constants import (
    DEFAULT_ENCODER_CHUNK_SIZE,
    NO_TOKEN_ID,
    YES_TOKEN_ID,
)


class T5Gemma2ForScoreClassification(T5Gemma2ForConditionalGeneration):
    """Expose the pretrained yes/no decision as one classification logit."""

    def __init__(self, config):
        super().__init__(config)
        self.num_labels = 1
        self.yes_token_id = int(getattr(config, "yes_token_id", YES_TOKEN_ID))
        self.no_token_id = int(getattr(config, "no_token_id", NO_TOKEN_ID))
        self.encoder_chunk_size = getattr(
            config, "encoder_chunk_size", DEFAULT_ENCODER_CHUNK_SIZE
        )
        if self.encoder_chunk_size is not None:
            self.encoder_chunk_size = int(self.encoder_chunk_size)
        self._validate_score_config()

    def _validate_score_config(self) -> None:
        vocab_size = int(getattr(self.config, "vocab_size", 0))
        if vocab_size <= 0:
            raise ValueError("config.vocab_size must be a positive integer.")
        for name, token_id in (
            ("yes_token_id", self.yes_token_id),
            ("no_token_id", self.no_token_id),
        ):
            if token_id < 0 or token_id >= vocab_size:
                raise ValueError(
                    f"{name}={token_id} is outside vocab_size={vocab_size}."
                )
        if self.encoder_chunk_size is not None and self.encoder_chunk_size <= 0:
            raise ValueError("encoder_chunk_size must be positive or None.")

        self.config.num_labels = 1
        self.config.yes_token_id = self.yes_token_id
        self.config.no_token_id = self.no_token_id
        self.config.encoder_chunk_size = self.encoder_chunk_size

    @staticmethod
    def _pool_encoder_chunks(
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        chunk_size: int,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        batch_size, sequence_length, hidden_size = hidden_states.shape
        num_chunks = (sequence_length + chunk_size - 1) // chunk_size
        padded_length = num_chunks * chunk_size
        pad_length = padded_length - sequence_length
        if pad_length:
            hidden_states = F.pad(hidden_states, (0, 0, 0, pad_length))
            attention_mask = F.pad(attention_mask, (0, pad_length))

        hidden_states = hidden_states.view(
            batch_size, num_chunks, chunk_size, hidden_size
        )
        chunk_mask = attention_mask.view(batch_size, num_chunks, chunk_size)
        expanded_mask = chunk_mask.unsqueeze(-1).to(hidden_states.dtype)
        pooled_hidden = (hidden_states * expanded_mask).sum(dim=2)
        pooled_hidden /= chunk_mask.sum(dim=2).clamp(min=1).unsqueeze(-1)
        pooled_mask = (chunk_mask.sum(dim=2) > 0).to(attention_mask.dtype)
        return pooled_hidden, pooled_mask

    def _forward_with_optional_chunk_pooling(
        self,
        *,
        input_ids: Optional[torch.Tensor],
        attention_mask: Optional[torch.Tensor],
        decoder_input_ids: Optional[torch.Tensor],
        decoder_attention_mask: Optional[torch.Tensor],
        encoder_outputs=None,
        **kwargs,
    ):
        if self.encoder_chunk_size is None or encoder_outputs is not None:
            return super().forward(
                input_ids=input_ids,
                attention_mask=attention_mask,
                decoder_input_ids=decoder_input_ids,
                decoder_attention_mask=decoder_attention_mask,
                encoder_outputs=encoder_outputs,
                return_dict=True,
                **kwargs,
            )
        if input_ids is None:
            raise ValueError("input_ids are required when encoder_outputs is None.")
        if attention_mask is None:
            attention_mask = torch.ones_like(input_ids)

        raw_encoder_outputs = self.get_encoder()(
            input_ids=input_ids,
            attention_mask=attention_mask,
            return_dict=True,
        )
        pooled_hidden, pooled_mask = self._pool_encoder_chunks(
            raw_encoder_outputs.last_hidden_state,
            attention_mask,
            self.encoder_chunk_size,
        )
        return super().forward(
            encoder_outputs=BaseModelOutput(last_hidden_state=pooled_hidden),
            attention_mask=pooled_mask,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            return_dict=True,
            **kwargs,
        )

    def forward(
        self,
        input_ids: Optional[torch.Tensor] = None,
        attention_mask: Optional[torch.Tensor] = None,
        decoder_input_ids: Optional[torch.Tensor] = None,
        decoder_attention_mask: Optional[torch.Tensor] = None,
        encoder_outputs=None,
        labels: Optional[torch.Tensor] = None,
        output_attentions: Optional[bool] = None,
        output_hidden_states: Optional[bool] = None,
        return_dict: Optional[bool] = None,
        **kwargs,
    ) -> SequenceClassifierOutput:
        if labels is not None:
            raise NotImplementedError("This wrapper is inference-only.")
        if decoder_input_ids is None:
            raise ValueError("decoder_input_ids are required.")
        if decoder_input_ids.shape[0] == 0:
            raise ValueError("empty batches are not supported.")
        if input_ids is not None and input_ids.shape[0] == 0:
            raise ValueError("empty batches are not supported.")

        outputs = self._forward_with_optional_chunk_pooling(
            input_ids=input_ids,
            attention_mask=attention_mask,
            decoder_input_ids=decoder_input_ids,
            decoder_attention_mask=decoder_attention_mask,
            encoder_outputs=encoder_outputs,
            output_attentions=output_attentions,
            output_hidden_states=output_hidden_states,
            **kwargs,
        )
        logits = outputs.logits
        if decoder_attention_mask is None:
            sequence_lengths = torch.full(
                (logits.shape[0],),
                logits.shape[1] - 1,
                dtype=torch.long,
                device=logits.device,
            )
        else:
            sequence_lengths = decoder_attention_mask.sum(dim=1).to(torch.long) - 1
            if (sequence_lengths < 0).any():
                raise ValueError("decoder_attention_mask contains an empty sequence.")

        batch_indices = torch.arange(logits.shape[0], device=logits.device)
        last_logits = logits[batch_indices, sequence_lengths]
        yes_no_logits = torch.stack(
            (
                last_logits[:, self.yes_token_id],
                last_logits[:, self.no_token_id],
            ),
            dim=-1,
        ).float()
        if not torch.isfinite(yes_no_logits).all():
            bad_count = (~torch.isfinite(yes_no_logits).all(dim=-1)).sum().item()
            raise RuntimeError(f"Non-finite yes/no logits for {bad_count} input(s).")

        margin = yes_no_logits[:, 0] - yes_no_logits[:, 1]
        return SequenceClassifierOutput(
            logits=margin[:, None],
            hidden_states=getattr(outputs, "hidden_states", None),
            attentions=getattr(outputs, "attentions", None),
        )


__all__ = ["T5Gemma2ForScoreClassification"]

