from __future__ import annotations

from typing import Any, ClassVar

try:
    from typing import Self
except ImportError:
    from typing_extensions import Self

import torch
from sentence_transformers.base.modules import InputModule
from transformers import AutoConfig, AutoModelForSeq2SeqLM, AutoTokenizer

from .kalm_reranker_utils import (
    DEFAULT_INSTRUCTION,
    DEFAULT_SYSTEM_INSTRUCTION,
    answer_token_id,
    build_decoder_text,
    cast_floating_parameters,
    extract_yes_no_logits,
    forward_reranker_model,
    normalize_requested_dtype,
    validate_text_pairs,
)


class KaLMCrossEncoderModule(InputModule):
    """Sentence Transformers input module for KaLM encoder-decoder rerankers."""

    config_file_name = "kalm_cross_encoder_config.json"
    config_keys: ClassVar[list[str]] = [
        "query_max_length",
        "document_max_length",
        "encoder_chunk_size",
        "system_instruction",
    ]
    save_in_root = True

    def __init__(
        self,
        model_name_or_path: str,
        *,
        query_max_length: int = 512,
        document_max_length: int = 1024,
        encoder_chunk_size: int | None = 4,
        system_instruction: str = DEFAULT_SYSTEM_INSTRUCTION,
        model_kwargs: dict[str, Any] | None = None,
        processor_kwargs: dict[str, Any] | None = None,
        config_kwargs: dict[str, Any] | None = None,
        backend: str = "torch",
    ) -> None:
        super().__init__()
        if backend != "torch":
            raise ValueError(
                "KaLMCrossEncoderModule only supports backend='torch'; "
                f"received {backend!r}."
            )
        if not isinstance(model_name_or_path, str) or not model_name_or_path:
            raise ValueError("model_name_or_path must be a non-empty string.")
        if not isinstance(query_max_length, int) or query_max_length <= 0:
            raise ValueError("query_max_length must be a positive integer.")
        if not isinstance(document_max_length, int) or document_max_length <= 0:
            raise ValueError("document_max_length must be a positive integer.")
        if encoder_chunk_size is not None and (
            not isinstance(encoder_chunk_size, int) or encoder_chunk_size <= 0
        ):
            raise ValueError("encoder_chunk_size must be a positive integer or None.")
        if not isinstance(system_instruction, str):
            raise TypeError("system_instruction must be a string.")

        self.query_max_length = query_max_length
        self.max_seq_length = document_max_length
        self.encoder_chunk_size = encoder_chunk_size
        self.system_instruction = system_instruction
        self.backend = backend

        model_kwargs = dict(model_kwargs or {})
        processor_kwargs = dict(processor_kwargs or {})
        config_kwargs = dict(config_kwargs or {})

        num_labels = config_kwargs.pop("num_labels", 1)
        if num_labels != 1:
            raise ValueError(
                "KaLM reranking produces one relevance score; num_labels must be 1."
            )

        config = AutoConfig.from_pretrained(model_name_or_path, **config_kwargs)
        self.tokenizer = AutoTokenizer.from_pretrained(
            model_name_or_path, **processor_kwargs
        )
        if self.tokenizer.pad_token_id is None:
            if self.tokenizer.eos_token_id is None:
                raise ValueError(
                    "The tokenizer must define a pad token or an EOS token."
                )
            self.tokenizer.pad_token = self.tokenizer.eos_token
        self.tokenizer.padding_side = "right"
        self.processor = self.tokenizer

        requested_dtype = normalize_requested_dtype(
            model_kwargs.get("dtype", model_kwargs.get("torch_dtype"))
        )
        self.model = AutoModelForSeq2SeqLM.from_pretrained(
            model_name_or_path,
            config=config,
            **model_kwargs,
        )
        cast_floating_parameters(self.model, requested_dtype)

        self.yes_token_id = answer_token_id(self.tokenizer, "yes")
        self.no_token_id = answer_token_id(self.tokenizer, "no")

    @property
    def document_max_length(self) -> int:
        return self.max_seq_length

    @document_max_length.setter
    def document_max_length(self, value: int) -> None:
        if not isinstance(value, int) or value <= 0:
            raise ValueError("document_max_length must be a positive integer.")
        self.max_seq_length = value

    @property
    def encoder_chunk_size(self) -> int | None:
        return self._encoder_chunk_size

    @encoder_chunk_size.setter
    def encoder_chunk_size(self, value: int | None) -> None:
        if value is not None and (not isinstance(value, int) or value <= 0):
            raise ValueError("encoder_chunk_size must be a positive integer or None.")
        self._encoder_chunk_size = value

    @property
    def chunk_size(self) -> int | None:
        """Alias for the encoder token mean-pooling compression rate."""
        return self.encoder_chunk_size

    @chunk_size.setter
    def chunk_size(self, value: int | None) -> None:
        self.encoder_chunk_size = value

    def preprocess(
        self,
        inputs: list[Any],
        prompt: str | None = None,
        **kwargs: Any,
    ) -> dict[str, torch.Tensor]:
        pairs = validate_text_pairs(inputs)
        if not pairs:
            return {}

        instruction = DEFAULT_INSTRUCTION if prompt is None else prompt
        if not isinstance(instruction, str):
            raise TypeError("prompt must be a string or None.")

        encoder_texts = [f"<Document>: {document}" for _, document in pairs]
        decoder_texts = [
            build_decoder_text(
                self.tokenizer,
                query,
                instruction,
                self.system_instruction,
                self.query_max_length,
            )
            for query, _ in pairs
        ]

        encoder_batch = self.tokenizer(
            encoder_texts,
            padding=True,
            truncation=True,
            max_length=self.document_max_length,
            add_special_tokens=False,
            return_tensors="pt",
        )
        decoder_batch = self.tokenizer(
            decoder_texts,
            padding=True,
            pad_to_multiple_of=8,
            add_special_tokens=False,
            return_tensors="pt",
        )
        return {
            "input_ids": encoder_batch["input_ids"],
            "attention_mask": encoder_batch["attention_mask"],
            "decoder_input_ids": decoder_batch["input_ids"],
            "decoder_attention_mask": decoder_batch["attention_mask"],
        }

    def forward(
        self,
        features: dict[str, torch.Tensor | Any],
        **kwargs: Any,
    ) -> dict[str, torch.Tensor | Any]:
        outputs = forward_reranker_model(
            self.model,
            input_ids=features["input_ids"],
            attention_mask=features["attention_mask"],
            decoder_input_ids=features["decoder_input_ids"],
            decoder_attention_mask=features["decoder_attention_mask"],
            encoder_chunk_size=self.chunk_size,
        )
        yes_no_logits = extract_yes_no_logits(
            outputs.logits,
            features["decoder_attention_mask"],
            self.yes_token_id,
            self.no_token_id,
        )
        features["scores"] = (yes_no_logits[:, 0] - yes_no_logits[:, 1]).unsqueeze(1)
        return features

    def save(
        self,
        output_path: str,
        *args: Any,
        safe_serialization: bool = True,
        **kwargs: Any,
    ) -> None:
        self.model.save_pretrained(output_path, safe_serialization=safe_serialization)
        self.tokenizer.save_pretrained(output_path)
        self.save_config(output_path)

    @classmethod
    def load(
        cls,
        model_name_or_path: str,
        subfolder: str = "",
        token: bool | str | None = None,
        cache_folder: str | None = None,
        revision: str | None = None,
        local_files_only: bool = False,
        trust_remote_code: bool = False,
        model_kwargs: dict[str, Any] | None = None,
        processor_kwargs: dict[str, Any] | None = None,
        config_kwargs: dict[str, Any] | None = None,
        backend: str = "torch",
        **kwargs: Any,
    ) -> Self:
        module_config = cls.load_config(
            model_name_or_path,
            subfolder=subfolder,
            token=token,
            cache_folder=cache_folder,
            revision=revision,
            local_files_only=local_files_only,
        )

        supplied_model_kwargs = dict(model_kwargs or {})
        supplied_config_kwargs = dict(config_kwargs or {})
        supplied_module_kwargs = dict(kwargs)
        chunk_size_values: list[tuple[str, int | None]] = []
        for source_name, source in (
            ("model_kwargs", supplied_model_kwargs),
            ("config_kwargs", supplied_config_kwargs),
            ("module kwargs", supplied_module_kwargs),
        ):
            for key in ("chunk_size", "encoder_chunk_size"):
                if key in source:
                    chunk_size_values.append((f"{source_name}.{key}", source.pop(key)))
        if chunk_size_values:
            first_name, first_value = chunk_size_values[0]
            for current_name, current_value in chunk_size_values[1:]:
                if current_value != first_value:
                    raise ValueError(
                        "Conflicting encoder chunk sizes: "
                        f"{first_name}={first_value!r}, "
                        f"{current_name}={current_value!r}."
                    )
            module_config["encoder_chunk_size"] = first_value

        hub_kwargs = {
            "subfolder": subfolder,
            "token": token,
            "cache_dir": cache_folder,
            "revision": revision,
            "local_files_only": local_files_only,
            "trust_remote_code": trust_remote_code,
        }
        effective_model_kwargs = {**hub_kwargs, **supplied_model_kwargs}
        effective_processor_kwargs = {**hub_kwargs, **(processor_kwargs or {})}
        effective_config_kwargs = {**hub_kwargs, **supplied_config_kwargs}

        if "model_max_length" in effective_processor_kwargs:
            module_config["document_max_length"] = effective_processor_kwargs[
                "model_max_length"
            ]

        return cls(
            model_name_or_path,
            model_kwargs=effective_model_kwargs,
            processor_kwargs=effective_processor_kwargs,
            config_kwargs=effective_config_kwargs,
            backend=backend,
            **module_config,
        )


__all__ = ["KaLMCrossEncoderModule"]
