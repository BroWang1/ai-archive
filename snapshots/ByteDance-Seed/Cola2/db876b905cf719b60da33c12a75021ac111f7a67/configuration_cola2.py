"""Configuration objects for the Cola2 Full-DiT model."""

from __future__ import annotations

from typing import Any, Optional

from transformers import GenerationConfig, PretrainedConfig


_AUTO_MAP = {
    "AutoConfig": "configuration_cola2.Cola2Config",
    "AutoModel": "modeling_cola2.Cola2ForConditionalGeneration",
    "AutoModelForCausalLM": "modeling_cola2.Cola2ForConditionalGeneration",
}


class Cola2Config(PretrainedConfig):
    """Architecture configuration for span-causal Cola2.

    Defaults describe the released 4B DiT + Qwen3-4B-shaped decoder. Tests and
    CPU examples should use :meth:`tiny`, which executes the identical graph at
    a small width and depth.
    """

    model_type = "cola2"
    keys_to_ignore_at_inference = ["past_key_values"]

    def __init__(
        self,
        vocab_size: int = 151_936,
        encoder_embedding_size: int = 2_560,
        encoder_hidden_size: int = 1_536,
        encoder_intermediate_size: int = 6_144,
        encoder_num_attention_heads: int = 12,
        encoder_num_hidden_layers: int = 0,
        pool_num_hidden_layers: int = 2,
        latent_encoder_num_hidden_layers: int = 2,
        latent_decoder_num_hidden_layers: int = 0,
        latent_dim: int = 64,
        use_variational_encoder: bool = True,
        boundary_score_alpha: float = 10.0,
        boundary_score_threshold: float = 0.5,
        target_compression_rate: float = 0.5,
        min_span_length: int = 1,
        max_span_length: int = 8,
        latent_block_causal: bool = False,
        latent_block_size: int = 8,
        dit_hidden_size: int = 2_560,
        dit_intermediate_size: int = 10_240,
        dit_num_hidden_layers: int = 34,
        dit_num_attention_heads: int = 20,
        dit_head_dim: int = 128,
        dit_rope_dim: int = 96,
        dit_block_size: int = 8,
        decoder_hidden_size: int = 2_560,
        decoder_intermediate_size: int = 9_728,
        decoder_num_hidden_layers: int = 36,
        decoder_num_attention_heads: int = 32,
        decoder_num_key_value_heads: int = 8,
        decoder_head_dim: int = 128,
        condition_num_attention_heads: int = 20,
        decoder_condition_num_hidden_layers: int = 2,
        decoder_lm_head_bias: bool = True,
        duration_hidden_size: Optional[int] = None,
        local_position_dim: int = 128,
        hidden_act: str = "silu",
        hidden_dropout: float = 0.0,
        attention_dropout: float = 0.0,
        layer_norm_eps: float = 1e-6,
        dit_layer_norm_eps: float = 1e-5,
        encoder_rope_theta: float = 500_000.0,
        condition_rope_theta: float = 500_000.0,
        decoder_rope_theta: float = 1_000_000.0,
        dit_rope_theta: float = 10_000.0,
        rope_theta: float = 1_000_000.0,
        initializer_range: float = 0.02,
        max_position_embeddings: int = 32_768,
        scaling_factor: float = 1.0,
        shifting_factor: float = 0.0,
        diffusion_time: float = 1_000.0,
        pad_token_id: int = 151_936,
        mask_token_id: int = 151_936,
        bos_token_id: Optional[int] = 151_643,
        eos_token_id: Optional[int] = 151_643,
        tie_word_embeddings: bool = False,
        auto_map: Optional[dict[str, str]] = None,
        architectures: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> None:
        self.vocab_size = int(vocab_size)
        self.encoder_embedding_size = int(encoder_embedding_size)
        self.encoder_hidden_size = int(encoder_hidden_size)
        self.encoder_intermediate_size = int(encoder_intermediate_size)
        self.encoder_num_attention_heads = int(encoder_num_attention_heads)
        self.encoder_num_hidden_layers = int(encoder_num_hidden_layers)
        self.pool_num_hidden_layers = int(pool_num_hidden_layers)
        self.latent_encoder_num_hidden_layers = int(
            latent_encoder_num_hidden_layers
        )
        self.latent_decoder_num_hidden_layers = int(
            latent_decoder_num_hidden_layers
        )
        self.latent_dim = int(latent_dim)
        self.use_variational_encoder = bool(use_variational_encoder)
        self.boundary_score_alpha = float(boundary_score_alpha)
        self.boundary_score_threshold = float(boundary_score_threshold)
        self.target_compression_rate = float(target_compression_rate)
        self.min_span_length = int(min_span_length)
        self.max_span_length = int(max_span_length)
        self.latent_block_causal = bool(latent_block_causal)
        self.latent_block_size = int(latent_block_size)

        self.dit_hidden_size = int(dit_hidden_size)
        self.dit_intermediate_size = int(dit_intermediate_size)
        self.dit_num_hidden_layers = int(dit_num_hidden_layers)
        self.dit_num_attention_heads = int(dit_num_attention_heads)
        self.dit_head_dim = int(dit_head_dim)
        self.dit_rope_dim = int(dit_rope_dim)
        self.dit_block_size = int(dit_block_size)

        self.decoder_hidden_size = int(decoder_hidden_size)
        self.decoder_intermediate_size = int(decoder_intermediate_size)
        self.decoder_num_hidden_layers = int(decoder_num_hidden_layers)
        self.decoder_num_attention_heads = int(decoder_num_attention_heads)
        self.decoder_num_key_value_heads = int(decoder_num_key_value_heads)
        self.decoder_head_dim = int(decoder_head_dim)
        self.condition_num_attention_heads = int(
            condition_num_attention_heads
        )
        self.decoder_condition_num_hidden_layers = int(
            decoder_condition_num_hidden_layers
        )
        self.decoder_lm_head_bias = bool(decoder_lm_head_bias)
        self.duration_hidden_size = int(
            duration_hidden_size or max(self.decoder_hidden_size // 2, 64)
        )
        self.local_position_dim = int(local_position_dim)

        self.hidden_act = str(hidden_act)
        self.hidden_dropout = float(hidden_dropout)
        self.attention_dropout = float(attention_dropout)
        self.layer_norm_eps = float(layer_norm_eps)
        self.dit_layer_norm_eps = float(dit_layer_norm_eps)
        self.encoder_rope_theta = float(encoder_rope_theta)
        self.condition_rope_theta = float(condition_rope_theta)
        self.decoder_rope_theta = float(decoder_rope_theta)
        self.dit_rope_theta = float(dit_rope_theta)
        self.rope_theta = float(rope_theta)
        self.initializer_range = float(initializer_range)
        self.max_position_embeddings = int(max_position_embeddings)
        self.scaling_factor = float(scaling_factor)
        self.shifting_factor = float(shifting_factor)
        self.diffusion_time = float(diffusion_time)
        self.mask_token_id = int(mask_token_id)

        self._validate_architecture()
        # These are serialized by PretrainedConfig and are fixed by this model.
        # Remove them from **kwargs to avoid passing the same keyword twice on a
        # config.json roundtrip.
        kwargs.pop("is_decoder", None)
        kwargs.pop("is_encoder_decoder", None)

        super().__init__(
            pad_token_id=int(pad_token_id),
            mask_token_id=int(mask_token_id),
            bos_token_id=bos_token_id,
            eos_token_id=eos_token_id,
            tie_word_embeddings=bool(tie_word_embeddings),
            is_decoder=True,
            is_encoder_decoder=False,
            auto_map=dict(_AUTO_MAP if auto_map is None else auto_map),
            architectures=(
                ["Cola2ForConditionalGeneration"]
                if architectures is None
                else architectures
            ),
            **kwargs,
        )

    def _validate_architecture(self) -> None:
        positive = {
            "vocab_size": self.vocab_size,
            "encoder_embedding_size": self.encoder_embedding_size,
            "encoder_hidden_size": self.encoder_hidden_size,
            "encoder_intermediate_size": self.encoder_intermediate_size,
            "encoder_num_attention_heads": self.encoder_num_attention_heads,
            "latent_dim": self.latent_dim,
            "latent_block_size": self.latent_block_size,
            "dit_hidden_size": self.dit_hidden_size,
            "dit_intermediate_size": self.dit_intermediate_size,
            "dit_num_attention_heads": self.dit_num_attention_heads,
            "dit_head_dim": self.dit_head_dim,
            "dit_block_size": self.dit_block_size,
            "decoder_hidden_size": self.decoder_hidden_size,
            "decoder_intermediate_size": self.decoder_intermediate_size,
            "decoder_num_attention_heads": self.decoder_num_attention_heads,
            "decoder_num_key_value_heads": self.decoder_num_key_value_heads,
            "decoder_head_dim": self.decoder_head_dim,
            "condition_num_attention_heads": self.condition_num_attention_heads,
            "max_span_length": self.max_span_length,
        }
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive, got {value}.")
        for name in (
            "encoder_num_hidden_layers",
            "pool_num_hidden_layers",
            "latent_encoder_num_hidden_layers",
            "latent_decoder_num_hidden_layers",
            "dit_num_hidden_layers",
            "decoder_num_hidden_layers",
            "decoder_condition_num_hidden_layers",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative.")
        if self.encoder_hidden_size % self.encoder_num_attention_heads:
            raise ValueError(
                "encoder_hidden_size must be divisible by "
                "encoder_num_attention_heads."
            )
        if (
            self.dit_num_attention_heads * self.dit_head_dim
            != self.dit_hidden_size
        ):
            raise ValueError(
                "dit_num_attention_heads * dit_head_dim must equal "
                "dit_hidden_size."
            )
        if (
            self.decoder_num_attention_heads * self.decoder_head_dim
            <= 0
        ):
            raise ValueError("Invalid decoder attention geometry.")
        if (
            self.decoder_num_attention_heads
            % self.decoder_num_key_value_heads
        ):
            raise ValueError(
                "decoder_num_attention_heads must be divisible by "
                "decoder_num_key_value_heads."
            )
        if self.decoder_hidden_size % self.condition_num_attention_heads:
            raise ValueError(
                "decoder_hidden_size must be divisible by "
                "condition_num_attention_heads."
            )
        if not 0 < self.dit_rope_dim <= self.dit_head_dim:
            raise ValueError("dit_rope_dim must be in (0, dit_head_dim].")
        if self.dit_rope_dim % 2:
            raise ValueError("dit_rope_dim must be even.")
        if self.decoder_head_dim % 2:
            raise ValueError("decoder_head_dim must be even.")
        if not 1 <= self.min_span_length <= self.max_span_length:
            raise ValueError(
                "Span lengths must satisfy 1 <= min_span_length <= "
                "max_span_length."
            )
        if not 0 < self.target_compression_rate <= 1:
            raise ValueError("target_compression_rate must be in (0, 1].")
        if self.scaling_factor == 0:
            raise ValueError("scaling_factor cannot be zero.")
        if self.diffusion_time <= 0:
            raise ValueError("diffusion_time must be positive.")

    @classmethod
    def tiny(cls, **overrides: Any) -> "Cola2Config":
        """Return a CPU-friendly config that uses the production code path."""

        values: dict[str, Any] = {
            "vocab_size": 67,
            "encoder_embedding_size": 32,
            "encoder_hidden_size": 32,
            "encoder_intermediate_size": 64,
            "encoder_num_attention_heads": 4,
            "encoder_num_hidden_layers": 0,
            "pool_num_hidden_layers": 1,
            "latent_encoder_num_hidden_layers": 1,
            "latent_decoder_num_hidden_layers": 0,
            "latent_dim": 8,
            "min_span_length": 1,
            "max_span_length": 3,
            "latent_block_size": 4,
            "dit_hidden_size": 32,
            "dit_intermediate_size": 64,
            "dit_num_hidden_layers": 2,
            "dit_num_attention_heads": 4,
            "dit_head_dim": 8,
            "dit_rope_dim": 8,
            "dit_block_size": 4,
            "decoder_hidden_size": 32,
            "decoder_intermediate_size": 64,
            "decoder_num_hidden_layers": 2,
            "decoder_num_attention_heads": 4,
            "decoder_num_key_value_heads": 2,
            "decoder_head_dim": 8,
            "condition_num_attention_heads": 4,
            "decoder_condition_num_hidden_layers": 1,
            "duration_hidden_size": 32,
            "local_position_dim": 8,
            "max_position_embeddings": 256,
            "pad_token_id": 0,
            "mask_token_id": 0,
            "bos_token_id": 1,
            "eos_token_id": 2,
        }
        values.update(overrides)
        return cls(**values)


class Cola2GenerationConfig(GenerationConfig):
    """Generation controls for the Full-DiT + span-causal inference path."""

    model_type = "cola2"

    def __init__(
        self,
        dit_num_steps: int = 8,
        dit_timestep_schedule: str = "low_noise",
        dit_timestep_power: Optional[float] = None,
        dit_cfg_disable_empty_prefix: bool = False,
        dit_guidance_scale: float = 10.0,
        decoder_guidance_scale: float = -0.9,
        span_causal_chunk_size: int = 1,
        dynamic_duration: bool = True,
        latent_feedback: bool = True,
        **kwargs: Any,
    ) -> None:
        # Accepted aliases mirror names used by the original evaluation harness.
        dit_num_steps = int(kwargs.pop("dit_steps", dit_num_steps))
        dit_guidance_scale = float(
            kwargs.pop("dit_cfg_scale", dit_guidance_scale)
        )
        decoder_guidance_scale = float(
            kwargs.pop("decoder_cfg_scale", decoder_guidance_scale)
        )
        span_causal_chunk_size = int(
            kwargs.pop(
                "span_causal_chunk_spans",
                kwargs.pop("chunk_spans", span_causal_chunk_size),
            )
        )
        latent_feedback = bool(
            kwargs.pop("latent_feedback_reencode", latent_feedback)
        )
        kwargs.setdefault("max_new_tokens", 32)
        kwargs.setdefault("do_sample", False)
        kwargs.setdefault("temperature", 1.0)
        kwargs.setdefault("top_k", 50)
        kwargs.setdefault("top_p", 1.0)
        super().__init__(**kwargs)
        self.dit_num_steps = dit_num_steps
        self.dit_timestep_schedule = str(dit_timestep_schedule)
        self.dit_timestep_power = (
            None
            if dit_timestep_power is None
            else float(dit_timestep_power)
        )
        self.dit_cfg_disable_empty_prefix = bool(
            dit_cfg_disable_empty_prefix
        )
        self.dit_guidance_scale = dit_guidance_scale
        self.decoder_guidance_scale = decoder_guidance_scale
        self.span_causal_chunk_size = span_causal_chunk_size
        self.dynamic_duration = bool(dynamic_duration)
        self.latent_feedback = bool(latent_feedback)
        self.validate()

    @property
    def dit_steps(self) -> int:
        return self.dit_num_steps

    @dit_steps.setter
    def dit_steps(self, value: int) -> None:
        self.dit_num_steps = int(value)

    @property
    def dit_cfg_scale(self) -> float:
        return self.dit_guidance_scale

    @dit_cfg_scale.setter
    def dit_cfg_scale(self, value: float) -> None:
        self.dit_guidance_scale = float(value)

    @property
    def decoder_cfg_scale(self) -> float:
        return self.decoder_guidance_scale

    @decoder_cfg_scale.setter
    def decoder_cfg_scale(self, value: float) -> None:
        self.decoder_guidance_scale = float(value)

    @property
    def chunk_spans(self) -> int:
        return self.span_causal_chunk_size

    @chunk_spans.setter
    def chunk_spans(self, value: int) -> None:
        self.span_causal_chunk_size = int(value)

    @property
    def span_causal_chunk_spans(self) -> int:
        return self.span_causal_chunk_size

    @span_causal_chunk_spans.setter
    def span_causal_chunk_spans(self, value: int) -> None:
        self.span_causal_chunk_size = int(value)

    @property
    def latent_feedback_reencode(self) -> bool:
        return self.latent_feedback

    @latent_feedback_reencode.setter
    def latent_feedback_reencode(self, value: bool) -> None:
        self.latent_feedback = bool(value)

    def validate(self, is_init: bool = False) -> None:
        super().validate(is_init=is_init)
        if getattr(self, "dit_num_steps", 1) < 1:
            raise ValueError("dit_num_steps must be at least 1.")
        if getattr(self, "dit_timestep_schedule", "uniform") not in {
            "uniform",
            "high_noise",
            "low_noise",
            "power",
        }:
            raise ValueError(
                "dit_timestep_schedule must be uniform, high_noise, "
                "low_noise, or power."
            )
        if (
            getattr(self, "dit_timestep_schedule", "uniform") == "power"
            and (
                getattr(self, "dit_timestep_power", None) is None
                or float(self.dit_timestep_power) <= 0
            )
        ):
            raise ValueError(
                "dit_timestep_power must be positive for power schedule."
            )
        if getattr(self, "span_causal_chunk_size", 1) < 1:
            raise ValueError("span_causal_chunk_size must be at least 1.")
