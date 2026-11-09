"""Hugging Face compatible Cola2 span-causal Full-DiT model."""

from __future__ import annotations

import copy
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import torch
import torch.nn.functional as F
from torch import nn
from transformers import PreTrainedModel
from transformers.generation.utils import GenerateDecoderOnlyOutput
from transformers.modeling_outputs import ModelOutput

from .configuration_cola2 import Cola2Config, Cola2GenerationConfig
from .modeling_layers import (
    AdaLN,
    DiTBlock,
    DurationHead,
    HardDurationExpander,
    Qwen3DecoderBlock,
    RMSNorm,
    TextVAEBlock,
    TimestepEmbedding,
    additive_attention_mask,
    block_causal_allow,
    causal_padding_allow,
    span_local_allow,
)


def _build_dit_timesteps(
    *,
    schedule_t: float,
    steps: int,
    schedule: str,
    power: Optional[float],
    device: torch.device,
) -> torch.Tensor:
    named_powers = {
        "uniform": 1.0,
        "high_noise": 0.5,
        "low_noise": 2.0,
    }
    if schedule == "power":
        exponent = float(power if power is not None else 1.0)
    else:
        exponent = named_powers[schedule]
    progress = torch.linspace(
        1.0,
        0.0,
        int(steps) + 1,
        dtype=torch.float32,
        device=device,
    )
    return progress.pow(exponent).mul_(float(schedule_t))


@dataclass
class Cola2EncoderOutput(ModelOutput):
    """Dynamic compression encoder output."""

    latents: Optional[torch.Tensor] = None
    latent_logvar: Optional[torch.Tensor] = None
    latent_mask: Optional[torch.Tensor] = None
    span_starts: Optional[torch.Tensor] = None
    span_ends: Optional[torch.Tensor] = None
    span_lengths: Optional[torch.Tensor] = None
    segment_ids: Optional[torch.Tensor] = None
    boundary_logits: Optional[torch.Tensor] = None
    boundary_probabilities: Optional[torch.Tensor] = None


@dataclass
class Cola2ConditionalGenerationOutput(ModelOutput):
    """Output of the same-position span-causal reconstruction forward."""

    loss: Optional[torch.Tensor] = None
    logits: Optional[torch.Tensor] = None
    latents: Optional[torch.Tensor] = None
    latent_mask: Optional[torch.Tensor] = None
    span_lengths: Optional[torch.Tensor] = None
    duration_logits: Optional[torch.Tensor] = None
    boundary_logits: Optional[torch.Tensor] = None


class CosineBoundaryScorer(nn.Module):
    """Native cosine scorer layout (``segmenter.scorer.norm`` in checkpoints)."""

    def __init__(self, config: Cola2Config) -> None:
        super().__init__()
        self.alpha = config.boundary_score_alpha
        self.threshold = config.boundary_score_threshold
        self.norm = nn.LayerNorm(
            config.encoder_hidden_size, eps=config.layer_norm_eps
        )

    def forward(
        self, hidden_states: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        batch, width, _ = hidden_states.shape
        if width <= 1:
            return hidden_states.new_zeros((batch, 0))
        normalized = self.norm(hidden_states)
        cosine = F.cosine_similarity(
            normalized[:, :-1], normalized[:, 1:], dim=-1
        )
        logits = self.alpha * (1.0 - cosine - self.threshold)
        valid = attention_mask.bool()
        return logits.masked_fill(
            ~(valid[:, :-1] & valid[:, 1:]), -1e4
        )


class DynamicSegmenter(nn.Module):
    """Auxiliary-loss-free cosine boundary scorer with hard span constraints."""

    def __init__(self, config: Cola2Config) -> None:
        super().__init__()
        self.lmin = config.min_span_length
        self.lmax = config.max_span_length
        self.scorer = CosineBoundaryScorer(config)
        rate = min(max(config.target_compression_rate, 1e-4), 1.0 - 1e-4)
        self.register_buffer(
            "rate_bias",
            torch.tensor(math.log(rate / (1.0 - rate)), dtype=torch.float32),
        )

    def forward(
        self, hidden_states: torch.Tensor, attention_mask: torch.Tensor
    ) -> dict[str, torch.Tensor]:
        batch, width, _ = hidden_states.shape
        valid = attention_mask.bool()
        logits = self.scorer(hidden_states, valid)
        if width > 1:
            probabilities = torch.sigmoid(
                logits + self.rate_bias.to(logits.dtype)
            )
        else:
            logits = hidden_states.new_zeros((batch, 0))
            probabilities = hidden_states.new_zeros((batch, 0))

        rows: list[list[tuple[int, int]]] = []
        boundaries = torch.zeros(
            batch, width, dtype=torch.bool, device=hidden_states.device
        )
        for row in range(batch):
            length = int(valid[row].long().sum().item())
            if length <= 0:
                rows.append([])
                continue
            spans: list[tuple[int, int]] = []
            start = 0
            for token_index in range(length):
                span_length = token_index - start + 1
                wanted = (
                    token_index < length - 1
                    and bool(probabilities[row, token_index] > 0.5)
                )
                should_cut = (
                    token_index == length - 1
                    or span_length >= self.lmax
                    or (wanted and span_length >= self.lmin)
                )
                if should_cut:
                    spans.append((start, token_index))
                    boundaries[row, token_index] = True
                    start = token_index + 1
            rows.append(spans)

        max_spans = max((len(row) for row in rows), default=0)
        max_spans = max(max_spans, 1)
        starts = torch.zeros(
            batch, max_spans, dtype=torch.long, device=hidden_states.device
        )
        ends = torch.zeros_like(starts)
        lengths = torch.zeros_like(starts)
        latent_mask = torch.zeros(
            batch, max_spans, dtype=torch.bool, device=hidden_states.device
        )
        segment_ids = torch.full(
            (batch, width), -1, dtype=torch.long, device=hidden_states.device
        )
        for row, spans in enumerate(rows):
            for span_index, (start, end) in enumerate(spans):
                starts[row, span_index] = start
                ends[row, span_index] = end
                lengths[row, span_index] = end - start + 1
                latent_mask[row, span_index] = True
                segment_ids[row, start : end + 1] = span_index

        return {
            "boundary_logits": logits,
            "boundary_probabilities": probabilities,
            "boundary_hard": boundaries,
            "span_starts": starts,
            "span_ends": ends,
            "span_lengths": lengths,
            "latent_mask": latent_mask,
            "segment_ids": segment_ids,
        }


class SpanLocalPool(nn.Module):
    """Span-local bidirectional contextualization followed by mean pooling."""

    def __init__(self, config: Cola2Config) -> None:
        super().__init__()
        self.blocks = nn.ModuleList(
            TextVAEBlock(
                config.encoder_hidden_size,
                config.encoder_intermediate_size,
                config.encoder_num_attention_heads,
                norm_eps=config.layer_norm_eps,
                rope_theta=config.encoder_rope_theta,
                attention_dropout=config.attention_dropout,
                hidden_dropout=config.hidden_dropout,
                norm_style="post_legacy",
            )
            for _ in range(config.pool_num_hidden_layers)
        )

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: torch.Tensor,
        segment_ids: torch.Tensor,
        latent_mask: torch.Tensor,
    ) -> torch.Tensor:
        valid = attention_mask.bool()
        positions = (torch.cumsum(valid.long(), dim=1) - 1).clamp_min(0)
        allowed = span_local_allow(valid, segment_ids)
        bias = additive_attention_mask(allowed, hidden_states.dtype)
        for block in self.blocks:
            hidden_states = block(hidden_states, bias, positions)

        batch, _, dim = hidden_states.shape
        max_spans = latent_mask.shape[1]
        pooled = hidden_states.new_zeros((batch, max_spans, dim))
        for row in range(batch):
            for span_index in range(max_spans):
                if not bool(latent_mask[row, span_index]):
                    continue
                selected = segment_ids[row] == span_index
                pooled[row, span_index] = hidden_states[row, selected].mean(
                    dim=0
                )
        return pooled


class Cola2CompressionVAE(nn.Module):
    """Dynamic text compressor and span-causal token decoder."""

    def __init__(self, config: Cola2Config) -> None:
        super().__init__()
        self.config = config
        input_rows = max(
            config.vocab_size,
            int(config.pad_token_id or 0) + 1,
            int(config.mask_token_id or 0) + 1,
        )
        self.encoder = nn.ModuleDict(
            {
                "wte": nn.Embedding(input_rows, config.encoder_embedding_size),
                "input_proj": (
                    nn.Linear(
                        config.encoder_embedding_size,
                        config.encoder_hidden_size,
                        bias=False,
                    )
                    if config.encoder_embedding_size
                    != config.encoder_hidden_size
                    else nn.Identity()
                ),
                "blocks": nn.ModuleList(
                    TextVAEBlock(
                        config.encoder_hidden_size,
                        config.encoder_intermediate_size,
                        config.encoder_num_attention_heads,
                        norm_eps=config.layer_norm_eps,
                        rope_theta=config.encoder_rope_theta,
                        attention_dropout=config.attention_dropout,
                        hidden_dropout=config.hidden_dropout,
                        norm_style="post_legacy",
                    )
                    for _ in range(config.encoder_num_hidden_layers)
                ),
            }
        )
        self.segmenter = DynamicSegmenter(config)
        self.pool = SpanLocalPool(config)
        self.latent_encoder_blocks = nn.ModuleList(
            TextVAEBlock(
                config.encoder_hidden_size,
                config.encoder_intermediate_size,
                config.encoder_num_attention_heads,
                norm_eps=config.layer_norm_eps,
                rope_theta=config.encoder_rope_theta,
                attention_dropout=config.attention_dropout,
                hidden_dropout=config.hidden_dropout,
                norm_style="post_legacy",
            )
            for _ in range(config.latent_encoder_num_hidden_layers)
        )
        posterior_size = config.latent_dim * (
            2 if config.use_variational_encoder else 1
        )
        self.posterior_proj = nn.Linear(
            config.encoder_hidden_size, posterior_size, bias=True
        )
        self.posterior_norm = nn.LayerNorm(
            config.latent_dim,
            eps=config.layer_norm_eps,
            elementwise_affine=False,
        )

        self.latent_in_proj = nn.Linear(
            config.latent_dim, config.decoder_hidden_size, bias=True
        )
        condition_intermediate = config.decoder_intermediate_size * 2
        condition_heads = config.condition_num_attention_heads
        self.latent_decoder_blocks = nn.ModuleList(
            TextVAEBlock(
                config.decoder_hidden_size,
                condition_intermediate,
                condition_heads,
                norm_eps=config.layer_norm_eps,
                rope_theta=config.condition_rope_theta,
                attention_dropout=config.attention_dropout,
                hidden_dropout=config.hidden_dropout,
                norm_style="reordered",
            )
            for _ in range(config.latent_decoder_num_hidden_layers)
        )
        self.duration_head = DurationHead(
            config.decoder_hidden_size,
            config.duration_hidden_size,
            config.max_span_length,
        )
        self.expander = HardDurationExpander(
            config.decoder_hidden_size,
            config.decoder_hidden_size,
            config.local_position_dim,
        )
        self.decoder_cond_stack = nn.ModuleList(
            TextVAEBlock(
                config.decoder_hidden_size,
                condition_intermediate,
                condition_heads,
                norm_eps=config.layer_norm_eps,
                rope_theta=config.condition_rope_theta,
                attention_dropout=config.attention_dropout,
                hidden_dropout=config.hidden_dropout,
                norm_style="reordered",
            )
            for _ in range(config.decoder_condition_num_hidden_layers)
        )

        self.decoder = nn.ModuleDict(
            {
                "blocks": nn.ModuleList(
                    Qwen3DecoderBlock(
                        config.decoder_hidden_size,
                        config.decoder_intermediate_size,
                        config.decoder_num_attention_heads,
                        config.decoder_num_key_value_heads,
                        config.decoder_head_dim,
                        norm_eps=config.layer_norm_eps,
                        rope_theta=config.decoder_rope_theta,
                        attention_dropout=config.attention_dropout,
                        hidden_dropout=config.hidden_dropout,
                    )
                    for _ in range(config.decoder_num_hidden_layers)
                ),
                "final_norm": RMSNorm(
                    config.decoder_hidden_size, eps=config.layer_norm_eps
                ),
                "final_layer": nn.Linear(
                    config.decoder_hidden_size,
                    config.vocab_size,
                    bias=config.decoder_lm_head_bias,
                ),
            }
        )
        self.decoder_mask_embedding = nn.Parameter(
            torch.zeros(config.decoder_hidden_size)
        )
        self.decoder_cond_in = nn.Linear(
            config.decoder_hidden_size,
            config.decoder_hidden_size,
            bias=True,
        )

    def token_hidden(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> torch.Tensor:
        hidden_states = self.encoder["input_proj"](
            self.encoder["wte"](input_ids)
        )
        valid = attention_mask.bool()
        positions = (torch.cumsum(valid.long(), dim=1) - 1).clamp_min(0)
        bias = additive_attention_mask(
            causal_padding_allow(valid), hidden_states.dtype
        )
        for block in self.encoder["blocks"]:
            hidden_states = block(hidden_states, bias, positions)
        return hidden_states

    def _latent_encode(
        self, pooled: torch.Tensor, latent_mask: torch.Tensor
    ) -> torch.Tensor:
        if not self.latent_encoder_blocks:
            return pooled
        valid = latent_mask.bool()
        positions = torch.arange(
            pooled.shape[1], device=pooled.device, dtype=torch.long
        ).unsqueeze(0).expand(pooled.shape[0], -1)
        if self.config.latent_block_causal:
            block_ids = positions // self.config.latent_block_size
            allowed = block_causal_allow(valid, block_ids)
        else:
            allowed = causal_padding_allow(valid)
        bias = additive_attention_mask(allowed, pooled.dtype)
        for block in self.latent_encoder_blocks:
            pooled = block(pooled, bias, positions)
        return pooled

    def _posterior(
        self, hidden_states: torch.Tensor
    ) -> tuple[torch.Tensor, Optional[torch.Tensor]]:
        parameters = self.posterior_proj(hidden_states)
        if self.config.use_variational_encoder:
            mean, logvar = parameters.chunk(2, dim=-1)
            return self.posterior_norm(mean), logvar.clamp(-30.0, 20.0)
        return self.posterior_norm(parameters), None

    def encode_dynamic(
        self, input_ids: torch.Tensor, attention_mask: torch.Tensor
    ) -> Cola2EncoderOutput:
        hidden_states = self.token_hidden(input_ids, attention_mask)
        segmentation = self.segmenter(hidden_states, attention_mask)
        pooled = self.pool(
            hidden_states,
            attention_mask,
            segmentation["segment_ids"],
            segmentation["latent_mask"],
        )
        pooled = self._latent_encode(pooled, segmentation["latent_mask"])
        latents, logvar = self._posterior(pooled)
        latents = latents * segmentation["latent_mask"].unsqueeze(-1)
        return Cola2EncoderOutput(
            latents=latents,
            latent_logvar=logvar,
            latent_mask=segmentation["latent_mask"],
            span_starts=segmentation["span_starts"],
            span_ends=segmentation["span_ends"],
            span_lengths=segmentation["span_lengths"],
            segment_ids=segmentation["segment_ids"],
            boundary_logits=segmentation["boundary_logits"],
            boundary_probabilities=segmentation["boundary_probabilities"],
        )

    def encode_given_spans(
        self, input_ids: torch.Tensor, span_lengths: torch.Tensor
    ) -> torch.Tensor:
        """Re-encode committed tokens under decoder-predicted span geometry."""

        if input_ids.ndim != 1 or span_lengths.ndim != 1:
            raise ValueError("encode_given_spans expects unpadded 1-D rows.")
        if int(span_lengths.sum().item()) != int(input_ids.numel()):
            raise ValueError(
                "Feedback spans must be positive and cover every committed token."
            )
        if bool((span_lengths <= 0).any()):
            raise ValueError("Feedback span lengths must all be positive.")
        token_batch = input_ids.unsqueeze(0)
        valid = torch.ones_like(token_batch, dtype=torch.bool)
        hidden_states = self.token_hidden(token_batch, valid)
        segment_ids = torch.empty_like(token_batch)
        offset = 0
        for span_index, length_tensor in enumerate(span_lengths):
            length = int(length_tensor.item())
            segment_ids[:, offset : offset + length] = span_index
            offset += length
        latent_mask = torch.ones(
            1,
            span_lengths.numel(),
            dtype=torch.bool,
            device=input_ids.device,
        )
        pooled = self.pool(
            hidden_states, valid, segment_ids, latent_mask
        )
        pooled = self._latent_encode(pooled, latent_mask)
        latents, _ = self._posterior(pooled)
        return latents[0]

    def latent_decode(
        self, latents: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if latents.ndim != 2:
            raise ValueError("latent_decode expects [K, latent_dim].")
        hidden_states = self.latent_in_proj(latents).unsqueeze(0)
        length = hidden_states.shape[1]
        valid = torch.ones(
            1, length, dtype=torch.bool, device=latents.device
        )
        positions = torch.arange(
            length, device=latents.device, dtype=torch.long
        ).unsqueeze(0)
        if self.config.latent_block_causal:
            block_ids = positions // self.config.latent_block_size
            allowed = block_causal_allow(valid, block_ids)
        else:
            allowed = causal_padding_allow(valid)
        bias = additive_attention_mask(allowed, hidden_states.dtype)
        for block in self.latent_decoder_blocks:
            hidden_states = block(hidden_states, bias, positions)
        duration_logits = self.duration_head(hidden_states)
        return hidden_states[0], duration_logits[0]

    def expand_and_refine(
        self, latents: torch.Tensor, span_lengths: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Create token-aligned latent conditions for one complete sequence."""

        latent_hidden, duration_logits = self.latent_decode(latents)
        condition = self.expander(latent_hidden, span_lengths)
        if condition.shape[0] == 0:
            return condition, duration_logits
        latent_blocks = (
            torch.arange(
                span_lengths.numel(),
                device=latents.device,
                dtype=torch.long,
            )
            // self.config.dit_block_size
        )
        token_blocks = torch.repeat_interleave(
            latent_blocks, span_lengths.long(), dim=0
        ).unsqueeze(0)
        valid = torch.ones(
            1, condition.shape[0], dtype=torch.bool, device=latents.device
        )
        positions = torch.arange(
            condition.shape[0], device=latents.device, dtype=torch.long
        ).unsqueeze(0)
        bias = additive_attention_mask(
            block_causal_allow(valid, token_blocks), condition.dtype
        )
        refined = condition.unsqueeze(0)
        for block in self.decoder_cond_stack:
            refined = block(refined, bias, positions)
        return refined[0], duration_logits

    def span_query_logits(
        self,
        clean_ids: torch.Tensor,
        query_condition: torch.Tensor,
        *,
        conditional: bool,
    ) -> torch.Tensor:
        """Predict one MASK-query chunk against the clean token prefix."""

        if clean_ids.ndim != 1 or query_condition.ndim != 2:
            raise ValueError("span_query_logits expects one unpadded row.")
        query_width = query_condition.shape[0]
        if query_width == 0:
            return query_condition.new_zeros((0, self.config.vocab_size))
        output_weight = self.decoder["final_layer"].weight
        if clean_ids.numel():
            clean_embedding = F.embedding(
                clean_ids.clamp(0, self.config.vocab_size - 1),
                output_weight,
            )
        else:
            clean_embedding = query_condition.new_zeros(
                (0, self.config.decoder_hidden_size)
            )
        query_embedding = self.decoder_mask_embedding.unsqueeze(0).expand(
            query_width, -1
        )
        if conditional:
            query_embedding = query_embedding + self.decoder_cond_in(
                query_condition
            )
        hidden_states = torch.cat(
            (clean_embedding, query_embedding), dim=0
        ).unsqueeze(0)
        total = hidden_states.shape[1]
        valid = torch.ones(
            1, total, dtype=torch.bool, device=hidden_states.device
        )
        positions = torch.arange(
            total, device=hidden_states.device, dtype=torch.long
        ).unsqueeze(0)
        bias = additive_attention_mask(
            causal_padding_allow(valid), hidden_states.dtype
        )
        for block in self.decoder["blocks"]:
            hidden_states = block(hidden_states, bias, positions)
        query_states = hidden_states[:, -query_width:]
        query_states = self.decoder["final_norm"](query_states)
        return self.decoder["final_layer"](query_states)[0]

    def teacher_forced_logits(
        self,
        input_ids: torch.Tensor,
        latents: torch.Tensor,
        span_lengths: torch.Tensor,
        *,
        chunk_spans: int,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Same-position dual-stream logits used by :meth:`forward`."""

        condition, duration_logits = self.expand_and_refine(
            latents, span_lengths
        )
        logits = condition.new_zeros(
            input_ids.numel(), self.config.vocab_size
        )
        bounds = torch.cat(
            (
                span_lengths.new_zeros(1),
                torch.cumsum(span_lengths, dim=0),
            ),
            dim=0,
        )
        for span_lo in range(0, span_lengths.numel(), chunk_spans):
            span_hi = min(span_lo + chunk_spans, span_lengths.numel())
            token_lo = int(bounds[span_lo].item())
            token_hi = int(bounds[span_hi].item())
            logits[token_lo:token_hi] = self.span_query_logits(
                input_ids[:token_lo],
                condition[token_lo:token_hi],
                conditional=True,
            )
        return logits, duration_logits


class _PatchProjection(nn.Module):
    def __init__(self, input_size: int, output_size: int) -> None:
        super().__init__()
        self.proj = nn.Linear(input_size, output_size)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return self.proj(hidden_states)


class Cola2DiT(nn.Module):
    """Block-causal latent flow transformer."""

    def __init__(self, config: Cola2Config) -> None:
        super().__init__()
        self.block_size = config.dit_block_size
        self.txt_in = _PatchProjection(
            config.latent_dim, config.dit_hidden_size
        )
        self.emb_in = TimestepEmbedding(
            config.dit_hidden_size, config.dit_hidden_size
        )
        self.blocks = nn.ModuleList(
            DiTBlock(
                config.dit_hidden_size,
                config.dit_intermediate_size,
                config.dit_num_attention_heads,
                config.dit_head_dim,
                config.dit_rope_dim,
                norm_eps=config.dit_layer_norm_eps,
                rope_theta=config.dit_rope_theta,
                attention_dropout=config.attention_dropout,
            )
            for _ in range(config.dit_num_hidden_layers)
        )
        self.txt_out_norm = nn.LayerNorm(
            config.dit_hidden_size,
            eps=config.dit_layer_norm_eps,
            elementwise_affine=True,
        )
        self.txt_out_ada = AdaLN(config.dit_hidden_size, ("out",))
        self.txt_out = _PatchProjection(
            config.dit_hidden_size, config.latent_dim
        )

    def forward(
        self, latent_states: torch.Tensor, timesteps: torch.Tensor
    ) -> torch.Tensor:
        if latent_states.ndim != 2:
            raise ValueError("DiT expects one latent row [L,D].")
        length = latent_states.shape[0]
        if timesteps.ndim == 0:
            timesteps = timesteps.expand(length)
        if timesteps.numel() == 1:
            timesteps = timesteps.expand(length)
        if timesteps.numel() != length:
            raise ValueError("DiT needs one timestep per latent position.")
        hidden_states = self.txt_in(latent_states).unsqueeze(0)
        embedding = self.emb_in(timesteps).unsqueeze(0)
        positions = torch.arange(
            length, device=latent_states.device, dtype=torch.long
        ).unsqueeze(0)
        valid = torch.ones(
            1, length, dtype=torch.bool, device=latent_states.device
        )
        block_ids = positions // self.block_size
        bias = additive_attention_mask(
            block_causal_allow(valid, block_ids), hidden_states.dtype
        )
        for block in self.blocks:
            hidden_states = block(
                hidden_states, embedding, bias, positions
            )
        hidden_states = self.txt_out_ada.modulate(
            hidden_states,
            embedding,
            "out",
            self.txt_out_norm,
        )
        return self.txt_out(hidden_states)[0]


class Cola2ForConditionalGeneration(PreTrainedModel):
    """Runnable span-causal Cola2 Full-DiT generation wrapper.

    Generation follows the production sequence:

    ``prompt encode -> DiT denoise -> dynamic duration -> span-causal decode
    -> feedback re-encode``.
    """

    config_class = Cola2Config
    generation_config_class = Cola2GenerationConfig
    base_model_prefix = "cola2"
    main_input_name = "input_ids"
    supports_gradient_checkpointing = False
    _no_split_modules = ["Qwen3DecoderBlock", "DiTBlock", "TextVAEBlock"]

    def __init__(self, config: Cola2Config) -> None:
        super().__init__(config)
        self.vae = Cola2CompressionVAE(config)
        self.dit = Cola2DiT(config)
        self.last_generation_stats: dict[str, int] = {}
        self.post_init()
        self.generation_config = Cola2GenerationConfig(
            pad_token_id=config.pad_token_id,
            bos_token_id=config.bos_token_id,
            eos_token_id=config.eos_token_id,
        )

    def _init_weights(self, module: nn.Module) -> None:
        if isinstance(module, nn.Linear):
            nn.init.normal_(
                module.weight, mean=0.0, std=self.config.initializer_range
            )
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, nn.Embedding):
            nn.init.normal_(
                module.weight, mean=0.0, std=self.config.initializer_range
            )
        elif isinstance(module, nn.LayerNorm):
            if module.weight is not None:
                nn.init.ones_(module.weight)
            if module.bias is not None:
                nn.init.zeros_(module.bias)
        elif isinstance(module, RMSNorm):
            nn.init.ones_(module.weight)

    @classmethod
    def from_pretrained(cls, *args: Any, **kwargs: Any) -> Any:
        """Preserve Cola2-specific generation fields after HF loading."""

        result = super().from_pretrained(*args, **kwargs)
        model = result[0] if isinstance(result, tuple) else result
        if not isinstance(model.generation_config, Cola2GenerationConfig):
            model.generation_config = Cola2GenerationConfig.from_dict(
                model.generation_config.to_dict()
            )
        return result

    def get_input_embeddings(self) -> nn.Module:
        return self.vae.encoder["wte"]

    def set_input_embeddings(self, value: nn.Module) -> None:
        self.vae.encoder["wte"] = value

    def get_output_embeddings(self) -> nn.Module:
        return self.vae.decoder["final_layer"]

    def set_output_embeddings(self, value: nn.Module) -> None:
        self.vae.decoder["final_layer"] = value

    def encode(
        self, input_ids: torch.Tensor, attention_mask: Optional[torch.Tensor] = None
    ) -> Cola2EncoderOutput:
        if attention_mask is None:
            attention_mask = input_ids.ne(self.config.pad_token_id)
        return self.vae.encode_dynamic(input_ids, attention_mask)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        labels: Optional[torch.Tensor] = None,
        return_dict: Optional[bool] = None,
        **_: Any,
    ) -> Union[Cola2ConditionalGenerationOutput, tuple[torch.Tensor, ...]]:
        """Encode and run the real span-causal reconstruction graph.

        Unlike an autoregressive LM, Cola2 predicts each token at the same
        position from its latent condition and the clean prefix available at the
        start of that complete-span chunk.
        """

        return_dict = (
            self.config.use_return_dict
            if return_dict is None
            else bool(return_dict)
        )
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch, sequence].")
        if attention_mask is None:
            attention_mask = input_ids.ne(self.config.pad_token_id)
        attention_mask = attention_mask.bool()
        encoder_output = self.vae.encode_dynamic(input_ids, attention_mask)
        batch, width = input_ids.shape
        logits = next(self.parameters()).new_zeros(
            batch, width, self.config.vocab_size
        )
        duration_logits = next(self.parameters()).new_zeros(
            batch,
            encoder_output.latents.shape[1],
            self.config.max_span_length,
        )
        chunk_spans = int(
            getattr(self.generation_config, "span_causal_chunk_size", 1)
        )
        for row in range(batch):
            token_count = int(attention_mask[row].long().sum().item())
            latent_count = int(
                encoder_output.latent_mask[row].long().sum().item()
            )
            if token_count <= 0 or latent_count <= 0:
                continue
            row_logits, row_duration = self.vae.teacher_forced_logits(
                input_ids[row, attention_mask[row]],
                encoder_output.latents[row, :latent_count],
                encoder_output.span_lengths[row, :latent_count],
                chunk_spans=chunk_spans,
            )
            logits[row, attention_mask[row]] = row_logits
            duration_logits[row, :latent_count] = row_duration

        loss = None
        if labels is not None:
            if labels.shape != input_ids.shape:
                raise ValueError("labels must have the same shape as input_ids.")
            supervised = attention_mask & labels.ge(0)
            if bool(supervised.any()):
                loss = F.cross_entropy(
                    logits[supervised].float(),
                    labels[supervised].clamp(
                        min=0, max=self.config.vocab_size - 1
                    ),
                )
            else:
                loss = logits.sum() * 0.0

        output = Cola2ConditionalGenerationOutput(
            loss=loss,
            logits=logits,
            latents=encoder_output.latents,
            latent_mask=encoder_output.latent_mask,
            span_lengths=encoder_output.span_lengths,
            duration_logits=duration_logits,
            boundary_logits=encoder_output.boundary_logits,
        )
        if return_dict:
            return output
        values: tuple[torch.Tensor, ...] = (
            logits,
            encoder_output.latents,
            encoder_output.span_lengths,
            duration_logits,
        )
        return ((loss,) + values) if loss is not None else values

    def prepare_inputs_for_generation(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            **kwargs,
        }

    def _scale_latents(self, latents: torch.Tensor) -> torch.Tensor:
        return (
            latents - self.config.shifting_factor
        ) * self.config.scaling_factor

    def _unscale_latents(self, latents: torch.Tensor) -> torch.Tensor:
        return (
            latents / self.config.scaling_factor
        ) + self.config.shifting_factor

    def _dit_drift(
        self,
        prefix: torch.Tensor,
        block: torch.Tensor,
        block_timesteps: torch.Tensor,
        *,
        conditional: bool,
    ) -> torch.Tensor:
        if conditional and prefix.numel():
            states = torch.cat((prefix, block), dim=0)
            timesteps = torch.cat(
                (
                    block_timesteps.new_zeros(prefix.shape[0]),
                    block_timesteps,
                ),
                dim=0,
            )
            return self.dit(states, timesteps)[-block.shape[0] :]
        return self.dit(block, block_timesteps)

    def _denoise_block(
        self,
        prefix: torch.Tensor,
        block_init: torch.Tensor,
        clean_prefix_length: int,
        generation_config: Cola2GenerationConfig,
    ) -> torch.Tensor:
        state = block_init.float()
        clean = block_init[:clean_prefix_length].float().clone()
        timesteps = _build_dit_timesteps(
            schedule_t=self.config.diffusion_time,
            steps=generation_config.dit_num_steps,
            schedule=generation_config.dit_timestep_schedule,
            power=generation_config.dit_timestep_power,
            device=state.device,
        )
        model_dtype = self.dit.txt_in.proj.weight.dtype
        for current, following in zip(
            timesteps[:-1], timesteps[1:], strict=True
        ):
            step = torch.full(
                (state.shape[0],),
                float(current.item()),
                dtype=torch.float32,
                device=state.device,
            )
            if clean_prefix_length:
                step[:clean_prefix_length] = 0.0
            state_model = state.to(model_dtype)
            prefix_model = prefix.to(model_dtype)
            step_model = step.to(model_dtype)
            conditional = self._dit_drift(
                prefix_model,
                state_model,
                step_model,
                conditional=True,
            ).float()
            apply_cfg = (
                abs(generation_config.dit_guidance_scale - 1.0) > 1e-8
                and not (
                    generation_config.dit_cfg_disable_empty_prefix
                    and prefix.numel() == 0
                )
            )
            if apply_cfg:
                unconditional = self._dit_drift(
                    prefix_model,
                    state_model,
                    step_model,
                    conditional=False,
                ).float()
                drift = (
                    generation_config.dit_guidance_scale
                    * (conditional - unconditional)
                    + unconditional
                )
            else:
                drift = conditional
            dt = float((current - following).item()) / self.config.diffusion_time
            state = state - drift * dt
            if clean_prefix_length:
                state[:clean_prefix_length] = clean
            self.last_generation_stats["dit_denoise_steps"] += 1
        return state

    @staticmethod
    def _filter_logits(
        logits: torch.Tensor, top_k: int, top_p: float
    ) -> torch.Tensor:
        filtered = logits.clone()
        if top_k > 0:
            k = min(int(top_k), filtered.shape[-1])
            threshold = torch.topk(filtered, k, dim=-1).values[:, -1:]
            filtered.masked_fill_(filtered < threshold, float("-inf"))
        if 0.0 < top_p < 1.0:
            sorted_logits, sorted_indices = filtered.sort(
                dim=-1, descending=True
            )
            cumulative = sorted_logits.softmax(-1).cumsum(-1)
            remove = cumulative > top_p
            remove[:, 1:] = remove[:, :-1].clone()
            remove[:, 0] = False
            remove = torch.zeros_like(remove).scatter(
                1, sorted_indices, remove
            )
            filtered.masked_fill_(remove, float("-inf"))
        return filtered

    def _sample_chunk(
        self,
        logits: torch.Tensor,
        clean_ids: torch.Tensor,
        generation_config: Cola2GenerationConfig,
        generator: Optional[torch.Generator],
    ) -> tuple[torch.Tensor, torch.Tensor]:
        scores = logits.float().clone()
        penalty = float(generation_config.repetition_penalty)
        if penalty != 1.0 and clean_ids.numel():
            token_ids = clean_ids.unique().clamp(
                0, self.config.vocab_size - 1
            )
            selected = scores[:, token_ids]
            selected = torch.where(
                selected < 0, selected * penalty, selected / penalty
            )
            scores[:, token_ids] = selected
        if not generation_config.do_sample:
            return scores.argmax(dim=-1), scores
        temperature = float(generation_config.temperature)
        if temperature <= 0:
            raise ValueError("temperature must be positive when do_sample=True.")
        scores = scores / temperature
        scores = self._filter_logits(
            scores,
            int(generation_config.top_k),
            float(generation_config.top_p),
        )
        probabilities = scores.softmax(dim=-1)
        sampled = torch.multinomial(
            probabilities, num_samples=1, generator=generator
        ).squeeze(-1)
        return sampled, scores

    def _span_causal_sample(
        self,
        clean_ids: torch.Tensor,
        query_condition: torch.Tensor,
        span_lengths: torch.Tensor,
        generation_config: Cola2GenerationConfig,
        generator: Optional[torch.Generator],
    ) -> tuple[torch.Tensor, list[torch.Tensor]]:
        committed = clean_ids
        sampled_pieces: list[torch.Tensor] = []
        score_rows: list[torch.Tensor] = []
        bounds = torch.cat(
            (
                span_lengths.new_zeros(1),
                torch.cumsum(span_lengths, dim=0),
            ),
            dim=0,
        )
        chunk_spans = generation_config.span_causal_chunk_size
        for span_lo in range(0, span_lengths.numel(), chunk_spans):
            span_hi = min(span_lo + chunk_spans, span_lengths.numel())
            token_lo = int(bounds[span_lo].item())
            token_hi = int(bounds[span_hi].item())
            condition = query_condition[token_lo:token_hi]
            logits_conditional = self.vae.span_query_logits(
                committed, condition, conditional=True
            ).float()
            weight = generation_config.decoder_guidance_scale
            if abs(weight) > 1e-12:
                logits_unconditional = self.vae.span_query_logits(
                    committed, condition, conditional=False
                ).float()
                logits = (
                    (1.0 + weight) * logits_conditional
                    - weight * logits_unconditional
                )
            else:
                logits = logits_conditional
            sampled, scores = self._sample_chunk(
                logits, committed, generation_config, generator
            )
            committed = torch.cat((committed, sampled), dim=0)
            sampled_pieces.append(sampled)
            score_rows.extend(scores.unbind(dim=0))
            self.last_generation_stats["decoder_chunks"] += 1
        if not sampled_pieces:
            return clean_ids.new_zeros((0,)), score_rows
        return torch.cat(sampled_pieces, dim=0), score_rows

    def _generate_one(
        self,
        prompt_ids: torch.Tensor,
        max_new_tokens: int,
        generation_config: Cola2GenerationConfig,
        generator: Optional[torch.Generator],
    ) -> tuple[torch.Tensor, list[torch.Tensor]]:
        if prompt_ids.numel() == 0:
            raise ValueError("Cola2 generation requires a non-empty prompt.")
        attention_mask = torch.ones_like(prompt_ids, dtype=torch.bool)
        encoded = self.vae.encode_dynamic(
            prompt_ids.unsqueeze(0), attention_mask.unsqueeze(0)
        )
        latent_count = int(encoded.latent_mask[0].long().sum().item())
        current_unscaled = encoded.latents[0, :latent_count].float()
        current_lengths = encoded.span_lengths[0, :latent_count].long()
        committed_ids = prompt_ids.clone()
        visible_tokens: list[int] = []
        visible_scores: list[torch.Tensor] = []
        eos_token_ids = generation_config.eos_token_id
        if eos_token_ids is None:
            eos_set: set[int] = set()
        elif isinstance(eos_token_ids, int):
            eos_set = {int(eos_token_ids)}
        else:
            eos_set = {int(value) for value in eos_token_ids}

        while len(visible_tokens) < max_new_tokens:
            scaled = self._scale_latents(current_unscaled)
            block_size = self.config.dit_block_size
            remainder = int(scaled.shape[0]) % block_size
            if remainder:
                prefix_length = int(scaled.shape[0]) - remainder
                clean_block = scaled[-remainder:]
                new_latent_count = block_size - remainder
            else:
                prefix_length = int(scaled.shape[0])
                clean_block = scaled.new_zeros((0, scaled.shape[-1]))
                new_latent_count = block_size
            prefix = scaled[:prefix_length]
            noise = torch.randn(
                new_latent_count,
                self.config.latent_dim,
                dtype=torch.float32,
                device=scaled.device,
                generator=generator,
            )
            block_init = torch.cat((clean_block.float(), noise), dim=0)
            denoised = self._denoise_block(
                prefix,
                block_init,
                remainder,
                generation_config,
            )
            block_unscaled = self._unscale_latents(denoised)
            candidate = torch.cat(
                (current_unscaled[:prefix_length], block_unscaled), dim=0
            )

            _, all_duration_logits = self.vae.latent_decode(
                candidate.to(self.vae.latent_in_proj.weight.dtype)
            )
            self.last_generation_stats["duration_predictions"] += 1
            if generation_config.dynamic_duration:
                predicted = all_duration_logits.argmax(dim=-1).long() + 1
            else:
                fixed = max(
                    1,
                    int(
                        round(
                            1.0 / self.config.target_compression_rate
                        )
                    ),
                )
                predicted = torch.full(
                    (candidate.shape[0],),
                    min(fixed, self.config.max_span_length),
                    dtype=torch.long,
                    device=candidate.device,
                )
            if remainder:
                predicted[prefix_length : prefix_length + remainder] = (
                    current_lengths[-remainder:]
                )
            new_lengths = predicted[-new_latent_count:]
            candidate_lengths = torch.cat(
                (current_lengths, new_lengths), dim=0
            )
            condition, _ = self.vae.expand_and_refine(
                candidate.to(self.vae.latent_in_proj.weight.dtype),
                candidate_lengths,
            )
            new_token_offset = int(current_lengths.sum().item())
            new_condition = condition[new_token_offset:]
            sampled, sampled_scores = self._span_causal_sample(
                committed_ids,
                new_condition,
                new_lengths,
                generation_config,
                generator,
            )
            committed_ids = torch.cat((committed_ids, sampled), dim=0)
            current_lengths = candidate_lengths

            stop = False
            for token, score in zip(
                sampled.detach().tolist(), sampled_scores, strict=True
            ):
                if len(visible_tokens) >= max_new_tokens:
                    break
                visible_tokens.append(int(token))
                visible_scores.append(score)
                if int(token) in eos_set:
                    stop = True
                    break

            if generation_config.latent_feedback:
                current_unscaled = self.vae.encode_given_spans(
                    committed_ids, current_lengths
                ).float()
                self.last_generation_stats["feedback_rounds"] += 1
            else:
                current_unscaled = candidate.float()
            self.last_generation_stats["generation_rounds"] += 1
            if stop:
                break

        return torch.tensor(
            visible_tokens, dtype=torch.long, device=prompt_ids.device
        ), visible_scores

    def _resolve_generation_config(
        self,
        generation_config: Optional[Union[Cola2GenerationConfig, Mapping[str, Any]]],
        kwargs: dict[str, Any],
    ) -> Cola2GenerationConfig:
        if generation_config is None:
            config = copy.deepcopy(self.generation_config)
        elif isinstance(generation_config, Mapping):
            config = Cola2GenerationConfig.from_dict(dict(generation_config))
        elif isinstance(generation_config, Cola2GenerationConfig):
            config = copy.deepcopy(generation_config)
        else:
            config = Cola2GenerationConfig.from_dict(
                generation_config.to_dict()
            )
        unused = config.update(**kwargs)
        if unused:
            names = ", ".join(sorted(unused))
            raise ValueError(f"Unused generation arguments: {names}.")
        config.validate()
        if int(config.num_return_sequences) != 1:
            raise ValueError("Cola2 currently supports num_return_sequences=1.")
        if int(config.num_beams) != 1:
            raise ValueError(
                "Beam search is not defined for block-parallel span-causal decoding."
            )
        return config

    @torch.no_grad()
    def generate(
        self,
        input_ids: Optional[torch.Tensor] = None,
        generation_config: Optional[
            Union[Cola2GenerationConfig, Mapping[str, Any]]
        ] = None,
        attention_mask: Optional[torch.Tensor] = None,
        generator: Optional[torch.Generator] = None,
        streamer: Any = None,
        **kwargs: Any,
    ) -> Union[torch.Tensor, GenerateDecoderOnlyOutput]:
        """Generate continuations with Full-DiT and span-causal decoding."""

        if input_ids is None:
            bos = self.config.bos_token_id
            if bos is None:
                raise ValueError("input_ids or bos_token_id is required.")
            input_ids = torch.tensor(
                [[bos]], dtype=torch.long, device=self.device
            )
        if input_ids.ndim != 2:
            raise ValueError("input_ids must have shape [batch, sequence].")
        if attention_mask is None:
            attention_mask = input_ids.ne(self.config.pad_token_id)
        if attention_mask.shape != input_ids.shape:
            raise ValueError("attention_mask must match input_ids.")

        config = self._resolve_generation_config(generation_config, kwargs)
        self.last_generation_stats = {
            "prompt_encodes": int(input_ids.shape[0]),
            "dit_denoise_steps": 0,
            "duration_predictions": 0,
            "decoder_chunks": 0,
            "feedback_rounds": 0,
            "generation_rounds": 0,
        }
        generated_rows: list[torch.Tensor] = []
        score_rows: list[list[torch.Tensor]] = []
        prompt_lengths: list[int] = []
        for row in range(input_ids.shape[0]):
            valid_ids = input_ids[row, attention_mask[row].bool()]
            prompt_lengths.append(int(valid_ids.numel()))
            if config.max_new_tokens is not None:
                budget = int(config.max_new_tokens)
            else:
                budget = max(0, int(config.max_length) - int(valid_ids.numel()))
            generated, scores = self._generate_one(
                valid_ids, budget, config, generator
            )
            generated_rows.append(generated)
            score_rows.append(scores)

        max_generated = max((row.numel() for row in generated_rows), default=0)
        pad_id = config.pad_token_id
        if pad_id is None:
            pad_id = (
                config.eos_token_id
                if isinstance(config.eos_token_id, int)
                else self.config.pad_token_id
            )
        if pad_id is None:
            pad_id = 0
        sequences = input_ids.new_full(
            (input_ids.shape[0], input_ids.shape[1] + max_generated),
            int(pad_id),
        )
        sequences[:, : input_ids.shape[1]] = input_ids
        for row, generated in enumerate(generated_rows):
            sequences[
                row,
                input_ids.shape[1] : input_ids.shape[1] + generated.numel(),
            ] = generated

        if streamer is not None:
            if input_ids.shape[0] != 1:
                raise ValueError("streamer is supported only for batch size 1.")
            for token in generated_rows[0]:
                streamer.put(token.reshape(1, 1).cpu())
            streamer.end()

        if not config.return_dict_in_generate:
            return sequences
        scores_tuple = None
        if config.output_scores:
            score_steps: list[torch.Tensor] = []
            for step in range(max_generated):
                rows = []
                for row_scores in score_rows:
                    if step < len(row_scores):
                        rows.append(row_scores[step])
                    else:
                        filler = next(self.parameters()).new_full(
                            (self.config.vocab_size,), float("-inf")
                        )
                        if 0 <= int(pad_id) < self.config.vocab_size:
                            filler[int(pad_id)] = 0.0
                        rows.append(filler)
                score_steps.append(torch.stack(rows, dim=0))
            scores_tuple = tuple(score_steps)
        return GenerateDecoderOnlyOutput(
            sequences=sequences,
            scores=scores_tuple,
        )

    @staticmethod
    def _read_checkpoint_state(
        source: Union[str, Path, Mapping[str, torch.Tensor]],
        map_location: Union[str, torch.device] = "cpu",
    ) -> dict[str, torch.Tensor]:
        if isinstance(source, Mapping):
            raw: Any = dict(source)
        else:
            path = Path(source)
            if path.is_dir():
                safe_index = path / "model.safetensors.index.json"
                bin_index = path / "pytorch_model.bin.index.json"
                if safe_index.exists() or bin_index.exists():
                    index_path = (
                        safe_index if safe_index.exists() else bin_index
                    )
                    with index_path.open("r", encoding="utf-8") as handle:
                        shard_names = sorted(
                            set(json.load(handle)["weight_map"].values())
                        )
                    state: dict[str, torch.Tensor] = {}
                    for shard_name in shard_names:
                        shard = Cola2ForConditionalGeneration._read_checkpoint_state(
                            path / shard_name, map_location=map_location
                        )
                        overlap = state.keys() & shard.keys()
                        if overlap:
                            raise RuntimeError(
                                f"Duplicate checkpoint keys: {sorted(overlap)[:5]}"
                            )
                        state.update(shard)
                    return state
                candidates = (
                    path / "model.safetensors",
                    path / "pytorch_model.bin",
                )
                path = next(
                    (candidate for candidate in candidates if candidate.exists()),
                    path,
                )
                if path.is_dir():
                    raise FileNotFoundError(
                        f"No model.safetensors or pytorch_model.bin in {path}."
                    )
            if path.suffix == ".safetensors":
                from safetensors.torch import load_file

                raw = load_file(str(path), device=str(map_location))
            else:
                raw = torch.load(
                    path, map_location=map_location, weights_only=True
                )
        if isinstance(raw, Mapping):
            for key in ("state_dict", "model"):
                nested = raw.get(key)
                if isinstance(nested, Mapping) and all(
                    torch.is_tensor(value) for value in nested.values()
                ):
                    raw = nested
                    break
        if not isinstance(raw, Mapping) or not all(
            isinstance(key, str) and torch.is_tensor(value)
            for key, value in raw.items()
        ):
            raise TypeError("Checkpoint must resolve to a tensor state dictionary.")
        return dict(raw)

    def load_strict_state_dict(
        self,
        source: Union[str, Path, Mapping[str, torch.Tensor]],
        *,
        map_location: Union[str, torch.device] = "cpu",
        prefix: Optional[str] = None,
        assign: bool = False,
    ) -> "Cola2ForConditionalGeneration":
        """Load package weights with exact key and shape validation.

        ``module.`` and ``_orig_mod.`` wrappers are stripped only when they wrap
        every key.  Other conversions must pass an explicit ``prefix`` so a
        partial or accidentally wrong native checkpoint cannot load silently.
        """

        state = self._read_checkpoint_state(source, map_location)
        if prefix is not None:
            if not all(key.startswith(prefix) for key in state):
                raise RuntimeError(
                    f"Not every checkpoint key starts with prefix {prefix!r}."
                )
            state = {key[len(prefix) :]: value for key, value in state.items()}
        for wrapper in ("module.", "_orig_mod."):
            if state and all(key.startswith(wrapper) for key in state):
                state = {
                    key[len(wrapper) :]: value for key, value in state.items()
                }

        expected = self.state_dict()
        missing = sorted(expected.keys() - state.keys())
        unexpected = sorted(state.keys() - expected.keys())
        mismatched = sorted(
            (
                key,
                tuple(state[key].shape),
                tuple(expected[key].shape),
            )
            for key in expected.keys() & state.keys()
            if tuple(state[key].shape) != tuple(expected[key].shape)
        )
        if missing or unexpected or mismatched:
            parts = []
            if missing:
                parts.append(f"missing={missing[:20]}")
            if unexpected:
                parts.append(f"unexpected={unexpected[:20]}")
            if mismatched:
                parts.append(f"shape_mismatches={mismatched[:20]}")
            raise RuntimeError(
                "Strict Cola2 state_dict validation failed: " + "; ".join(parts)
            )
        self.load_state_dict(state, strict=True, assign=assign)
        return self


def build_export_components(
    exported_config: Mapping[str, Any],
) -> dict[str, nn.Module]:
    """Build strict-validation components from a legacy export config.

    This compatibility factory accepts either a public Cola2 config or an
    earlier nested, path-free config and constructs the same DiT and VAE
    modules.
    """

    raw = dict(exported_config)
    if "dit_config" not in raw or "vae_config" not in raw:
        config = Cola2Config.from_dict(raw)
        return {"dit": Cola2DiT(config), "vae": Cola2CompressionVAE(config)}

    dit = dict(raw["dit_config"])
    vae = dict(raw["vae_config"])
    backbone = dict(vae.get("qwen3_backbone_config") or {})
    backbone = dict(backbone.get("text_config", backbone))
    model_config = Cola2Config(
        vocab_size=int(vae["vocab_size"]),
        encoder_embedding_size=(
            int(backbone.get("hidden_size", vae["dim"]))
            if bool(vae.get("qwen_encoder_token_weights", False))
            else int(vae["dim"])
        ),
        encoder_hidden_size=int(vae["dim"]),
        encoder_intermediate_size=int(vae["ffn_dim"]),
        encoder_num_attention_heads=int(vae["num_heads"]),
        encoder_num_hidden_layers=int(vae["token_encoder_num_blocks"]),
        pool_num_hidden_layers=int(vae["pool_num_blocks"]),
        latent_encoder_num_hidden_layers=int(
            vae["latent_encoder_num_blocks"]
        ),
        latent_decoder_num_hidden_layers=int(
            vae["latent_decoder_num_blocks"]
        ),
        latent_dim=int(vae["latent_dim"]),
        use_variational_encoder=bool(vae["use_variation"]),
        boundary_score_alpha=float(vae["scorer_score_alpha"]),
        boundary_score_threshold=float(vae["scorer_score_tau0"]),
        target_compression_rate=float(vae["rho_target"]),
        min_span_length=int(vae["lmin"]),
        max_span_length=int(vae["lmax"]),
        latent_block_causal=bool(vae["latent_block_causal"]),
        latent_block_size=int(vae["latent_block_size"]),
        dit_hidden_size=int(dit["txt_dim"]),
        dit_intermediate_size=int(dit["txt_dim"])
        * int(dit["expand_ratio"]),
        dit_num_hidden_layers=int(dit["num_layers"]),
        dit_num_attention_heads=int(dit["heads"]),
        dit_head_dim=int(dit["head_dim"]),
        dit_rope_dim=int(
            dit["rope_dim"][0]
            if isinstance(dit["rope_dim"], list)
            else dit["rope_dim"]
        ),
        dit_block_size=int(dit["block_size"]),
        decoder_hidden_size=int(
            backbone.get("hidden_size", vae["decoder_dim"])
        ),
        decoder_intermediate_size=int(
            backbone.get(
                "intermediate_size",
                int(vae["decoder_ffn_dim"]) // 2,
            )
        ),
        decoder_num_hidden_layers=int(vae["token_decoder_num_blocks"]),
        decoder_num_attention_heads=int(
            backbone.get(
                "num_attention_heads", vae["decoder_num_heads"]
            )
        ),
        decoder_num_key_value_heads=int(
            backbone.get(
                "num_key_value_heads", vae["decoder_num_heads"]
            )
        ),
        decoder_head_dim=int(
            backbone.get(
                "head_dim",
                int(vae["decoder_dim"])
                // int(vae["decoder_num_heads"]),
            )
        ),
        condition_num_attention_heads=int(vae["decoder_num_heads"]),
        decoder_condition_num_hidden_layers=int(vae["decoder_cond_blocks"]),
        decoder_lm_head_bias=bool(vae.get("bias", True)),
        duration_hidden_size=(
            None
            if vae.get("duration_hidden_dim") is None
            else int(vae["duration_hidden_dim"])
        ),
        local_position_dim=int(vae["loc_dim"]),
        hidden_dropout=float(vae["dropout"]),
        attention_dropout=float(vae["attn_dropout"]),
        layer_norm_eps=float(vae["layer_norm_eps"]),
        dit_layer_norm_eps=float(dit["norm_eps"]),
        encoder_rope_theta=float(vae["rope_theta"]),
        condition_rope_theta=float(vae["rope_theta"]),
        decoder_rope_theta=float(
            backbone.get("rope_theta", 1_000_000.0)
        ),
        dit_rope_theta=10_000.0,
        rope_theta=float(backbone.get("rope_theta", 1_000_000.0)),
        initializer_range=float(vae["init_std"]),
        scaling_factor=float(raw.get("latent_scaling_factor", 1.0)),
        shifting_factor=float(raw.get("latent_shifting_factor", 0.0)),
        pad_token_id=int(raw["pad_token_id"]),
        mask_token_id=int(raw["mask_token_id"]),
        eos_token_id=int(raw["eos_token_id"]),
        bos_token_id=int(raw["eos_token_id"]),
    )
    return {
        "dit": Cola2DiT(model_config),
        "vae": Cola2CompressionVAE(model_config),
    }
